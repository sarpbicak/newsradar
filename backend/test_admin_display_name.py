"""Admin: şirketin görünen adını düzenleme (izole temp DB, anahtarsız).

Doğrular:
  (A) GET /admin/entities: id, ham ad, görünen ad, otomatik ad, takipçi; yalnızca admin
  (B) PATCH .../display-name: yalnızca display_name değişir (ham ad / sembol aynı); boşluklar sadeleşir;
      kartta yeni ad görünür; admin olayı kaydedilir
  (C) boş ya da null → otomatik ada döner (otomatik ad yoksa None = ham ad)
  (D) sınırlar: 60 karakter kabul, 61 → 422; kontrol / yön değiştirme karakteri → 422; yok → 404
  (E) açılıştaki otomatik doldurma elle verilen adı ezmez
Çalıştır: python test_admin_display_name.py
"""
import os
import tempfile
import uuid

_db = os.path.join(tempfile.gettempdir(), "nr_test_admin_display_name.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
                  APP_SECRET="dn-secret-1234567890", ADMIN_USERNAME="rootadmin", NEWSRADAR_TRUSTED_PROXY="render",
                  NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR="0", NEWSRADAR_MAX_USERS="0")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402
from app.api.serializers import entity_card  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import Entity, UsageEvent, UserWatchlist  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


def auth(t):
    return {"Authorization": f"Bearer {t}"}


with TestClient(app) as c:
    adm = c.post("/users/register", json={"username": "rootadmin", "password": "parola12345", "email": f"{uuid.uuid4().hex[:8]}@example.com"},
                 headers={"X-Forwarded-For": "192.0.2.1"}).json()
    atok, aid = adm["token"], adm["user"]["id"]
    anon = c.post("/session/bootstrap", headers={"X-Forwarded-For": "192.0.2.2"}).json()["token"]
    with SessionLocal() as s:
        koc = Entity(name="KOC HOLDING AS", display_name="KOC", type="ticker", query="KCHOL.IS", active=True)
        tsla = Entity(name="Tesla", type="ticker", query="TSLA", active=True)
        s.add_all([koc, tsla]); s.flush()
        s.add(UserWatchlist(user_id=aid, entity_id=koc.id))
        s.commit()
        kid, tid = koc.id, tsla.id

    print("== A: liste")
    r = c.get("/admin/entities", headers=auth(atok))
    rows = {x["id"]: x for x in r.json()}
    check(r.status_code == 200 and rows[kid]["followers"] == 1 and rows[kid]["auto_display_name"] == "KOC"
          and rows[tid]["auto_display_name"] is None and r.json()[0]["id"] == kid, "liste: takipçi, otomatik ad, en çok takip edilen önce")
    check(c.get("/admin/entities", headers=auth(anon)).status_code == 403, "admin olmayan 403")
    check(c.patch(f"/admin/entities/{kid}/display-name", json={"display_name": "X"}, headers=auth(anon)).status_code == 403,
          "admin olmayan düzenleyemez (403)")

    print("== B: düzenle")
    r = c.patch(f"/admin/entities/{kid}/display-name", json={"display_name": "  Koç   Holding "}, headers=auth(atok))
    check(r.status_code == 200 and r.json()["display_name"] == "Koç Holding", f"boşluklar sadeleşti ({r.json().get('display_name')})")
    with SessionLocal() as s:
        e = s.get(Entity, kid)
        card = entity_card(s, e, "tr")
        ev = s.query(UsageEvent).filter_by(user_id=aid, event_type="rename_entity").one()
    check(e.name == "KOC HOLDING AS" and e.query == "KCHOL.IS", "ham ad ve sembol değişmedi")
    check(card.display_name == "Koç Holding", "kartta yeni ad")
    check(ev.detail == {"entity_id": kid, "from": "KOC", "to": "Koç Holding", "auto": False}, "admin olayı kaydedildi")

    print("== C: boş → otomatik ad")
    r1 = c.patch(f"/admin/entities/{kid}/display-name", json={"display_name": "   "}, headers=auth(atok))
    r2 = c.patch(f"/admin/entities/{tid}/display-name", json={"display_name": None}, headers=auth(atok))
    check(r1.json()["display_name"] == "KOC", "boş → otomatik ad (KOC HOLDING AS → KOC)")
    check(r2.status_code == 200 and r2.json()["display_name"] is None, "otomatik ad yoksa None (ham ad gösterilir)")

    print("== D: sınırlar")
    ok60 = c.patch(f"/admin/entities/{kid}/display-name", json={"display_name": "a" * 60}, headers=auth(atok))
    bad61 = c.patch(f"/admin/entities/{kid}/display-name", json={"display_name": "a" * 61}, headers=auth(atok))
    check(ok60.status_code == 200 and bad61.status_code == 422, f"60 karakter kabul, 61 → 422 ({ok60.status_code}, {bad61.status_code})")
    for bad, label in (("Koç\u0007Holding", "kontrol karakteri"), ("Koç‮Holding", "yön değiştirme (RTL override)")):
        check(c.patch(f"/admin/entities/{kid}/display-name", json={"display_name": bad}, headers=auth(atok)).status_code == 422,
              f"{label} → 422")
    check(c.patch("/admin/entities/99999/display-name", json={"display_name": "X"}, headers=auth(atok)).status_code == 404, "yok → 404")

    pre = c.options(f"/admin/entities/{kid}/display-name", headers={"Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "PATCH", "Access-Control-Request-Headers": "authorization,content-type"})
    check(pre.status_code == 200 and "PATCH" in pre.headers.get("access-control-allow-methods", ""),
          "CORS ön isteği PATCH'e izin veriyor (arayüz farklı alt alan adında)")

    print("== E: açılış elle verilen adı ezmez")
    c.patch(f"/admin/entities/{kid}/display-name", json={"display_name": "Koç Holding"}, headers=auth(atok))
    init_db()
    with SessionLocal() as s:
        check(s.get(Entity, kid).display_name == "Koç Holding", "init_db sonrası elle verilen ad duruyor")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
