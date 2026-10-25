"""Misafir kayıt temizliği (izole temp DB, anahtarsız).

Doğrular:
  (A) sınır günleri: şirketsiz misafir 29/30 gün kalır, 31 gün silinir; şirketli 89/90 kalır, 91 silinir;
      last_active_at yoksa created_at kullanılır
  (B) kayıtlı kullanıcılara ve admin'e dokunulmaz (400 gün görülmese bile)
  (C) ilk çalıştırma DENEME: hiçbir şey silinmez, silinecek sayı kaydedilir; ikincisi siler
  (D) ortak havuz korunur: entity ve analizleri kalır (kimsede kalmadıysa pasif, başkasındaysa aktif);
      kişisel satırlar (liste, olaylar, e-posta token'ı) silinir, geri bildirim anonimleşir
  (E) NEWSRADAR_ANON_CLEANUP=off işi kapatır, dry-run her çalıştırmayı deneme yapar; admin ucu
Çalıştır: python test_anon_cleanup.py
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_anon_cleanup.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
                  APP_SECRET="ac-secret-1234567890", NEWSRADAR_ANON_CLEANUP="on")

from sqlalchemy import select  # noqa: E402

from app import anon_cleanup as AC, scheduler  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import (  # noqa: E402
    EmailToken, Entity, EntityAnalysis, Feedback, MaintenanceRun, UsageEvent, User, UserWatchlist,
)

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
init_db()
with SessionLocal() as s:
    shared = Entity(name="Tesla", type="ticker", query="TSLA", active=True)
    lonely = Entity(name="Ocugen", type="ticker", query="OCGN", active=True)
    s.add_all([shared, lonely]); s.flush()
    s.add(EntityAnalysis(entity_id=lonely.id, language="all", risk_score=50, sentiment_trend="stable", top_drivers=[],
                         summary="s.", stance="neutral", conviction="low", what_to_verify=[], invalidation="i."))

    def user(name, days, anon=True, companies=(), last_active=True, admin=False):
        seen = NOW - timedelta(days=days)
        u = User(username=name, password_hash="x", is_anonymous=anon, is_admin=admin, created_at=seen,
                 last_active_at=seen if last_active else None)
        s.add(u); s.flush()
        for e in companies:
            s.add(UserWatchlist(user_id=u.id, entity_id=e.id))
        return u.id

    ids = {
        "e29": user("anon:e29", 29), "e30": user("anon:e30", 30), "e31": user("anon:e31", 31),
        "c89": user("anon:c89", 89, companies=[shared]), "c90": user("anon:c90", 90, companies=[shared]),
        "c91": user("anon:c91", 91, companies=[shared, lonely]),
        "nolast": user("anon:nolast", 40, last_active=False),
        "reg": user("kayitli", 400, anon=False), "regco": user("kayitli2", 400, anon=False, companies=[shared]),
        "admin": user("admin", 400, anon=False, admin=True),
    }
    # Silinecek misafirin kişisel satırları
    s.add(UsageEvent(user_id=ids["c91"], event_type="view_entity", detail={"entity_id": lonely.id}))
    s.add(EmailToken(user_id=ids["c91"], purpose="verify", token_hash="h" * 64, expires_at=NOW))
    s.add(Feedback(user_id=ids["c91"], message="güzel site"))
    s.commit()
    shared_id, lonely_id = shared.id, lonely.id

print("== A/B: adaylar")
with SessionLocal() as s:
    cand = {uid for uid, _ in AC.candidates(s, NOW)}
expect = {ids["e31"], ids["c91"], ids["nolast"]}
check(cand == expect, f"silinecekler: şirketsiz 31 gün, şirketli 91 gün, last_active yok + 40 gün ({sorted(cand)})")
check(ids["e29"] not in cand and ids["e30"] not in cand, "şirketsiz 29 ve tam 30 gün kalır")
check(ids["c89"] not in cand and ids["c90"] not in cand, "şirketli 89 ve tam 90 gün kalır")
check(not {ids["reg"], ids["regco"], ids["admin"]} & cand, "kayıtlı hesaplar ve admin aday değil (400 gün olsa da)")

print("== C: ilk çalıştırma deneme")
r1 = AC.run(now=NOW)
with SessionLocal() as s:
    n_users = s.query(User).count()
    runs = s.query(MaintenanceRun).all()
check(r1["dry_run"] and r1["deleted"] == 3 and n_users == 10, f"deneme: 3 silinecek, hiçbiri silinmedi ({r1})")
check(len(runs) == 1 and runs[0].dry_run and runs[0].deleted == 3 and runs[0].details["with_companies"] == 1,
      "deneme kaydı (silinecek 3; şirketli 1, şirketsiz 2)")
r2 = AC.run(now=NOW)
with SessionLocal() as s:
    left = {u.username for u in s.query(User)}
check(not r2["dry_run"] and r2["deleted"] == 3, "ikinci çalıştırma gerçekten sildi")
check(left == {"anon:e29", "anon:e30", "anon:c89", "anon:c90", "kayitli", "kayitli2", "admin"}, f"kalanlar doğru ({sorted(left)})")

print("== D: ortak havuz ve kişisel satırlar")
with SessionLocal() as s:
    sh, lo = s.get(Entity, shared_id), s.get(Entity, lonely_id)
    analyses = s.query(EntityAnalysis).filter_by(entity_id=lonely_id).count()
    personal = (s.query(UserWatchlist).filter_by(user_id=ids["c91"]).count(),
                s.query(UsageEvent).filter_by(user_id=ids["c91"]).count(),
                s.query(EmailToken).filter_by(user_id=ids["c91"]).count())
    fb = s.query(Feedback).one()
check(sh is not None and lo is not None and analyses == 1, "entity'ler ve analizleri silinmedi")
check(sh.active and not lo.active, "başkasının listesindeki entity aktif, kimsede kalmayan pasif")
check(personal == (0, 0, 0), f"kişisel satırlar silindi (liste, olay, e-posta token'ı) {personal}")
check(fb.message == "güzel site" and fb.user_id is None, "geri bildirim kaldı, kimliği düştü")

print("== E: ayarlar ve admin ucu")
with SessionLocal() as s:
    s.add(User(username="anon:yeni-eski", password_hash="x", is_anonymous=True,
               created_at=NOW - timedelta(days=200), last_active_at=NOW - timedelta(days=200)))
    s.commit()
os.environ["NEWSRADAR_ANON_CLEANUP"] = "off"; get_settings.cache_clear()
before = SessionLocal().query(MaintenanceRun).count()
scheduler._anon_cleanup_job()
check(SessionLocal().query(MaintenanceRun).count() == before, "off: zamanlayıcı işi hiçbir şey yapmadı")
os.environ["NEWSRADAR_ANON_CLEANUP"] = "dry-run"; get_settings.cache_clear()
r3 = AC.run()
check(r3["dry_run"] and SessionLocal().scalar(select(User.id).where(User.username == "anon:yeni-eski")) is not None,
      "dry-run: her çalıştırma deneme (silmedi)")
os.environ["NEWSRADAR_ANON_CLEANUP"] = "on"; get_settings.cache_clear()
with SessionLocal() as s:
    last = AC.last_run(s)
check(last["dry_run"] and last["deleted"] == 1 and "ran_at" in last, f"son çalışma bilgisi (admin paneli) {last}")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
