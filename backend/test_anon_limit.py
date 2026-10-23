"""NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR gerçekten okunuyor mu (izole temp DB, gerçek /session/bootstrap).

Önceden sınırlayıcı kodda 10'a sabitti; ayar hiçbir yerde okunmuyordu.
Doğrular:
  (A) ayar = 3 → aynı IP'den 3 yeni anon oturum açılır, 4. istek 429
  (B) başka IP bu sayaçtan etkilenmez
  (C) ayar yoksa varsayılan 10 (davranış değişmedi): 10 açılır, 11. istek 429
  (D) 0 = sınırsız
Çalıştır: python test_anon_limit.py
"""
import os
import tempfile

_db = os.path.join(tempfile.gettempdir(), "nr_test_anon_limit.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y" * 20, NEWSRADAR_SCHEDULER="off",
                  NEWSRADAR_SEED_ON_START="off", NEWSRADAR_MAX_USERS="0", NEWSRADAR_TRUSTED_PROXY="render",
                  NEWSRADAR_COOKIE_SECURE="off", NEWSRADAR_COOKIE_SAMESITE="lax",
                  NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR="3")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.session import anon_create_limiter  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


def bootstrap_codes(c, n, ip):
    codes = []
    for _ in range(n):
        c.cookies.clear()  # çerez varsa aynı cihaza döner, yeni oturum açılmaz
        codes.append(c.post("/session/bootstrap", headers={"X-Forwarded-For": ip}).status_code)
    return codes


def reset(value):
    if value is None:
        os.environ.pop("NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR", None)
    else:
        os.environ["NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR"] = str(value)
    get_settings.cache_clear()
    anon_create_limiter._hits.clear()


with TestClient(app) as c:
    print("== A: ayar = 3")
    codes = bootstrap_codes(c, 4, "198.51.100.1")
    check(codes == [200, 200, 200, 429], f"3 oturum açıldı, 4. istek 429 ({codes})")
    check(anon_create_limiter.per_hour == 3, f"sınırlayıcı ayarı okuyor (per_hour={anon_create_limiter.per_hour})")

    print("== B: başka IP")
    check(bootstrap_codes(c, 1, "198.51.100.2") == [200], "farklı IP etkilenmedi")

    print("== C: ayar yok → varsayılan 10")
    reset(None)
    codes = bootstrap_codes(c, 11, "198.51.100.3")
    check(codes[:10] == [200] * 10 and codes[10] == 429, f"10 açıldı, 11. istek 429 ({codes.count(200)}×200, son {codes[-1]})")
    check(anon_create_limiter.per_hour == 10, "varsayılan 10")

    print("== D: 0 = sınırsız")
    reset(0)
    codes = bootstrap_codes(c, 15, "198.51.100.4")
    check(set(codes) == {200}, f"15 istek, hepsi 200 ({set(codes)})")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
