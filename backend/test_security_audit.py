"""Kapsamlı GÜVENLİK TESTİ — saldırgan gözüyle, herkese açmadan önce.

Her madde GERÇEKTEN çalıştırılır (canlı uvicorn + httpx); "kodda doğru görünüyor"
kabul edilmez. Bölümler: A kimlik/oturum, B yetki, C kota/kaynak, D girdi/enjeksiyon,
E sır sızıntısı, F iş mantığı.

Çalıştır:  python test_security_audit.py
           NEWSRADAR_TRUSTED_PROXY=caddy python test_security_audit.py  (Docker/Caddy modu)
Çıkış kodu 0 = bloklayıcı (Kritik/Önemli) bulgu yok.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

# --- Ortam: izole temp DB + üretim-benzeri cookie (Secure/SameSite=None) ---
_db = os.path.join(tempfile.gettempdir(), "nr_test_secaudit.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_SECRET="secaudit-secret-🔒-xyz", APP_PASSWORD="sharedpw123",
    ADMIN_USERNAME="root", NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_LLM_PROVIDER="anthropic",
    NEWSRADAR_COOKIE_SECURE="on", NEWSRADAR_COOKIE_SAMESITE="none",
    NEWSRADAR_MAX_ENTITIES_ANON="3", NEWSRADAR_MAX_REFRESH_REGISTERED="3",
    NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR="10", NEWSRADAR_FEEDBACK_PER_IP_HOUR="5",
    NEWSRADAR_MAX_USERS="0",
)

import logging  # noqa: E402

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from app.api.main import app  # noqa: E402
from app.api.routes_auth import _sign  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.database import session_scope  # noqa: E402
from app.db.models import User  # noqa: E402
from app.security import LoginRateLimiter, login_limiter  # noqa: E402

# --- Log yakalama (Bölüm E: sır sızıntısı) ---
LOGS: list[str] = []
class _Cap(logging.Handler):
    def emit(self, r):
        try:
            LOGS.append(self.format(r))
        except Exception:
            pass
_cap = _Cap()
_cap.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
logging.getLogger().addHandler(_cap)
logging.getLogger().setLevel(logging.DEBUG)

PORT = 8137
BASE = f"http://127.0.0.1:{PORT}"

# --- Sonuç toplama + sınıflandırma ---
RESULTS: list[tuple[str, bool, str]] = []
def check(passed: bool, name: str, severity: str = "Önemli") -> bool:
    RESULTS.append((name, bool(passed), severity))
    tag = "✓ PASS" if passed else f"✗ FAIL [{severity}]"
    print(f"  {tag}  {name}")
    return passed

def section(title: str) -> None:
    print(f"\n{'='*70}\n{title}\n{'='*70}")


# --- HTTP yardımcıları ---
def C() -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=30)

def bearer(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}

def register(c, username, password, **hdr):
    return c.post("/users/register", json={"username": username, "password": password, "email": f"{uuid.uuid4().hex[:12]}@test.local"}, headers=hdr)

def bootstrap(c, **hdr):
    return c.post("/session/bootstrap", headers=hdr)

def pwhash_of(uid: int) -> str:
    with session_scope() as s:
        return s.get(User, uid).password_hash

def mint(uid: int, pwhash: str, iat: int | None = None) -> str:
    iat = iat if iat is not None else int(time.time())
    return f"{uid}.{iat}.{_sign(uid, iat, pwhash, get_settings().app_secret)}"


# ==================================================================== #
def run_tests():
    c = C()

    # İlk kayıt admin (ADMIN_USERNAME=root); iki normal kullanıcı + anon.
    r = register(c, "root", "adminpass1"); admin_tok = r.json()["token"]; admin_id = r.json()["user"]["id"]
    r = register(c, "alice", "alicepass1"); a_tok = r.json()["token"]; a_id = r.json()["user"]["id"]
    r = register(c, "bob", "bobpass1234"); b_tok = r.json()["token"]; b_id = r.json()["user"]["id"]
    anon_tok = bootstrap(c, **{"X-Forwarded-For": "10.0.0.1"}).json()["token"]

    # ---------------------------------------------------------------- #
    section("A. KİMLİK DOĞRULAMA VE OTURUM")

    # A1 token sahteciliği
    parts = a_tok.split(".")
    tampered = f"{parts[0]}.{parts[1]}.{parts[2][:-1]}{'a' if parts[2][-1] != 'a' else 'b'}"
    check(c.get("/users/me", headers=bearer(tampered)).status_code == 401,
          "A1 imzası bozulmuş token 401", "Kritik")
    swapped = f"{b_id}.{parts[1]}.{parts[2]}"  # alice imzası, bob uid
    rs = c.get("/users/me", headers=bearer(swapped))
    check(rs.status_code == 401, "A1 uid değiştirilip imza korunan token 401 (kimliğe bürünme yok)", "Kritik")

    # A2 token yeniden kullanımı → sadece SAHİBİNİN verisi
    me = c.get("/users/me", headers=bearer(a_tok)).json()
    check(me["id"] == a_id and me["username"] == "alice",
          "A2 token sahibinin kendi verisini döndürür (başkasının değil)", "Kritik")

    # A3 süre dolması (31 gün önce)
    expired = mint(a_id, pwhash_of(a_id), iat=int(time.time()) - 31 * 86400)
    check(c.get("/users/me", headers=bearer(expired)).status_code == 401, "A3 31 gün önceki token 401", "Önemli")

    # A4 şifre değişince eski token geçersiz
    r = register(c, "throwaway1", "throwpass1"); t_tok = r.json()["token"]; t_id = r.json()["user"]["id"]
    with session_scope() as s:
        from app.api.routes_auth import hash_password
        s.get(User, t_id).password_hash = hash_password("newpass99")
    check(c.get("/users/me", headers=bearer(t_tok)).status_code == 401,
          "A4 şifre değişince eski token geçersiz", "Önemli")

    # A5 bozuk girdi → 401, çökme yok. (İstemcinin reddettiği değerler — boş/null byte —
    # sunucuya hiç ulaşmaz; çökme sayılmaz, atlanır.)
    bad_tokens = ["", "randomstring", "a" * 100000, "a.b", "not.a.token", "1." + "9" * 40 + ".x",
                  "ab\x00cd", "   "]
    a5_ok = True
    for bt in bad_tokens:
        try:
            code = c.get("/users/me", headers=bearer(bt)).status_code
        except Exception:
            continue  # istemci geçersiz header'ı reddetti → sunucuya ulaşmadı
        if code not in (401, 422, 400):
            a5_ok = False
            print(f"      ! token={bt[:20]!r} → {code}")
    check(a5_ok and c.get("/health").status_code == 200, "A5 bozuk/uzun/null token → 401, uygulama ayakta", "Önemli")

    # A6 anon cookie: HttpOnly+Secure+SameSite + yeterli entropi
    rb = bootstrap(c, **{"X-Forwarded-For": "10.0.0.2"})
    setc = rb.headers.get("set-cookie", "")
    low = setc.lower()
    check("httponly" in low and "secure" in low and "samesite=none" in low,
          f"A6 cookie HttpOnly+Secure+SameSite=None ({setc[:60]}…)", "Önemli")
    # nr_device değeri uzunluğu (entropi proxy'si: token_urlsafe(32) ≈ 43 char)
    val = ""
    for kv in setc.split(";")[0:1]:
        if "=" in kv:
            val = kv.split("=", 1)[1]
    check(len(val) >= 40, f"A6 device_id entropisi yeterli (len={len(val)}, tahmin/brute edilemez)", "Önemli")

    # ---------------------------------------------------------------- #
    section("B. YETKİLENDİRME (IDOR / veri izolasyonu)")

    # alice bir entity ekler
    r = c.post("/entities", headers=bearer(a_tok), json={"name": "AliceCo", "type": "keyword", "query": "aliceco"})
    a_ent = r.json()["id"]

    # B7 IDOR: bob, alice'in entity'sini göremez (dashboard + chat)
    check(c.get(f"/entities/{a_ent}/dashboard", headers=bearer(b_tok)).status_code == 404,
          "B7 IDOR dashboard: bob → alice entity 404", "Kritik")
    rc = c.post("/chat", headers=bearer(b_tok), json={"entity_id": a_ent, "messages": [{"role": "user", "content": "gizli?"}]})
    check(rc.status_code == 404, f"B7 IDOR chat: bob → alice entity 404 (gerçekleşen {rc.status_code})", "Kritik")
    # bob'un listesinde alice'in entity'si görünmemeli
    bob_ids = {e["id"] for e in c.get("/entities", headers=bearer(b_tok)).json()}
    check(a_ent not in bob_ids, "B7 bob'un listesinde alice'in entity'si yok", "Kritik")

    # B8 öneri izolasyonu — Suggestion ekle (alice kaynaklı), bob görmemeli; dismiss kişisel
    with session_scope() as s:
        from app.db.models import Suggestion
        sug = Suggestion(name="SuggCo", ticker=None, is_public=False, norm_key="n:suggco",
                         mention_count=5, source_entity_ids=[a_ent], source_language="en")
        s.add(sug); s.flush(); sug_id = sug.id
    a_sees = any(x["id"] == sug_id for x in c.get("/suggestions", headers=bearer(a_tok)).json())
    b_sees = any(x["id"] == sug_id for x in c.get("/suggestions", headers=bearer(b_tok)).json())
    check(a_sees and not b_sees, "B8 öneri yalnızca kaynak-entity sahibine görünür (bob'a sızmaz)", "Önemli")
    # dismiss KİŞİSEL: alice kapatınca yalnızca alice'ten kaybolur (API üzerinden doğrula —
    # canlı sunucu ayrı thread'de yazdığı için doğrudan DB okuması snapshot yüzünden yanıltıcı).
    dcode = c.post(f"/suggestions/{sug_id}/dismiss", headers=bearer(a_tok)).status_code
    a_after = any(x["id"] == sug_id for x in c.get("/suggestions", headers=bearer(a_tok)).json())
    check(dcode == 204 and not a_after, "B8 dismiss KİŞİSEL — alice kapattı, alice'ten kalktı (204)", "Önemli")

    # B9 watchlist manipülasyonu: body'ye user_id enjekte etmek işe yaramaz
    before = {e["id"] for e in c.get("/entities", headers=bearer(a_tok)).json()}
    c.post("/entities", headers=bearer(b_tok),
           json={"name": "BobCo", "type": "keyword", "query": "bobco", "user_id": a_id})
    after = {e["id"] for e in c.get("/entities", headers=bearer(a_tok)).json()}
    check(before == after, "B9 istekte user_id enjekte → alice'in listesi DEĞİŞMEDİ", "Kritik")

    # B10 admin uçları: normal + anon → 403
    admin_eps = [
        ("GET", "/admin/users"), ("GET", f"/admin/users/{admin_id}"), ("GET", "/admin/stats"),
        ("GET", "/admin/feedback"), ("POST", f"/admin/users/{a_id}/reset-password"),
        ("DELETE", f"/admin/users/{a_id}"),
    ]
    b10 = True
    for tok, who in ((b_tok, "normal"), (anon_tok, "anon")):
        for meth, ep in admin_eps:
            code = c.request(meth, ep, headers=bearer(tok)).status_code
            if code != 403:
                b10 = False
                print(f"      ! {who} {meth} {ep} → {code} (403 bekleniyordu)")
    check(b10, "B10 tüm /admin/* uçları normal+anon için 403", "Kritik")

    # B11 admin kendini silemez
    check(c.delete(f"/admin/users/{admin_id}", headers=bearer(admin_tok)).status_code == 403,
          "B11 admin kendi hesabını silemez (son-admin kilidi)", "Önemli")

    # B12 geri bildirim izolasyonu: normal kullanıcı okuyamaz
    c.post("/feedback", headers=bearer(a_tok), json={"message": "gizli geri bildirim"})
    check(c.get("/admin/feedback", headers=bearer(b_tok)).status_code == 403,
          "B12 normal kullanıcı başkasının geri bildirimini okuyamaz (403)", "Kritik")

    # ---------------------------------------------------------------- #
    section("C. KOTA VE KAYNAK TÜKETİMİ")

    # C13 kota yarış koşulu: anon (limit 3) eşzamanlı 10 farklı ekleme → ≤3
    race_anon = bootstrap(c, **{"X-Forwarded-For": "10.0.0.3"}).json()["token"]
    def add_one(i):
        with C() as cc:
            return cc.post("/entities", headers=bearer(race_anon),
                           json={"name": f"RaceCo{i}", "type": "keyword", "query": f"raceq{i}"}).status_code
    with ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(add_one, range(10)))
    final = len(c.get("/entities", headers=bearer(race_anon)).json())
    check(final <= 3, f"C13 eşzamanlı ekleme kota AŞMADI (liste={final}, limit=3)", "Önemli")

    # C14 anon oturum oluşturma IP hız sınırı (saatte 10) — taze IP ile 12 dene
    codes = [bootstrap(c, **{"X-Forwarded-For": "203.0.113.77"}).status_code for _ in range(12)]
    check(codes.count(429) >= 1 and codes[:10].count(200) >= 8,
          f"C14 anon oturum IP hız sınırı çalışıyor (429 sayısı={codes.count(429)})", "Önemli")

    # C15 rate limit: 6 başarısız /users/login (taze IP) → 429 + DB kalıcılığı
    ipL = "198.51.100.10"
    login_codes = []
    for _ in range(7):
        login_codes.append(c.post("/users/login", headers={"X-Forwarded-For": ipL},
                                  json={"username": "alice", "password": "wrongpass"}).status_code)
    check(429 in login_codes, f"C15 6+ başarısız giriş → 429 (kod dizisi {login_codes})", "Kritik")
    # DB kalıcılığı: TAZE limiter örneği (yeniden başlatma simülasyonu) kilidi görüyor mu
    fresh = LoginRateLimiter()
    check(fresh.locked_seconds(ipL) > 0, "C15 kilit DB-tabanlı (yeniden başlatmada korunur)", "Kritik")
    # Karışık uçlar aynı IP sayacını paylaşıyor mu (taze IP)
    ipM = "198.51.100.20"
    c.post("/auth/login", headers={"X-Forwarded-For": ipM}, json={"password": "x"})
    c.post("/auth/login", headers={"X-Forwarded-For": ipM}, json={"password": "x"})
    for _ in range(4):
        c.post("/users/login", headers={"X-Forwarded-For": ipM}, json={"username": "nouser", "password": "x"})
    mixed = c.post("/users/login", headers={"X-Forwarded-For": ipM}, json={"username": "nouser", "password": "x"}).status_code
    check(mixed == 429, f"C15 karışık uçlar (auth+users/login) aynı IP sayacını paylaşır ({mixed})", "Önemli")

    # C16 XFF spoofing: her istekte farklı sahte IP → tek hesaba 20 deneme kilitleniyor mu?
    spoof_codes = []
    for i in range(20):
        spoof_codes.append(c.post("/users/login", headers={"X-Forwarded-For": f"7.7.{i}.{i}"},
                                  json={"username": "bob", "password": "wrongpass"}).status_code)
    check(429 in spoof_codes,
          f"C16 XFF spoof ile hesap brute-force ENGELLENDİ (hesap-bazlı kilit; 429 var={429 in spoof_codes})",
          "Kritik")

    # C16b (yalnızca caddy modu) Caddy'yi ATLAYAN istek: bağlantı güvenilen proxy'den değil →
    # sahte XFF yok sayılır, hız sınırı GERÇEK bağlantı adresini sayar (her istekte farklı
    # sahte IP yollamak kilidi atlatmaz). Ayrı sunucu: forwarded_allow_ips Caddy'nin IP'si,
    # test istemcisi (127.0.0.1) değil.
    if get_settings().trusted_proxy == "caddy":
        srv2 = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT + 1, log_level="warning",
                                             log_config=None, server_header=False,
                                             proxy_headers=True, forwarded_allow_ips="172.28.0.10"))
        threading.Thread(target=srv2.run, daemon=True).start()
        for _ in range(100):
            if srv2.started:
                break
            time.sleep(0.05)
        with httpx.Client(base_url=f"http://127.0.0.1:{PORT + 1}", timeout=30) as c2:
            direct = [c2.post("/users/login", headers={"X-Forwarded-For": f"9.9.{i}.{i}"},
                              json={"username": "nouser2", "password": "x"}).status_code for i in range(7)]
        peer_locked = LoginRateLimiter().locked_seconds("127.0.0.1") > 0
        spoof_seen = any(LoginRateLimiter().locked_seconds(f"9.9.{i}.{i}") > 0 for i in range(7))
        check(429 in direct and peer_locked and not spoof_seen,
              f"C16b caddy: güvenilmeyen bağlantının sahte XFF'i yok sayıldı, kilit gerçek IP'de ({direct})",
              "Kritik")
        login_limiter.record_success("127.0.0.1")  # sonraki testler aynı adresten gelir
        srv2.should_exit = True

    # C17 büyük girdi (DoS) → 422, çökme yok
    big_name = "x" * (10 * 1024 * 1024)
    r1 = c.post("/entities", headers=bearer(b_tok), json={"name": big_name, "type": "keyword", "query": "y"})
    r2 = c.post("/feedback", headers=bearer(b_tok), json={"message": "z" * (1024 * 1024)})
    r3 = c.get("/symbol-search", params={"q": "s" * 5000}, headers=bearer(b_tok))
    check(r1.status_code == 422 and r2.status_code == 422 and r3.status_code == 422 and c.get("/health").status_code == 200,
          f"C17 aşırı büyük girdi → 422 ({r1.status_code}/{r2.status_code}/{r3.status_code}), uygulama ayakta", "Önemli")

    # C18 pahalı işlem tekrarı: 50 art arda /refresh → 5xx yok; gerçekten BAŞLAYAN tarama
    # sayısı sınırlı (kişi kotası 3 + tek-tarama koruması). started=False no-op'lar zararsız.
    resp18 = [c.post("/refresh", headers=bearer(a_tok)) for _ in range(50)]
    no5xx = all(r.status_code < 500 for r in resp18)
    started_cnt = sum(1 for r in resp18 if r.status_code == 200 and r.json().get("started"))
    check(no5xx and started_cnt <= 3,
          f"C18 50 yenileme → 5xx yok, gerçek tarama başlatma ≤ kota ({started_cnt} started, quota=3)",
          "Önemli")

    # ---------------------------------------------------------------- #
    section("D. GİRDİ VE ENJEKSİYON")

    # D19 SQL enjeksiyonu — literal saklanır, tablo bozulmaz
    check(register(c, "' OR 1=1--", "password1").status_code == 422, "D19 SQLi kullanıcı adı regex ile 422", "Önemli")
    inj = c.post("/entities", headers=bearer(b_tok),
                 json={"name": "'; DROP TABLE users;--", "type": "keyword", "query": "injq1"})
    c.post("/feedback", headers=bearer(b_tok), json={"message": "Robert'); DROP TABLE feedback;--"})
    with session_scope() as s:
        users_ok = s.query(User).count() > 0
        from app.db.models import Entity as _E, Feedback as _F
        ents_ok = s.query(_E).count() > 0
        fb_ok = s.query(_F).count() > 0
    check(inj.status_code in (201, 409) and users_ok and ents_ok and fb_ok,
          "D19 SQLi yükleri literal saklandı; users/entities/feedback tabloları sağlam", "Kritik")

    # D20 XSS — backend ham saklar; frontend React ESCAPE eder + dangerouslySetInnerHTML YOK
    xss = "<script>alert(1)</script>"
    c.post("/feedback", headers=bearer(a_tok), json={"message": xss})
    fb = c.get("/admin/feedback", headers=bearer(admin_tok)).json()
    stored_verbatim = any(f["message"] == xss for f in fb)
    grep = subprocess.run(["grep", "-rn", "dangerouslySetInnerHTML", "../frontend/src"],
                          capture_output=True, text=True)
    no_raw_html = grep.returncode != 0  # eşleşme yok = güvenli
    check(stored_verbatim and no_raw_html,
          "D20 XSS yükü ham saklanır; frontend'de dangerouslySetInnerHTML YOK (React escape eder)", "Kritik")

    # D21 path traversal — int path param + dosya erişimi yok
    p1 = c.get("/entities/..%2f..%2fetc%2fpasswd/dashboard", headers=bearer(a_tok)).status_code
    p2 = c.get("/symbol-search", params={"q": "../../../../etc/passwd"}, headers=bearer(a_tok))
    leaked = "root:" in p2.text
    check(p1 in (404, 422) and p2.status_code == 200 and not leaked,
          f"D21 path traversal engellendi (dashboard {p1}, dosya sızıntısı={leaked})", "Önemli")

    # D22 JSON/şema — yanlış tip, aşırı liste, bozuk gövde → 422/400, çökme yok
    j1 = c.post("/entities", headers=bearer(b_tok), json={"name": {"x": 1}, "type": "keyword", "query": "q"}).status_code
    j2 = c.post("/chat", headers=bearer(a_tok), json={"entity_id": a_ent, "messages": [{"role": "user", "content": "hi"}] * 100}).status_code
    j3 = c.post("/entities", headers={**bearer(b_tok), "Content-Type": "application/json"}, content=b"{not valid json")
    check(j1 == 422 and j2 == 422 and j3.status_code in (400, 422) and c.get("/health").status_code == 200,
          f"D22 kötü şema/tip/gövde → 422/400 ({j1}/{j2}/{j3.status_code}), çökme yok", "Önemli")

    # D23 unicode/homoglyph — admın (ASCII dışı) reddedilir → admin ile çakışma yok
    u1 = register(c, "admın", "password1").status_code  # dotless i
    u2 = c.post("/entities", headers=bearer(b_tok), json={"name": "📈 Emoji RTL ‮ test", "type": "keyword", "query": "emojiq"}).status_code
    check(u1 == 422 and u2 in (201, 409) and c.get("/health").status_code == 200,
          f"D23 homoglyph kullanıcı adı reddedildi ({u1}); emoji/RTL güvenle işlendi ({u2})", "Önemli")

    # ---------------------------------------------------------------- #
    section("E. SIR SIZINTISI")

    # E24 log taraması — akış çalıştır, sırları ara
    c.post("/users/login", json={"username": "alice", "password": "alicepass1"})
    c.post("/feedback", headers=bearer(a_tok), json={"message": "log testi", "contact": "x@y.z"})
    joined = "\n".join(LOGS)
    secrets_found = [s for s in ("alicepass1", "adminpass1", "bobpass1234", get_settings().app_secret, "sharedpw123")
                     if s in joined]
    check(not secrets_found, f"E24 loglarda şifre/sır YOK (bulunan: {secrets_found})", "Kritik")

    # E25 hata mesajları — stack trace / dosya yolu / SQL sızmaz
    err = c.post("/entities", headers={**bearer(b_tok), "Content-Type": "application/json"}, content=b"{bad")
    body = err.text.lower()
    leaky = any(x in body for x in ("traceback", "/users/", "sqlalchemy", 'file "', "site-packages"))
    check(not leaky, "E25 hata yanıtında stack trace/dosya yolu/SQL YOK", "Önemli")

    # E26 header'lar — güvenlik header'ları var; Server versiyonu sızmıyor
    h = c.get("/health").headers
    sec_ok = (h.get("x-content-type-options") == "nosniff" and h.get("referrer-policy") == "no-referrer"
              and h.get("x-frame-options") == "DENY" and "max-age" in (h.get("strict-transport-security") or "")
              and "default-src" in (h.get("content-security-policy") or ""))
    server_hdr = (h.get("server") or "").lower()
    check(sec_ok, "E26 güvenlik header'ları (CSP/HSTS/nosniff/frame/referrer) dönüyor", "Önemli")
    check("uvicorn" not in server_hdr and "x-powered-by" not in {k.lower() for k in h.keys()},
          f"E26 Server/X-Powered-By versiyon sızdırmıyor (server={server_hdr!r})", "İyileştirme")

    # E27 git geçmişi — gerçek anahtar / izlenmiş .env yok. Adında FAKE geçen eşleşmeler
    # test yer tutucusudur (ör. eski bir fixture'daki sk-ant-api03-FAKE…), gerçek anahtar değil.
    env_tracked = subprocess.run(["git", "-C", "..", "log", "--all", "--oneline", "--", "backend/.env", ".env"],
                                 capture_output=True, text=True).stdout.strip()
    keyshapes = subprocess.run("git -C .. log --all -p | grep -oE '(sk-ant-[A-Za-z0-9_-]{20,}|nvapi-[A-Za-z0-9_-]{20,}|sk-or-v1-[A-Za-z0-9_-]{20,})' | grep -v FAKE | sort -u",
                               shell=True, capture_output=True, text=True).stdout.strip()
    check(not env_tracked and not keyshapes,
          f"E27 git geçmişinde izlenmiş .env / gerçek anahtar YOK (env='{env_tracked[:30]}', key='{keyshapes[:30]}')",
          "Kritik")

    # ---------------------------------------------------------------- #
    section("F. İŞ MANTIĞI")

    # F28 negatif/aşırı limit → 422
    n1 = c.get(f"/entities/{a_ent}/dashboard", params={"limit": -1}, headers=bearer(a_tok)).status_code
    n2 = c.get(f"/entities/{a_ent}/dashboard", params={"limit": 0}, headers=bearer(a_tok)).status_code
    n3 = c.get(f"/entities/{a_ent}/dashboard", params={"limit": 999999}, headers=bearer(a_tok)).status_code
    check(n1 == 422 and n2 == 422 and n3 == 422, f"F28 negatif/0/aşırı limit → 422 ({n1}/{n2}/{n3})", "Önemli")

    # F29 sıra manipülasyonu
    d1 = c.delete("/entities/999999", headers=bearer(a_tok)).status_code            # olmayan
    c.post("/entities", headers=bearer(a_tok), json={"name": "DupCo", "type": "keyword", "query": "dupq"})
    d2 = c.post("/entities", headers=bearer(a_tok), json={"name": "DupCo", "type": "keyword", "query": "dupq"}).status_code  # tekrar
    # silinmiş kullanıcının token'ı
    r = register(c, "todelete", "delpass123"); del_tok = r.json()["token"]; del_id = r.json()["user"]["id"]
    c.delete(f"/admin/users/{del_id}", headers=bearer(admin_tok))
    d3 = c.get("/users/me", headers=bearer(del_tok)).status_code
    check(d1 == 404 and d2 == 409 and d3 == 401,
          f"F29 olmayan silme 404, çift ekleme 409, silinmiş kullanıcı token 401 ({d1}/{d2}/{d3})", "Önemli")

    # F30 CORS — evil origin reddedilir; * + credentials yok
    ev = c.get("/health", headers={"Origin": "https://evil.com"})
    acao = ev.headers.get("access-control-allow-origin")
    ok_origin = c.get("/health", headers={"Origin": "http://localhost:5173"}).headers.get("access-control-allow-origin")
    creds = ev.headers.get("access-control-allow-credentials")
    not_star_with_creds = not (acao == "*" and creds == "true")
    check(acao != "https://evil.com" and not_star_with_creds,
          f"F30 evil origin CORS reddi (ACAO={acao!r}, izinli localhost={ok_origin!r})", "Önemli")

    c.close()


def summarize():
    section("SONUÇ ÖZETİ")
    by_sev = {"Kritik": [0, 0], "Önemli": [0, 0], "İyileştirme": [0, 0]}
    for name, passed, sev in RESULTS:
        by_sev.setdefault(sev, [0, 0])
        by_sev[sev][0 if passed else 1] += 1
    total = len(RESULTS)
    passed = sum(1 for _, p, _ in RESULTS if p)
    print(f"Toplam: {passed}/{total} test geçti\n")
    for sev in ("Kritik", "Önemli", "İyileştirme"):
        p, f = by_sev.get(sev, [0, 0])
        print(f"  {sev:12} → {p} geçti, {f} BAŞARISIZ")
    blockers = [n for n, p, s in RESULTS if not p and s in ("Kritik", "Önemli")]
    print()
    if blockers:
        print("❌ SİTE HAZIR DEĞİL — bloklayıcı bulgular:")
        for b in blockers:
            print(f"   • {b}")
    else:
        improvements = [n for n, p, s in RESULTS if not p]
        print("✅ Bloklayıcı (Kritik/Önemli) bulgu yok — site herkese açılmaya hazır.")
        if improvements:
            print("   (İyileştirme önerileri kaldı: " + "; ".join(improvements) + ")")
    return not blockers


def main():
    # server_header=False → üretimdeki --no-server-header ile aynı (Server sızıntısı yok).
    # proxy_headers + forwarded_allow_ips: üretimdeki uvicorn bayraklarıyla aynı. Test istemcisi
    # (127.0.0.1) burada GÜVENİLEN PROXY rolünde (render: Render kenarı, caddy: Caddy) →
    # X-Forwarded-For ile istemci IP'si simüle edilir.
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning",
                            log_config=None, server_header=False,
                            proxy_headers=True, forwarded_allow_ips="127.0.0.1")
    server = uvicorn.Server(config)
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(150):
        try:
            if httpx.get(BASE + "/health", timeout=1).status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.1)
    else:
        raise RuntimeError("Sunucu başlamadı")
    try:
        run_tests()
    finally:
        ok = summarize()
        server.should_exit = True
        time.sleep(0.3)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
