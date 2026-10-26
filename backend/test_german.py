"""Almanca (DE) desteği — sahte çıktı, gerçek API yok, izole temp DB.

Doğrular:
  (A) dil kodu: "de" kaydedilir (POST /users/me/language), geçersiz → tr; ?lang=de içerik dili
  (B) çeviri istemi DE: Almanca, du hitabı, yasaklı ifadeler; kalite kuralları (yasaklı ifade,
      dil sızıntısı, emniyet tavanı) DE için de çalışır
  (C) sohbet: DE kullanıcıda çıktı dili direktifi Almanca
  (D) e-posta: DE kullanıcıya Almanca doğrulama/sıfırlama e-postası; backend kopyası
      (app/locales/email.de.json) frontend/src/locales/de.json'daki email.* anahtarlarıyla aynı
  (E) kodlu hatalar: {"detail", "code", "params"} (metin frontend'de, kullanıcının dilinde)
  (F) borsa ülkesi DE'de Almanca
Çalıştır: python test_german.py
"""
import json
import os
import re
import tempfile
from pathlib import Path

_db = os.path.join(tempfile.gettempdir(), "nr_test_german.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ["NEWSRADAR_ENABLE_DE"] = "on"  # Almanca bayrağı açıkken (DE testleri)
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="genelsifre", APP_SECRET="de-secret-1234567890",
    ADMIN_USERNAME="rootadmin", NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_MAX_USERS="0", NEWSRADAR_TRUSTED_PROXY="render", NEWSRADAR_COOKIE_SECURE="off",
    NEWSRADAR_COOKIE_SAMESITE="lax", NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR="0",
    EMAIL_BACKEND="console", NEWSRADAR_PUBLIC_URL="https://newsradar.example",
)

from fastapi.testclient import TestClient  # noqa: E402

from app.analysis.prompts import build_translation_prompt, output_language_directive  # noqa: E402
from app.analysis.schemas import sanitize_translation  # noqa: E402
from app.analysis.text_quality import banned_phrase_hits, hard_cap, language_leak_hits  # noqa: E402
from app.api.main import app  # noqa: E402
from app.api.serializers import content_language  # noqa: E402
from app.email_templates import render  # noqa: E402
from app.languages import language_from_accept, normalize_language  # noqa: E402
from app.locales import email_de  # noqa: E402
from app.locales.sync import FRONTEND_DE, email_keys  # noqa: E402
from app.mailer import get_mailer  # noqa: E402
from app.markets import market_of  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


_ip = [0]


def xff():
    _ip[0] += 1
    return {"X-Forwarded-For": f"198.51.100.{_ip[0]}"}


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


print("== A: dil kodu ==")
check(normalize_language("DE") == "de" and normalize_language("fr") == "tr" and normalize_language(None) == "tr",
      "normalize: de geçerli, bilinmeyen → tr")
check(content_language(type("U", (), {"language": "tr"})(), "de") == "de", "?lang=de içerik dilini belirler")
check([language_from_accept(h) for h in ("de-DE,de;q=0.9", "tr-TR", "fr-FR", "", None)] == ["de", "tr", "en", "en", "en"],
      "Accept-Language: de → de, tr → tr, diğerleri → en")

with TestClient(app) as c:
    c.post("/users/register", json={"username": "rootadmin", "password": "parola12345", "email": "r@example.com"},
           headers=xff())
    r = c.post("/users/register", json={"username": "jonas", "password": "parola12345", "email": "j1@example.com"},
               headers=xff())
    tok = r.json()["token"]
    r = c.post("/session/bootstrap", headers={**xff(), "Accept-Language": "de-DE,de;q=0.9"})
    check(r.status_code == 200 and r.json()["user"]["language"] == "de", "anonim oturum: de tarayıcı → de")
    me = c.post("/users/me/language", json={"language": "de"}, headers=auth(tok)).json()
    check(me["language"] == "de", f"POST /users/me/language de kaydedildi ({me['language']})")
    check(c.get("/users/me", headers=auth(tok)).json()["language"] == "de", "GET /users/me: de")

    print("== D: e-posta ==")
    get_mailer().sent.clear()
    c.post("/users/me/email", json={"email": "jonas@example.com"}, headers=auth(tok))
    sent = get_mailer().sent
    check(bool(sent) and sent[-1].subject == "NewsRadar: Bestätige deine E-Mail-Adresse",
          f"doğrulama e-postası Almanca ({sent[-1].subject if sent else '-'})")
    check(bool(sent) and "Hallo jonas," in sent[-1].text and 'lang="de"' in sent[-1].html
          and "Wir verschicken keine Werbe-E-Mails." in sent[-1].text, "selam, alt not ve html lang=de")
    get_mailer().sent.clear()
    c.post("/users/forgot-password", json={"email": "jonas@example.com"}, headers=xff())
    sent = get_mailer().sent
    check(bool(sent) and sent[-1].subject == "NewsRadar: Passwort zurücksetzen", "sıfırlama e-postası Almanca")

    print("== E: kodlu hatalar ==")
    r = c.post("/users/login", json={"username": "jonas", "password": "yanlis-sifre"}, headers=xff())
    body = r.json()
    check(r.status_code == 401 and body.get("code") == "login_invalid" and body.get("detail"),
          f"giriş hatası: code + detail ({body})")
    r = c.post("/users/register", json={"username": "kurz", "password": "abc", "email": "k@example.com"}, headers=xff())
    body = r.json()
    check(r.status_code == 422 and body.get("code") == "password_short" and body.get("params", {}).get("n") == 8,
          f"kısa şifre: code + params.n ({body})")
    r = c.get("/entities/999999/dashboard", headers=auth(tok))
    check(r.status_code == 404 and r.json().get("code") == "entity_not_found", "bulunamadı: entity_not_found")
    r = c.post("/users/register", json={"username": "jonas", "password": "parola12345", "email": "j1@example.com"},
               headers=xff())
    check(r.status_code == 409 and r.json().get("code") == "username_taken", "alınmış kullanıcı adı: username_taken")

print("== D2: e-posta metinleri tek kaynakla aynı ==")
subject, text, html = render("reset", "de", "<b>x</b>", "https://e/x")
check(subject == email_de()["email.reset.subject"] and "&lt;b&gt;x&lt;/b&gt;" in html, "render DE + kaçış")
check(render("verify", "xx", "a", "l")[0] == "NewsRadar: e-posta adresini doğrula", "bilinmeyen dil → tr")
if FRONTEND_DE.exists():
    check(email_keys() == email_de(),
          "app/locales/email.de.json = frontend de.json email.* (değiştiyse: python -m app.locales.sync)")
else:
    check(False, f"tek kaynak dosya yok: {FRONTEND_DE}")
check(not any("—" in v for v in email_de().values()), "Almanca e-posta metinlerinde uzun tire yok")

print("== B: çeviri istemi + kalite kuralları ==")
p = build_translation_prompt({"headline_verdict": "Deliveries fell 8%."}, "de")
check("plain German" in p and "'du'" in p and "überwiegend" in p and "Deliveries fell 8%." in p,
      "DE istemi: Almanca, du, yasaklı ifadeler, kaynak metin")
check(banned_phrase_hits("Die Lage ist überwiegend positiv.", "de") == ["überwiegend positiv"],
      "DE yasaklı ifade yakalandı")
check(banned_phrase_hits("Die Auslieferungen sanken um 8 Prozent.", "de") == [], "temiz DE metin")
check(language_leak_hits("Der Markt hat already reagiert.", "de") == ["already"]
      and language_leak_hits("Die Aktie ist still gefallen, also bleibt Vorsicht.", "de") == [],
      "DE dil sızıntısı: İngilizce işlev kelimesi yakalanır, 'still'/'also' Almanca sayılır")
check(language_leak_hits("Der Umsatz düştü stark.", "de") == ["düştü"], "DE metinde Türkçe kelime yakalanır")
check(hard_cap("headline_verdict", "de") == 28, "DE emniyet tavanı")
src = {"headline_verdict": "A.", "top_drivers": ["B.", "C."]}
ok = sanitize_translation({"headline_verdict": "Satz.", "top_drivers": ["Eins.", "Zwei."]}, src, "de")
bad = sanitize_translation({"headline_verdict": "Satz.", "top_drivers": ["Eins."]}, src, "de")
check(ok == {"headline_verdict": "Satz.", "top_drivers": ["Eins.", "Zwei."]} and bad is None,
      "DE çeviri doğrulama (madde sayısı)")
pc = sanitize_translation({"headline_verdict": "Umsatz plus 40% und minus 8 %.", "top_drivers": ["Eins.", "Zwei."]}, src, "de")
check(pc["headline_verdict"] == "Umsatz plus 40\u00a0% und minus 8\u00a0%.", "DE: sayı ile % arasında bölünmez boşluk")

print("== C: sohbet dili ==")
d = output_language_directive("de")
check("ALMANCA" in d and "'du'" in d and "İngilizce" in d, "DE direktifi: Almanca, du, karışık dil yok")
check(output_language_directive("en") != d and output_language_directive("tr") != d, "TR/EN direktifleri ayrı")

print("== F: borsa ülkesi ==")
m = market_of("SAP.DE")
check(m.country("de") == "Deutschland" and m.country("en") == "Germany" and m.country("tr") == "Almanya",
      "SAP.DE ülkesi üç dilde")
check(market_of("AAPL").country("de") == "USA" and market_of("THYAO.IS").country("de") == "Türkei", "ABD / Türkei")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
