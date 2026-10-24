"""Gösterilen analist hedefi: medyan varsa medyan, yoksa FMP konsensüsü (ortalama). Kart/detay
(AnalystOut), istem bağlamı (analyst_context_for) ve istem satırı aynı değeri ve yüzdeyi kullanır
(izole temp DB, anahtarsız).

Çalıştır: python test_analyst_target.py
"""
import os
import tempfile

_db = os.path.join(tempfile.gettempdir(), "nr_test_analyst_target.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off")

from app.analysis.prompts import _analyst_lines  # noqa: E402
from app.analyst import analyst_context_for, display_target  # noqa: E402
from app.api.serializers import _analyst_out  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import AnalystSnapshot, Entity, PriceSnapshot  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


init_db()
with SessionLocal() as s:
    tsla = Entity(name="Tesla", type="ticker", query="TSLA", active=True)
    old = Entity(name="Eski", type="ticker", query="OLD", active=True)
    s.add_all([tsla, old]); s.flush()
    # TSLA yerel DB örneği: konsensüs (ortalama) 431.09, medyan 420.
    s.add(AnalystSnapshot(entity_id=tsla.id, strong_buy=5, buy=10, hold=12, sell=5, strong_sell=2,
                          target_mean=431.09, target_consensus=431.09, target_median=420.0,
                          target_high=600.0, target_low=150.0))
    # Medyanı olmayan eski kayıt → konsensüse düşer.
    s.add(AnalystSnapshot(entity_id=old.id, strong_buy=1, buy=0, hold=0, sell=0, strong_sell=0,
                          target_mean=110.0, target_consensus=110.0))
    s.add_all([PriceSnapshot(entity_id=tsla.id, price=372.0), PriceSnapshot(entity_id=old.id, price=100.0)])
    s.commit()
    snap_t = s.query(AnalystSnapshot).filter_by(entity_id=tsla.id).one()
    snap_o = s.query(AnalystSnapshot).filter_by(entity_id=old.id).one()
    tid, oid = tsla.id, old.id

    print("== display_target")
    check(display_target(snap_t) == (420.0, "median"), "medyan varsa medyan")
    check(display_target(snap_o) == (110.0, "consensus"), "medyan yoksa konsensüs")

    print("== AnalystOut (kart/detay)")
    a = _analyst_out(snap_t, 372.0)
    check(a.target == 420.0 and a.target_kind == "median", f"target=medyan ({a.target}, {a.target_kind})")
    check(a.upside_percent == round((420 - 372) / 372 * 100, 1), f"fark medyana göre ({a.upside_percent})")
    check(a.target_mean == 431.09 and a.target_median == 420.0, "ham alanlar korunur (geriye uyum)")
    b = _analyst_out(snap_o, 100.0)
    check(b.target == 110.0 and b.target_kind == "consensus" and b.upside_percent == 10.0, "eski kayıt: konsensüs + fark")

print("== istem bağlamı")
ctx = analyst_context_for(tid)
check(ctx["target"] == 420.0 and ctx["target_kind"] == "median", "bağlamda medyan")
check(ctx["upside_percent"] == a.upside_percent, "istem ve kart aynı yüzdeyi kullanır")
line = next(x for x in _analyst_lines(ctx) if "HEDEF FİYATI" in x)
check("medyan=420.0" in line and "431" not in line, f"istem satırı medyanı aktarır ({line[:80]}…)")
line_o = next(x for x in _analyst_lines(analyst_context_for(oid)) if "HEDEF FİYATI" in x)
check("ortalama=110.0" in line_o, "konsensüs düşüşünde 'ortalama' yazar")
# Eski biçimli bağlam (target yok) da çalışır.
legacy = {"total": 0, "target_mean": 50.0, "target_low": None, "target_high": None}
check(any("ortalama=50.0" in x for x in _analyst_lines(legacy)), "target alanı olmayan eski bağlam")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
