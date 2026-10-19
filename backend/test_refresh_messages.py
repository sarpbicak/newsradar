"""Yenileme özeti + mesajlar — sayaçlar net, uyarılar kod+parametre, beklenen hatalar sessiz.

Doğrular:
  (A) her mesaj kodu ve kaynak için frontend'de TR+EN çeviri var (messages.py ↔ i18n.jsx)
  (B) render(): tüm kodlar parametreleriyle Türkçe log metnine dönüşüyor
  (C) beklenen/kalıcı sağlayıcı hatası (403, sembol kapsam dışı): uyarı YOK, 24 saat
      tekrar denenmez (provider_skips), süre dolunca yeniden denenir; beklenmeyen hata
      kullanıcıya entity'li uyarı olarak gider
  (D) FMP 401/402/403 → expected=True; 500 → expected=False
  (E) sayaçlar: llm_articles = tutulan + elenen; kuyruk (queued) doğru
Çalıştır: python test_refresh_messages.py
"""
import asyncio
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

_db = os.path.join(tempfile.gettempdir(), "nr_test_refresh_msgs.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y", NEWSRADAR_SCHEDULER="off",
    NEWSRADAR_SEED_ON_START="off", NEWSRADAR_LLM_PROVIDER="anthropic",
    NEWSRADAR_DAILY_BUDGET_USD="0", NEWSRADAR_BATCH_SIZE="10", FMP_API_KEY="test",
)

from app import analyst as analyst_mod  # noqa: E402
from app.analysis.pipeline import analyze_all_async  # noqa: E402
from app.analysis.schemas import ARTICLE_ANALYSIS_TOOL  # noqa: E402
from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import Article, Entity, ProviderSkip  # noqa: E402
from app.messages import CODES, _SOURCE_TR, msg, render  # noqa: E402
from app.providers import fmp_analyst  # noqa: E402
from app.providers.base import AnalystRating, AnalystResult  # noqa: E402
from app.refresh import _queued_count  # noqa: E402

PASS = FAIL = 0


def check(cond, msg_):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg_}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg_}")


init_db()

print("== A: backend kodları ↔ frontend çevirileri ==")
i18n = (Path(__file__).resolve().parent.parent / "frontend/src/i18n.jsx").read_text(encoding="utf-8")
missing = [c for c in sorted(CODES)
           if not re.search(rf'"msg\.{c}": \{{ tr: "[^"]+", en: "[^"]+" \}}', i18n)]
check(not missing, f"her mesaj kodunun TR+EN çevirisi var (eksik: {missing})")
missing_src = [s for s in _SOURCE_TR if f'"src.{s}"' not in i18n]
check(not missing_src, f"her kaynağın çevirisi var (eksik: {missing_src})")
for k in ("notice.warnings_one", "notice.newArticles_one", "notice.infos_one", "notice.queued_one"):
    check(f'"{k}"' in i18n, f"tekil biçim tanımlı: {k}")
check('en: " 1 warning."' in i18n and 'en: " {n} warnings."' in i18n, "EN: '1 warning' / 'N warnings'")

print("== B: render() ==")
sample = {"type": "x", "hours": 2, "used": 100, "limit": 100, "error": "E", "key": "K",
          "source": "fmp_target", "status": 403, "symbol": "AAPL", "message": "m",
          "batches": 2, "article_id": 7, "count": 3, "lang": "tr", "detail": "d"}
bad = [c for c in CODES if "{" in render(msg(c, "Tesla", **sample)).split("] ", 1)[-1]]
check(not bad, f"tüm kodlar parametreyle doldu (doldurulmayan: {bad})")
check(render(msg("http_error", "Apple", source="fmp_target", status=403, symbol="AAPL"))
      == "[Apple] FMP hedef fiyat hatası (403) — AAPL atlandı.", "kaynak adı + entity önekiyle Türkçe log")

print("== C: beklenen hatalar sessiz + 24 saat cache ==")
with session_scope() as s:
    e = Entity(name="Apple", type="ticker", query="AAPL", active=True)
    s.add(e); s.flush()
    apple_id = e.id


class FakeProvider:
    def __init__(self, name, result):
        self.name, self.result, self.calls = name, result, 0
    def is_available(self):
        return True
    def fetch(self, entity):
        self.calls += 1
        return self.result


rec = FakeProvider("finnhub-analyst", AnalystResult(provider="f", rating=AnalystRating(buy=3)))
tgt = FakeProvider("fmp-target", AnalystResult(
    provider="fmp-target", expected=True,
    warning=msg("http_error", source="fmp_target", status=403, symbol="AAPL")))
analyst_mod.get_analyst_provider = lambda: rec
analyst_mod.get_target_provider = lambda: tgt
w1 = analyst_mod.refresh_analyst({apple_id})
check(w1 == [], f"beklenen 403 → kullanıcıya uyarı YOK ({w1})")
with session_scope() as s:
    row = s.get(ProviderSkip, "fmp-target:AAPL")
    check(row is not None and row.code == "http_error" and row.status == 403
          and row.until > datetime.now(timezone.utc) + timedelta(hours=23),
          "provider_skips: 403 kaydı ~24 saat")
analyst_mod.refresh_analyst({apple_id})
check(tgt.calls == 1 and rec.calls == 2, f"24 saat içinde FMP'ye tekrar gidilmedi (fmp={tgt.calls}, finnhub={rec.calls})")
with session_scope() as s:
    s.get(ProviderSkip, "fmp-target:AAPL").until = datetime.now(timezone.utc) - timedelta(minutes=1)
analyst_mod.refresh_analyst({apple_id})
check(tgt.calls == 2, "süre dolunca yeniden denendi")
tgt.result = AnalystResult(provider="fmp-target",
                           warning=msg("http_error", source="fmp_target", status=500, symbol="AAPL"))
with session_scope() as s:
    s.query(ProviderSkip).delete()
w2 = analyst_mod.refresh_analyst({apple_id})
check(w2 == [{"code": "http_error", "entity": "Apple",
              "params": {"source": "fmp_target", "status": 500, "symbol": "AAPL"}}],
      f"beklenmeyen 500 → entity'li kodlu uyarı ({w2})")

print("== D: FMP durum kodları ==")
_orig_get = fmp_analyst.httpx.get
for status, exp in ((403, True), (402, True), (401, True), (500, False)):
    fmp_analyst.httpx.get = lambda *a, _s=status, **k: SimpleNamespace(status_code=_s, json=lambda: {})
    r = fmp_analyst.FMPAnalystProvider().fetch(SimpleNamespace(query="AAPL"))
    check(r.expected is exp and r.warning["code"] == "http_error" and r.warning["params"]["status"] == status,
          f"FMP {status} → expected={exp}")
fmp_analyst.httpx.get = _orig_get

print("== E: sayaçlar ==")
with session_scope() as s:
    e = Entity(name="Counter", type="keyword", query="Counter", active=True, language="en")
    s.add(e); s.flush()
    cid = e.id
    words = ["merger", "lawsuit", "earnings", "factory", "recall", "partnership", "layoffs",
             "dividend", "patent", "acquisition", "regulator", "outage", "launch", "guidance"]
    for i in range(14):
        s.add(Article(entity_id=cid, url=f"http://c/{i}", url_hash=f"c{i}",
                      title=f"{words[i]} {words[(i + 5) % 14]}{i} headline{i * 7}",
                      source="s", description="d", provider="t", analyzed=False, prefiltered=False,
                      published_at=datetime.now(timezone.utc) - timedelta(hours=i + 1)))
os.environ["NEWSRADAR_MAX_ARTICLES_PER_ENTITY"] = "10"
from app.config import get_settings  # noqa: E402
get_settings().max_articles_per_entity = 10


class Client:
    model = "fake"
    def call_tool(self, *, system, user, tool, max_tokens=4096):
        if tool["name"] != ARTICLE_ANALYSIS_TOOL["name"]:
            return {"headline_verdict": "v.", "summary": "s."}
        ids = [int(x) for x in re.findall(r"id=(\d+)", user)] or [int(x) for x in re.findall(r'"id": (\d+)', user)]
        return {"analyses": [{"id": i, "sentiment": 0.1, "event_type": "other", "risk_flags": [],
                              "impact_horizon": "short", "relevance": 0.9 if n % 2 == 0 else 0.1,
                              "rationale": "r.", "co_mentioned_entities": []}
                             for n, i in enumerate(ids)]}


t = asyncio.run(analyze_all_async(Client(), entity_ids={cid}))
check(t.llm_articles == 10, f"llm_articles = LLM'e giden 10 ({t.llm_articles})")
check(t.analyzed + t.discarded == t.llm_articles and t.discarded > 0,
      f"llm_articles = tutulan ({t.analyzed}) + elenen ({t.discarded})")
check(_queued_count({cid}) == 4, f"kuyrukta 4 makale kaldı (tavan 10) ({_queued_count({cid})})")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
