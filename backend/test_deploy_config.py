"""Deploy profilleri: cihaz cookie'si + CORS + güvenilen proxy ayarları (env'den).

Doğrular:
  (A) AWS profili (uygulama bu env ile açılır): cookie Domain=.newsradarapp.com, SameSite=Lax,
      Secure, HttpOnly; CORS apex + www'ye credentials ile izin verir, başka origin'e vermez
  (B) Render profili (varsayılanlar): Domain YOK (host-only), SameSite=None, Secure — canlı
      sitenin davranışı değişmedi; FRONTEND_URL hâlâ CORS'a girer
  (C) hatalı değerler açılışta reddedilir (SameSite, None+Secure-off, TRUSTED_PROXY)
Çalıştır: python test_deploy_config.py
"""
import os
import tempfile

_db = os.path.join(tempfile.gettempdir(), "nr_test_deploy.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
AWS = dict(
    NEWSRADAR_COOKIE_SAMESITE="lax", NEWSRADAR_COOKIE_SECURE="on",
    NEWSRADAR_COOKIE_DOMAIN=".newsradarapp.com", NEWSRADAR_TRUSTED_PROXY="caddy",
    NEWSRADAR_CORS_ORIGINS="https://newsradarapp.com, https://www.newsradarapp.com/",
)
os.environ.update(NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y" * 20,
                  NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
                  NEWSRADAR_LLM_PROVIDER="anthropic", **AWS)
os.environ.pop("FRONTEND_URL", None)

from fastapi import Response  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402
from app.api.routes_session import _set_device_cookie  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


def with_env(overrides: dict, drop=()):
    """Geçici env ile taze Settings (lru_cache'e dokunmadan)."""
    saved = {k: os.environ.get(k) for k in (*overrides, *drop)}
    try:
        for k in drop:
            os.environ.pop(k, None)
        os.environ.update(overrides)
        return Settings()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def preflight(c, origin):
    return c.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})


print("== A: AWS profili ==")
with TestClient(app, base_url="https://api.newsradarapp.com") as c:
    setc = c.post("/session/bootstrap").headers.get("set-cookie", "")
    low = setc.lower()
    check("domain=.newsradarapp.com" in low, f"cookie Domain=.newsradarapp.com ({setc[setc.find(';'):][:90]}…)")
    check("samesite=lax" in low and "; secure" in low and "httponly" in low, "cookie SameSite=Lax + Secure + HttpOnly")
    for origin in ("https://newsradarapp.com", "https://www.newsradarapp.com"):
        r = preflight(c, origin)
        check(r.status_code == 200 and r.headers.get("access-control-allow-origin") == origin
              and r.headers.get("access-control-allow-credentials") == "true",
              f"CORS izinli (credentials): {origin}")
    r = preflight(c, "https://evil.example")
    check("access-control-allow-origin" not in r.headers, f"CORS izinsiz origin reddedildi ({r.status_code})")
    check(get_settings().cors_origins.count("https://www.newsradarapp.com") == 1,
          "sondaki '/' kırpıldı, tekrar yok")

print("== B: Render profili (varsayılanlar) ==")
render = with_env({"FRONTEND_URL": "https://newsradar-web.onrender.com"},
                  drop=("NEWSRADAR_COOKIE_SAMESITE", "NEWSRADAR_COOKIE_SECURE", "NEWSRADAR_COOKIE_DOMAIN",
                        "NEWSRADAR_TRUSTED_PROXY", "NEWSRADAR_CORS_ORIGINS"))
check(render.cookie_samesite == "none" and render.cookie_secure and render.cookie_domain is None
      and render.trusted_proxy == "render", "varsayılan: SameSite=None, Secure, Domain yok, proxy=render")
check("https://newsradar-web.onrender.com" in render.cors_origins, "FRONTEND_URL CORS'a girer (eski ad)")
get_settings.cache_clear()
saved = {k: os.environ.pop(k) for k in AWS}
try:
    resp = Response()
    _set_device_cookie(resp, "dev123")
    setc = resp.headers.get("set-cookie", "").lower()
    check("domain=" not in setc and "samesite=none" in setc and "; secure" in setc,
          f"Render cookie değişmedi (host-only, None+Secure): {setc}")
finally:
    os.environ.update(saved)
    get_settings.cache_clear()

print("== C: hatalı değerler ==")
for env, why in (({"NEWSRADAR_COOKIE_SAMESITE": "relaxed"}, "SameSite geçersiz"),
                 ({"NEWSRADAR_COOKIE_SAMESITE": "none", "NEWSRADAR_COOKIE_SECURE": "off"}, "None + Secure=off"),
                 ({"NEWSRADAR_TRUSTED_PROXY": "nginx"}, "TRUSTED_PROXY geçersiz")):
    try:
        with_env(env)
        check(False, f"{why} reddedilmedi")
    except ValueError as e:
        check(True, f"{why} → ValueError ({e})")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
