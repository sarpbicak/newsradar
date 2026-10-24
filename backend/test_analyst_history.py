"""Dashboard analyst_history: dönem başına SON snapshot, toplam 0 olanlar atlanır, eski → yeni,
en fazla 6 dönem; ticker olmayan şirkette boş (izole temp DB, anahtarsız).

Çalıştır: python test_analyst_history.py
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_analyst_history.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off")

from app.api.serializers import analyst_history  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import AnalystSnapshot, Entity  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


init_db()
now = datetime.now(timezone.utc)
with SessionLocal() as s:
    e = Entity(name="NVIDIA", type="ticker", query="NVDA", active=True)
    s.add(e); s.flush()

    def snap(period, sb, days_ago):
        s.add(AnalystSnapshot(entity_id=e.id, period=period, strong_buy=sb, buy=1, hold=1, sell=0, strong_sell=0,
                              fetched_at=now - timedelta(days=days_ago)))
    # Aynı dönemde iki snapshot: yenisi (sb=9) kazanmalı.
    snap("2026-07-01", 5, 40); snap("2026-07-01", 9, 35)
    snap("2026-08-01", 7, 10)
    # Toplamı 0 olan snapshot atlanır.
    s.add(AnalystSnapshot(entity_id=e.id, period="2026-09-01", strong_buy=0, buy=0, hold=0, sell=0, strong_sell=0,
                          fetched_at=now - timedelta(days=2)))
    for i in range(8):  # çok dönem → en fazla 6
        snap(f"2025-{i + 1:02d}-01", 1, 400 - i)
    s.commit()
    h = analyst_history(s, e.id)

print("== analyst_history")
check(len(h) == 6, f"en fazla 6 dönem ({len(h)})")
check([x.period for x in h] == sorted(x.period for x in h), "eski → yeni sıralı")
check(h[-1].period == "2026-08-01" and h[-2].period == "2026-07-01", f"en yeni dönemler ({[x.period for x in h][-2:]})")
check(h[-2].strong_buy == 9, f"dönemin SON snapshot'ı ({h[-2].strong_buy})")
check(all(x.period != "2026-09-01" for x in h), "toplamı 0 olan dönem atlanır")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
