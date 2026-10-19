"""Yenileme ilerlemesi — adım bazlı metin + entity içinde dolan çubuk (izole temp DB).

Doğrular:
  (A) analyze_all_async adımları: filter → analyze (batch'ler bittikçe artan frac) →
      assess → done; yeni verisi olmayan entity → skipped
  (B) refresh durumu: progress_fraction = entity dilimlerinin ortalaması, done sayacı,
      frac geri gitmez, atlama notu ~3 sn sonra kaybolur
  (C) fetch bildirimi entity dilimini 0.15'e taşır (çubuk 0'da takılmaz)
Çalıştır: python test_progress.py
"""
import asyncio
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_progress.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y" * 20,
                  NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
                  NEWSRADAR_LLM_PROVIDER="anthropic", NEWSRADAR_DAILY_BUDGET_USD="0",
                  NEWSRADAR_BATCH_SIZE="4")

from app import refresh as R  # noqa: E402
from app.analysis.pipeline import analyze_all_async  # noqa: E402
from app.analysis.schemas import ARTICLE_ANALYSIS_TOOL  # noqa: E402
from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import Article, Entity, EntityAnalysis  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


now = datetime.now(timezone.utc)
init_db()
words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]
with session_scope() as s:
    busy = Entity(name="Busy", type="keyword", query="Busy", active=True, language="en")
    quiet = Entity(name="Quiet", type="keyword", query="Quiet", active=True, language="en")
    s.add_all([busy, quiet]); s.flush()
    bid, qid = busy.id, quiet.id
    for i in range(8):
        s.add(Article(entity_id=bid, url=f"http://b/{i}", url_hash=f"b{i}", source="s",
                      title=f"{words[i]} {words[(i + 3) % 10]}{i} story{i * 13}", description="d",
                      provider="t", analyzed=False, prefiltered=False, published_at=now - timedelta(hours=i + 1)))
    # Quiet: taze değerlendirmesi var, yeni makale yok → atlanmalı
    for lang in ("tr", "en"):
        s.add(EntityAnalysis(entity_id=qid, language=lang, risk_score=40, sentiment_trend="stable",
                             top_drivers=[], summary="s.", stance="neutral", conviction="low",
                             what_to_verify=[], invalidation="i.", created_at=now))


class Client:
    model = "fake"
    def call_tool(self, *, system, user, tool, max_tokens=4096):
        if tool["name"] != ARTICLE_ANALYSIS_TOOL["name"]:
            return {"headline_verdict": "v.", "summary": "s."}
        ids = [int(x) for x in re.findall(r"id=(\d+)", user)]
        return {"analyses": [{"id": i, "sentiment": 0.1, "event_type": "other", "risk_flags": [],
                              "impact_horizon": "short", "relevance": 0.9, "rationale": "r.",
                              "co_mentioned_entities": []} for i in ids]}


print("== A: adımlar ==")
events = []
asyncio.run(analyze_all_async(Client(), entity_ids={bid, qid},
                              step_cb=lambda eid, name, step, n, frac: events.append((name, step, n, frac))))
busy_ev = [(st, n, f) for name, st, n, f in events if name == "Busy"]
steps = [st for st, _, _ in busy_ev]
check(steps[0] == "filter" and busy_ev[0][1] == 8, f"önce filtre (8 makale): {busy_ev[0]}")
check(steps.count("analyze") == 3 and busy_ev[1][1] == 8, f"analiz: başlangıç + 2 batch ({steps})")
fr = [f for st, _, f in busy_ev if st == "analyze"]
check(fr == sorted(fr) and abs(fr[-1] - 0.8) < 1e-9, f"analiz dilimi batch'lerle artıyor ({fr})")
check(steps[-2:] == ["assess", "done"], f"sonra değerlendirme → bitiş ({steps[-2:]})")
quiet_steps = [st for name, st, _, _ in events if name == "Quiet"]
check("skipped" in quiet_steps and "assess" not in quiet_steps, f"yeni veri yok → skipped ({quiet_steps})")

print("== B/C: refresh durumu ==")
R._set_running(True, total=2, user_id=1, entity_ids=[bid, qid])
R._on_fetch(bid, "Busy", "start")
st = R.get_state()
check(st["step"] == "fetch" and st["step_entity"] == "Busy" and st["progress_fraction"] > 0,
      f"çekme başladı → metin + çubuk 0'dan kalktı ({st['progress_fraction']})")
R._on_fetch(bid, "Busy", "done")
check(abs(R.get_state()["progress_fraction"] - 0.075) < 1e-9, "fetch bitti: Busy 0.15 → genel 0.075")
R._report_step(bid, "Busy", "analyze", n=8, frac=0.5)
R._report_step(bid, "Busy", "filter", n=8, frac=0.2)  # geri gitmemeli
check(abs(R.get_state()["progress_fraction"] - 0.25) < 1e-9, "frac geri gitmez (0.5 kaldı)")
R._report_step(qid, "Quiet", "skipped", frac=1.0)
st = R.get_state()
check(st["skipped_entity"] == "Quiet" and st["progress_done"] == 1, "atlama notu + done=1")
check(st["step"] == "filter" and st["step_entity"] == "Busy", "atlama, süren adım metnini ezmedi (son adım Busy/filter)")
R._state.skipped_at -= R.SKIP_NOTE_SECONDS + 0.1
check(R.get_state()["skipped_entity"] is None, "atlama notu ~3 sn sonra kayboldu")
R._report_step(bid, "Busy", "done", frac=1.0)
st = R.get_state()
check(st["progress_fraction"] == 1.0 and st["progress_done"] == 2, "hepsi bitti → 1.0, 2/2")
R._set_running(False)

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
