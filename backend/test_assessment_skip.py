"""Gereksiz değerlendirmeyi atlama — sahte client (gerçek API yok, izole temp DB).

Doğrular:
  (A) ilk tarama → TR + EN değerlendirme (2 çağrı)
  (B) yeni veri yok → 0 değerlendirme çağrısı, log: "[X] değerlendirme atlandı: yeni veri yok"
  (C) fiyat ≥ %3 oynadı → yeniden değerlendirme; %2 → atlanır
  (D) son değerlendirme 24 saatten eski → yeniden değerlendirme
  (E) yeni analiz edilmiş makale → yeniden değerlendirme
Çalıştır: python test_assessment_skip.py
"""
import asyncio
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_assess_skip.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y", NEWSRADAR_SCHEDULER="off",
    NEWSRADAR_SEED_ON_START="off", NEWSRADAR_LLM_PROVIDER="anthropic",
    NEWSRADAR_DAILY_BUDGET_USD="0",
)

from sqlalchemy import update  # noqa: E402

from app.analysis.pipeline import analyze_all_async  # noqa: E402
from app.analysis.schemas import ENTITY_ANALYSIS_TOOL  # noqa: E402
from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import Article, Entity, EntityAnalysis, PriceSnapshot  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


class LogCap(logging.Handler):
    def __init__(self): super().__init__(); self.msgs = []
    def emit(self, r): self.msgs.append(r.getMessage())


cap = LogCap()
lg = logging.getLogger("newsradar.analysis")
lg.addHandler(cap); lg.setLevel(logging.INFO)


class FakeClient:
    model = "fake"
    def __init__(self):
        self.assess_calls = 0
        self.article_calls = 0
    def call_tool(self, *, system, user, tool, max_tokens=4096):
        if tool["name"] == ENTITY_ANALYSIS_TOOL["name"]:
            self.assess_calls += 1
            if "CRITICAL RULES" in user:  # EN çıktı istendi → İngilizce (dil sızıntısı yok)
                return {"headline_verdict": "Verdict.", "summary": "Summary.", "risk_score": 40}
            return {"headline_verdict": "hüküm", "summary": "özet", "risk_score": 40}
        self.article_calls += 1
        return {"analyses": []}


def now():
    return datetime.now(timezone.utc)


init_db()
with session_scope() as s:
    e = Entity(name="Tesla", type="ticker", query="TSLA", active=True, language="en")
    s.add(e); s.flush()
    eid = e.id
    s.add(Article(entity_id=eid, url="http://a/1", url_hash="h1", title="Tesla news",
                  source="s", description="d", provider="t", analyzed=True,
                  analyzed_at=now() - timedelta(hours=1), prefiltered=False,
                  sentiment=0.2, event_type="other", relevance=0.9))
    s.add(PriceSnapshot(entity_id=eid, price=100.0, fetched_at=now() - timedelta(hours=2)))


def run():
    fc = FakeClient()
    cap.msgs.clear()
    totals = asyncio.run(analyze_all_async(fc, entity_ids={eid}))
    return fc, totals


print("== A: ilk tarama ==")
fc, t = run()
check(fc.assess_calls == 2 and t.entity_assessments == 2, f"TR+EN değerlendirildi ({fc.assess_calls})")

print("== B: yeni veri yok ==")
fc, t = run()
check(fc.assess_calls == 0 and t.assessments_skipped == 2, f"değerlendirme çağrısı yok ({fc.assess_calls})")
check(any(m.startswith("[Tesla] değerlendirme atlandı: yeni veri yok") for m in cap.msgs),
      "log: [Tesla] değerlendirme atlandı: yeni veri yok")

print("== C: fiyat hareketi ==")
with session_scope() as s:
    s.add(PriceSnapshot(entity_id=eid, price=102.0, fetched_at=now()))
fc, _ = run()
check(fc.assess_calls == 0, f"%2 hareket → atlandı ({fc.assess_calls})")
with session_scope() as s:
    s.add(PriceSnapshot(entity_id=eid, price=103.5, fetched_at=now()))
fc, _ = run()
check(fc.assess_calls == 2, f"%3.5 hareket → TR+EN yeniden ({fc.assess_calls})")
check(any("fiyat %+3.5 oynadı" in m for m in cap.msgs), "sebep loglandı (fiyat)")

print("== D: 24 saatten eski ==")
with session_scope() as s:
    s.execute(update(EntityAnalysis).where(EntityAnalysis.entity_id == eid)
              .values(created_at=now() - timedelta(hours=25)))
fc, _ = run()
check(fc.assess_calls == 2, f"25 saatlik değerlendirme → yeniden ({fc.assess_calls})")

print("== E: yeni analiz edilmiş makale ==")
fc, _ = run()
check(fc.assess_calls == 0, "ara tarama → atlandı")
with session_scope() as s:
    s.add(Article(entity_id=eid, url="http://a/2", url_hash="h2", title="Tesla new",
                  source="s", description="d", provider="t", analyzed=True,
                  analyzed_at=now() + timedelta(seconds=1), prefiltered=False,
                  sentiment=0.1, event_type="other", relevance=0.9))
fc, _ = run()
check(fc.assess_calls == 2, f"yeni makale → TR+EN yeniden ({fc.assess_calls})")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
