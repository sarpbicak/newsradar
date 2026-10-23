"""/status yenileme hakkı alanları — sayılar KODDAN değil ayarlardan gelir (izole temp DB).

Doğrular:
  (A) refresh_limit_anon / refresh_limit_registered = NEWSRADAR_MAX_REFRESH_ANON / _REGISTERED
  (B) misafirin kendi limiti anon ayarı; hak dolmadan refresh_resets_at yok
  (C) hak dolunca refresh_resets_at = penceredeki en eski yenileme + 24 saat
  (D) admin: limit 0 (sınırsız), refresh_is_admin, resets_at yok
  (E) POST /refresh onayı: liste boşsa reason="empty"; başlayınca /status HEMEN is_running=true
      (onay ile durum arasında boşluk yok); aynı kullanıcı tekrar → reason="running" (izle);
      başka kullanıcı → reason="busy" (sessiz kalmaz)
Çalıştır: python test_refresh_status.py
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_refresh_status.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="genelsifre", APP_SECRET="rs-secret-1234567890",
    ADMIN_USERNAME="rootadmin", NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_MAX_USERS="0", NEWSRADAR_TRUSTED_PROXY="render", NEWSRADAR_COOKIE_SECURE="off",
    NEWSRADAR_COOKIE_SAMESITE="lax",
    # Varsayılanlardan (1 / 3) farklı sayılar: değerin ayardan okunduğunu gösterir.
    NEWSRADAR_MAX_REFRESH_ANON="2", NEWSRADAR_MAX_REFRESH_REGISTERED="7",
)

import threading  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import app.refresh as refresh_mod  # noqa: E402
from app.api.main import app  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import UsageEvent  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


def parse(ts):
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


with TestClient(app) as c:
    # İlk kayıt = admin.
    gt = c.post("/auth/login", json={"password": "genelsifre"}).json()["token"]
    adm = c.post("/users/register", json={"username": "rootadmin", "password": "parola12345"},
                 headers={"Authorization": f"Bearer {gt}"}).json()["token"]
    c.cookies.clear()
    anon = c.post("/session/bootstrap", headers={"X-Forwarded-For": "198.51.100.7"}).json()
    AH = {"Authorization": f"Bearer {anon['token']}"}
    uid = c.get("/users/me", headers=AH).json()["id"]

    print("== A/B: ayardaki sayılar, hak dolmadan")
    st = c.get("/status", headers=AH).json()
    check(st["refresh_limit_anon"] == 2 and st["refresh_limit_registered"] == 7,
          f"ayarlar: anon={st['refresh_limit_anon']}, kayıtlı={st['refresh_limit_registered']}")
    check(st["refresh_limit"] == 2 and st["refresh_used"] == 0 and not st["refresh_is_admin"], "misafirin limiti anon ayarı")
    check(st["refresh_resets_at"] is None, "hak dolmadan resets_at yok")

    print("== C: hak dolunca dönüş zamanı = en eski yenileme + 24 saat")
    now = datetime.now(timezone.utc)
    oldest = now - timedelta(hours=5)
    with SessionLocal() as db:
        db.add(UsageEvent(user_id=uid, event_type="refresh", detail={}, created_at=oldest))
        db.add(UsageEvent(user_id=uid, event_type="refresh", detail={}, created_at=now - timedelta(hours=1)))
        db.commit()
    st = c.get("/status", headers=AH).json()
    check(st["refresh_used"] == 2, f"kullanılan 2 ({st['refresh_used']})")
    got = parse(st["refresh_resets_at"]) if st["refresh_resets_at"] else None
    check(got is not None and abs((got - (oldest + timedelta(hours=24))).total_seconds()) < 2,
          f"resets_at ≈ en eski + 24s ({got})")

    print("== D: admin")
    st = c.get("/status", headers={"Authorization": f"Bearer {adm}"}).json()
    check(st["refresh_is_admin"] and st["refresh_limit"] == 0 and st["refresh_resets_at"] is None, "admin sınırsız, resets_at yok")

    print("== E: yenileme onayı ve durum tutarlılığı")
    # Taramayı fiyat adımında beklet (anahtarsız tarama yoksa milisaniyede biter).
    gate = threading.Event()
    orig_prices = refresh_mod.refresh_prices
    refresh_mod.refresh_prices = lambda ids: (gate.wait(10), [])[1]
    try:
        c.cookies.clear()
        a2 = c.post("/session/bootstrap", headers={"X-Forwarded-For": "198.51.100.8"}).json()
        A2 = {"Authorization": f"Bearer {a2['token']}"}
        ack = c.post("/refresh", headers=A2).json()
        check(ack["started"] is False and ack["reason"] == "empty" and ack["is_running"] is False, f"boş liste → empty ({ack})")
        r = c.post("/entities", headers=A2, json={"name": "Tesla", "type": "ticker", "query": "TSLA", "language": "en"})
        check(r.status_code in (200, 201), f"şirket eklendi ({r.status_code})")
        ack = c.post("/refresh", headers=A2).json()
        check(ack["started"] is True and ack["reason"] is None, f"başladı ({ack})")
        st = c.get("/status", headers=A2).json()
        check(st["is_running"] is True, "onaydan hemen sonra /status is_running=true")
        ack = c.post("/refresh", headers=A2).json()
        check(ack["started"] is False and ack["reason"] == "running" and ack["is_running"] is True, f"kendi taraması sürüyor → running ({ack})")
        ack = c.post("/refresh", headers={"Authorization": f"Bearer {adm}"}).json()
        check(ack["started"] is False and ack["reason"] in ("busy", "empty"), f"başka kullanıcı: sessiz değil ({ack})")
        c.post("/entities", headers={"Authorization": f"Bearer {adm}"}, json={"name": "Tesla", "type": "ticker", "query": "TSLA", "language": "en"})
        ack = c.post("/refresh", headers={"Authorization": f"Bearer {adm}"}).json()
        check(ack["started"] is False and ack["reason"] == "busy" and ack["is_running"] is False, f"başka kullanıcının taraması → busy ({ack})")
    finally:
        gate.set()
        refresh_mod.refresh_prices = orig_prices
    for _ in range(100):
        if not refresh_mod.is_running():
            break
        threading.Event().wait(0.05)
    st = c.get("/status", headers=A2).json()
    check(st["is_running"] is False and st["last_completed_at"], "tarama bitti, bitiş zamanı görünür")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
