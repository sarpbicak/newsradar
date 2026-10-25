"""E-posta doğrulama + şifre sıfırlama (izole temp DB, anahtarsız, console arka ucu, sahte boto3).

Doğrular:
  (A) kayıt → doğrulama postası (TR/EN kullanıcının dilinde, HTML + düz metin); bağlantı doğrular;
      tekrar kullanılan / süresi dolmuş / başka adres için üretilmiş bağlantı reddedilir
  (B) "tekrar gönder": 1 dk bekleme (429 + Retry-After), süre geçince gönderir; anon yasak
  (C) şifremi unuttum: kayıtlı/kayıtsız adres AYNI yanıt (hesap sızmaz); yalnızca kayıtlıya posta;
      adres başına saatte 3 (sessiz), IP başına saatte 5 (429)
  (D) sıfırlama: 1 sa + tek kullanımlık; yeni şifre çalışır; eski oturum token'ları 401; başka
      cihazın çerezi hesabı geri getirmez; kısa şifre 422; süresi dolmuş 400
  (E) arka uçlar: console log + bellek; ses → boto3 sesv2.send_email doğru parametreler (ağ yok);
      bağlantı kökü NEWSRADAR_PUBLIC_URL'den (Host başlığı değil)
Çalıştır: python test_email_flows.py
"""
import os
import re
import sys
import tempfile
import types
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_email_flows.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="genelsifre", APP_SECRET="ef-secret-1234567890",
    ADMIN_USERNAME="rootadmin", NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_MAX_USERS="0", NEWSRADAR_TRUSTED_PROXY="render", NEWSRADAR_COOKIE_SECURE="off",
    NEWSRADAR_COOKIE_SAMESITE="lax", NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR="0",
    EMAIL_BACKEND="console", NEWSRADAR_PUBLIC_URL="https://newsradar.example",
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import update  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.api.main import app  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import EmailToken, UsageEvent, User  # noqa: E402
from app.mailer import get_mailer, send_email, EmailMessage  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


_ip = [0]


def xff(ip=None):
    _ip[0] += 1
    return {"X-Forwarded-For": ip or f"198.51.100.{_ip[0]}"}


def mails():
    return get_mailer().sent


def last_token(kind):
    m = mails()[-1]
    path = "/verify-email" if kind == "verify" else "/reset-password"
    found = re.search(re.escape("https://newsradar.example" + path) + r"\?token=([A-Za-z0-9_-]+)", m.text)
    return found.group(1) if found else None


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def age_tokens(user_id, purpose, **delta):
    with SessionLocal() as s:
        s.execute(update(EmailToken).where(EmailToken.user_id == user_id, EmailToken.purpose == purpose)
                  .values(created_at=datetime.now(timezone.utc) - timedelta(**delta),
                          expires_at=datetime.now(timezone.utc) - timedelta(**delta) + (timedelta(hours=24) if purpose == "verify" else timedelta(hours=1))))
        s.commit()


with TestClient(app) as c:
    c.post("/users/register", json={"username": "rootadmin", "password": "parola12345", "email": "root@example.com"}, headers=xff())
    print("== A: kayıt → doğrulama")
    n0 = len(mails())
    r = c.post("/users/register", json={"username": "ayse", "password": "parola12345", "email": "Ayse@Example.com"}, headers=xff())
    tok_ayse, uid = r.json()["token"], r.json()["user"]["id"]
    m = mails()[-1]
    check(len(mails()) == n0 + 1 and m.to == "ayse@example.com", "kayıttan sonra doğrulama postası gitti")
    check(r.json()["user"]["email_verified"] is False, "başta doğrulanmamış (hesap engellenmez: token var)")
    check(m.html.startswith("<!doctype html>") and "NewsRadar" in m.text and "24 saat" in m.text, "HTML + düz metin, TR")
    vt = last_token("verify")
    check(vt is not None, "bağlantı NEWSRADAR_PUBLIC_URL kökünde")
    with SessionLocal() as s:
        stored = s.query(EmailToken).filter_by(user_id=uid).one()
        check(stored.token_hash != vt and len(stored.token_hash) == 64, "token düz değil, sha256 özetiyle saklanıyor")
    check(c.post("/users/verify-email", json={"token": vt}).status_code == 200, "bağlantı doğruladı")
    check(c.get("/users/me", headers=auth(tok_ayse)).json()["email_verified"] is True, "me: email_verified=True")
    with SessionLocal() as s:
        check(s.query(UsageEvent).filter_by(user_id=uid, event_type="email_verified").count() == 1,
              "doğrulama olayı kaydedildi (admin panelinde görünür)")
    check(c.post("/users/verify-email", json={"token": vt}).status_code == 400, "aynı bağlantı ikinci kez 400")
    check(c.post("/users/verify-email", json={"token": "uydurma"}).status_code == 400, "uydurma token 400")
    # EN kullanıcı + süresi dolmuş bağlantı
    r = c.post("/users/register", json={"username": "john", "password": "parola12345", "email": "john@example.com"}, headers=xff())
    tok_john, jid = r.json()["token"], r.json()["user"]["id"]
    c.post("/users/me/language", json={"language": "en"}, headers=auth(tok_john))
    age_tokens(jid, "verify", hours=25)
    check(c.post("/users/verify-email", json={"token": last_token("verify")}).status_code == 400, "24 saati geçmiş bağlantı 400")
    # Adres değişince eski bağlantı yeni adresi doğrulamaz
    c.post("/users/me/email/resend", headers=auth(tok_john))
    old_link = last_token("verify")
    check("valid for 24 hours" in mails()[-1].text, "EN kullanıcıya İngilizce posta")
    c.post("/users/me/email", json={"email": "john2@example.com"}, headers=auth(tok_john))
    check(mails()[-1].to == "john2@example.com", "adres değişince yeni adrese posta")
    check(c.post("/users/verify-email", json={"token": old_link}).status_code == 400, "eski adresin bağlantısı yeni adresi doğrulamaz")

    print("== B: tekrar gönder")
    r = c.post("/users/me/email/resend", headers=auth(tok_john))
    check(r.status_code == 429 and int(r.headers.get("retry-after", 0)) > 0, f"1 dk dolmadan 429 + Retry-After ({r.status_code})")
    age_tokens(jid, "verify", seconds=61)
    n = len(mails())
    check(c.post("/users/me/email/resend", headers=auth(tok_john)).status_code == 200 and len(mails()) == n + 1, "1 dk sonra yeniden gönderildi")
    anon = c.post("/session/bootstrap", headers=xff()).json()["token"]
    check(c.post("/users/me/email/resend", headers=auth(anon)).status_code == 400, "misafir için gönderim yok")

    print("== C: şifremi unuttum (hesap sızmaz)")
    n = len(mails())
    r1 = c.post("/users/forgot-password", json={"email": "ayse@example.com"}, headers=xff())
    r2 = c.post("/users/forgot-password", json={"email": "kimse@example.com"}, headers=xff())
    r3 = c.post("/users/forgot-password", json={"email": "bozuk-adres"}, headers=xff())
    check(r1.status_code == r2.status_code == r3.status_code == 202 and r1.json() == r2.json() == r3.json(),
          "kayıtlı / kayıtsız / bozuk adres → aynı durum ve aynı mesaj")
    check(len(mails()) == n + 1 and mails()[-1].to == "ayse@example.com", "yalnızca kayıtlı adrese posta gitti")
    with SessionLocal() as s:
        check(s.query(UsageEvent).filter_by(user_id=uid, event_type="password_reset_requested").count() == 1,
              "sıfırlama isteği olayı kaydedildi")
    for _ in range(4):
        c.post("/users/forgot-password", json={"email": "ayse@example.com"}, headers=xff())
    with SessionLocal() as s:
        resets = s.query(EmailToken).filter_by(user_id=uid, purpose="reset").count()
    check(resets == 3, f"adres başına saatte en fazla 3 posta (fazlası sessiz) ({resets})")
    codes = [c.post("/users/forgot-password", json={"email": f"x{i}@example.com"}, headers=xff("203.0.113.9")).status_code for i in range(6)]
    check(codes[:5] == [202] * 5 and codes[5] == 429, f"IP başına saatte 5, sonra 429 ({codes})")

    print("== D: sıfırlama")
    # Ayşe'nin başka bir cihazı: çerezle bağlanmış hesap (misafirken yükseltilmiş)
    other = TestClient(app)
    t_dev = other.post("/session/bootstrap", headers=xff()).json()["token"]
    up = other.post("/users/upgrade", json={"username": "mehmet", "password": "parola12345", "email": "mehmet@example.com"}, headers=auth(t_dev))
    mtok, mid = up.json()["token"], up.json()["user"]["id"]
    check(other.post("/session/bootstrap", headers=xff()).json()["user"]["username"] == "mehmet", "önce: diğer cihazın çerezi hesabı getiriyor")
    c.post("/users/forgot-password", json={"email": "mehmet@example.com"}, headers=xff())
    rt = last_token("reset")
    # Misafirden yükseltilen hesabın dili Accept-Language'dan (TestClient'ta yok → en).
    check("valid for 1 hour" in mails()[-1].text, "sıfırlama postası kullanıcının dilinde (en, 1 saat)")
    check(c.post("/users/reset-password", json={"token": rt, "password": "kisa"}, headers=xff()).status_code == 422, "kısa şifre 422")
    r = c.post("/users/reset-password", json={"token": rt, "password": "yeniparola99"}, headers=xff())
    check(r.status_code == 200 and r.json()["token"], "geçerli bağlantı → yeni şifre + bu cihaz için taze oturum")
    check(c.get("/users/me", headers=auth(mtok)).status_code == 401, "eski oturum token'ı 401 (diğer oturumlar kapandı)")
    check(c.get("/users/me", headers=auth(r.json()["token"])).status_code == 200, "yeni token çalışıyor")
    with SessionLocal() as s:
        check(s.query(UsageEvent).filter_by(user_id=mid, event_type="password_reset").count() == 1, "sıfırlama olayı kaydedildi")
    b = other.post("/session/bootstrap", headers=xff()).json()["user"]
    check(b["username"] != "mehmet" and b["is_anonymous"], "diğer cihazın çerezi artık hesabı geri getirmiyor")
    check(c.post("/users/login", json={"username": "mehmet", "password": "yeniparola99"}, headers=xff()).status_code == 200, "yeni şifreyle giriş")
    check(c.post("/users/login", json={"username": "mehmet", "password": "parola12345"}, headers=xff()).status_code == 401, "eski şifre reddedildi")
    check(c.post("/users/reset-password", json={"token": rt, "password": "baskaparola1"}, headers=xff()).status_code == 400, "aynı bağlantı ikinci kez 400")
    c.post("/users/forgot-password", json={"email": "mehmet@example.com"}, headers=xff())
    rt2 = last_token("reset")
    age_tokens(mid, "reset", minutes=61)
    check(c.post("/users/reset-password", json={"token": rt2, "password": "baskaparola1"}, headers=xff()).status_code == 400, "1 saati geçmiş bağlantı 400")
    # Host başlığı bağlantıyı etkilemez
    c.post("/users/forgot-password", json={"email": "john2@example.com"}, headers={**xff(), "Host": "evil.example"})
    check("evil.example" not in mails()[-1].text and "https://newsradar.example/reset-password?token=" in mails()[-1].text,
          "bağlantı kökü yapılandırmadan, Host başlığından değil")

print("== E: arka uçlar")
check(get_mailer().name == "console", "EMAIL_BACKEND=console → console arka ucu")
calls = []


class FakeSes:
    def send_email(self, **kw):
        calls.append(kw)
        return {"MessageId": "x"}


fake_boto3 = types.ModuleType("boto3")
fake_boto3.client = lambda name, region_name=None: (calls.append(("client", name, region_name)), FakeSes())[1]
sys.modules["boto3"] = fake_boto3
os.environ.update(EMAIL_BACKEND="ses", EMAIL_FROM="NewsRadar <no-reply@newsradar.example>", EMAIL_SES_REGION="eu-west-1")
get_settings.cache_clear() if hasattr(get_settings, "cache_clear") else None
ok = send_email(EmailMessage(to="a@example.com", subject="Konu", text="metin", html="<p>html</p>"))
check(get_mailer().name == "ses" and ok, "EMAIL_BACKEND=ses → SES arka ucu")
check(("client", "sesv2", "eu-west-1") in calls, "boto3 sesv2 istemcisi doğru bölgede (anahtar parametresi yok)")
kw = [x for x in calls if isinstance(x, dict)][0]
check(kw["FromEmailAddress"] == "NewsRadar <no-reply@newsradar.example>" and kw["Destination"] == {"ToAddresses": ["a@example.com"]}
      and kw["Content"]["Simple"]["Body"]["Html"]["Data"] == "<p>html</p>", "gönderen, alıcı, HTML + metin gövde")


class BoomSes:
    def send_email(self, **kw):
        raise RuntimeError("throttled")


get_mailer()._client = BoomSes()
check(send_email(EmailMessage(to="a@example.com", subject="K", text="t", html="h")) is False, "SES hatası akışı bozmaz (False döner)")

print("== F: arayüz özellik bayrağı")
from fastapi import Response  # noqa: E402

from app.api.routes_public import public_features  # noqa: E402

for backend, proxy, want in (("console", "render", True), ("console", "caddy", False), ("ses", "caddy", True)):
    os.environ.update(EMAIL_BACKEND=backend, NEWSRADAR_TRUSTED_PROXY=proxy)
    get_settings.cache_clear()
    check(public_features(Response())["email"] is want, f"EMAIL_BACKEND={backend}, proxy={proxy} → email={want}")
os.environ.update(EMAIL_BACKEND="console", NEWSRADAR_TRUSTED_PROXY="render")
get_settings.cache_clear()

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
