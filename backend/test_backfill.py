"""Yeni şirkette bir kerelik geriye dönük doldurma (izole temp DB, anahtarsız, sahte sağlayıcı/LLM).

Doğrular:
  (A) yeni şirket (değerlendirmesi yok): sağlayıcıdan 7 günlük pencere istenir; 48 saatten
      eskilerden yalnızca en yeni 20'si kaydedilir (backfill=True), 7 günden eski hiç kaydedilmez
  (B) ikinci yenilemede doldurma ÇALIŞMAZ: pencere 48 saat, eski haber kaydedilmez
  (C) değerlendirmesi olan şirkette ve sağlayıcı hatasında doldurma yok / işaretlenmez
  (D) expire: doldurma haberi çekildikten sonra bir lookback süresi expire edilmez; normal eski
      bekleyen haber expire edilir
  (E) OCGN senaryosu: yalnızca 4 günlük tek haberi olan şirket eklendiği gün değerlendirme alır;
      doldurmadan sonra da haber yoksa 'son 7 günde yeterli haber yok'
Çalıştır: python test_backfill.py
"""
import asyncio
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_backfill.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
                  NEWSRADAR_LOOKBACK_HOURS="48", NEWSRADAR_BACKFILL_DAYS="7",
                  NEWSRADAR_BACKFILL_MAX_ARTICLES="20", NEWSRADAR_LLM_PROVIDER="anthropic",
                  NEWSRADAR_DAILY_BUDGET_USD="0", APP_SECRET="y")

from sqlalchemy import update  # noqa: E402

import app.ingest as ingest  # noqa: E402
from app.analysis.pipeline import analyze_all_async, expire_stale_pending  # noqa: E402
from app.analysis.schemas import ARTICLE_ANALYSIS_TOOL, ENTITY_ANALYSIS_TOOL, TRANSLATION_TOOL  # noqa: E402
from app.api.serializers import entity_card  # noqa: E402
from app.db.database import SessionLocal, init_db, session_scope  # noqa: E402
from app.db.models import Article, Entity, EntityAnalysis  # noqa: E402
from app.providers.base import FetchedArticle, ProviderResult  # noqa: E402
from app.refresh import _few_news_messages  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


now = datetime.now(timezone.utc)


class FakeProvider:
    name = "finnhub"
    entity_filtered = True

    def __init__(self, articles, warning=None):
        self.articles, self.warning, self.since = articles, warning, []

    def is_available(self):
        return True

    def fetch(self, entity, since):
        self.since.append(since)
        return ProviderResult(provider="finnhub", articles=list(self.articles), warning=self.warning)


def art(key, hours):
    return FetchedArticle(url=f"http://x/{key}", title=f"Haber {key}", published_at=now - timedelta(hours=hours))


def stored(s, eid):
    return {a.title: a.backfill for a in s.query(Article).filter(Article.entity_id == eid)}


init_db()
print("== A: yeni şirket → bir kerelik 7 günlük doldurma ==")
old = [art(f"eski{i}", 50 + i * 4) for i in range(25)]  # 50..146 sa (2-6 gün)
p = FakeProvider([art("taze", 3), *old, art("cokeski", 24 * 10)])
ingest.get_provider_for = lambda e: p
with SessionLocal() as s:
    e = Entity(name="Yeni AŞ", type="ticker", query="YENI", active=True)
    s.add(e); s.commit()
    r = ingest.fetch_for_entity(s, e)
    st = stored(s, e.id)
    eid, backfilled_at = e.id, e.backfilled_at
check(abs((now - p.since[0]).total_seconds() - 7 * 86400) < 60, "sağlayıcıdan 7 günlük pencere istendi")
check(st.get("Haber taze") is False, "pencere içindeki haber normal kaydedildi")
olds = [t for t, b in st.items() if b]
check(len(olds) == 20 and r.backfilled == 20, f"eskilerden en fazla 20 ({len(olds)})")
check("Haber eski0" in olds and "Haber eski19" in olds and "Haber eski20" not in olds, "en yeni 20 seçildi")
check("Haber cokeski" not in st and r.too_old == 6, f"7 günden eski kaydedilmedi, fazlalar sayıldı (too_old={r.too_old})")
check(backfilled_at is not None, "doldurma işaretlendi (backfilled_at)")

print("== B: ikinci yenilemede doldurma yok ==")
p2 = FakeProvider([art("taze2", 2), art("eski-yeni-url", 70)])
ingest.get_provider_for = lambda e: p2
with SessionLocal() as s:
    e = s.get(Entity, eid)
    r2 = ingest.fetch_for_entity(s, e)
    st2 = stored(s, eid)
check(abs((now - p2.since[0]).total_seconds() - 48 * 3600) < 60, "pencere yine 48 saat")
check("Haber eski-yeni-url" not in st2 and r2.too_old == 1 and r2.backfilled == 0, "48 saatten eski haber kaydedilmedi")

print("== C: değerlendirmesi olan şirket / sağlayıcı hatası ==")
p3 = FakeProvider([art("x1", 3), art("x2", 80)])
ingest.get_provider_for = lambda e: p3
with SessionLocal() as s:
    e = Entity(name="Eski AŞ", type="ticker", query="ESKI", active=True)
    s.add(e); s.flush()
    s.add(EntityAnalysis(entity_id=e.id, language="tr", risk_score=50, sentiment_trend="stable", top_drivers=[],
                         summary="s.", stance="neutral", conviction="low", what_to_verify=[], invalidation="i."))
    s.commit()
    r3 = ingest.fetch_for_entity(s, e)
    check(r3.backfilled == 0 and "Haber x2" not in stored(s, e.id) and e.backfilled_at is None,
          "değerlendirmesi olan şirkette doldurma yok")
p4 = FakeProvider([], warning={"code": "http_error", "params": {"status": 500}})
ingest.get_provider_for = lambda e: p4
with SessionLocal() as s:
    e = Entity(name="Hatalı AŞ", type="ticker", query="HATA", active=True)
    s.add(e); s.commit()
    ingest.fetch_for_entity(s, e)
    check(e.backfilled_at is None, "sağlayıcı hatasında işaretlenmedi (sonraki yenileme dener)")

print("== D: expire istisnası ==")
with session_scope() as s:
    s.add(Article(entity_id=eid, url="http://x/bekleyen-eski", url_hash="be", title="Normal eski", source="s",
                  description="d", provider="t", published_at=now - timedelta(hours=72),
                  fetched_at=now - timedelta(hours=72)))
n = expire_stale_pending()
with session_scope() as s:
    exp = {a.title: a.expired for a in s.query(Article).filter(Article.entity_id == eid)}
check(exp["Normal eski"] is True, "normal eski bekleyen haber expire edildi")
check(not any(exp[t] for t in olds), "doldurma haberleri (yeni çekildi) expire edilmedi")
with session_scope() as s:
    s.execute(update(Article).where(Article.entity_id == eid, Article.backfill.is_(True))
              .values(fetched_at=now - timedelta(hours=49)))
expire_stale_pending()
with session_scope() as s:
    still = s.query(Article).filter(Article.entity_id == eid, Article.backfill.is_(True), Article.expired.is_(False)).count()
check(still == 0, "bir lookback süresi geçince doldurma haberi de expire edilir")


class FakeLLM:
    model = "fake"

    def call_tool(self, *, system, user, tool, max_tokens=4096):
        if tool["name"] == ARTICLE_ANALYSIS_TOOL["name"]:
            ids = [int(x) for x in re.findall(r"id=(\d+)", user)]
            return {"analyses": [{"id": i, "sentiment": 0.3, "event_type": "product", "risk_flags": [],
                                  "impact_horizon": "short", "relevance": 0.9, "rationale": "r.",
                                  "co_mentioned_entities": []} for i in ids]}
        if tool["name"] == TRANSLATION_TOOL["name"]:
            src, _ = json.JSONDecoder().raw_decode(user.split("JSON:\n", 1)[1])
            return {k: ([f"Türkçe {i}." for i, _x in enumerate(v)] if isinstance(v, list) else ("Türkçe metin." if v else ""))
                    for k, v in src.items()}
        if tool["name"] == ENTITY_ANALYSIS_TOOL["name"]:
            return {"headline_verdict": "Ocugen's trial update lifts the outlook.", "summary": "One trial update.",
                    "risk_score": 45, "stance": "neutral"}
        raise AssertionError(tool["name"])


print("== E: OCGN senaryosu ==")
p5 = FakeProvider([art("ocgn-deneme", 96)])  # yalnızca 4 günlük tek haber
ingest.get_provider_for = lambda e: p5
with SessionLocal() as s:
    e = Entity(name="OCUGEN INC", type="ticker", query="OCGN", active=True)
    q = Entity(name="Sessiz AŞ", type="keyword", query="Sessiz", active=True)
    s.add_all([e, q]); s.commit()
    ingest.fetch_for_entity(s, e)
    ingest.get_provider_for = lambda e: FakeProvider([])
    ingest.fetch_for_entity(s, q)
    oid, qid = e.id, q.id
asyncio.run(analyze_all_async(FakeLLM(), entity_ids={oid, qid}))
with session_scope() as s:
    c_tr = entity_card(s, s.get(Entity, oid), "tr")
    c_q = entity_card(s, s.get(Entity, qid), "tr")
check(c_tr.analysis is not None and c_tr.analysis.risk_score == 45, "OCGN eklendiği gün değerlendirme aldı")
check(c_q.analysis is None and c_q.no_analysis_reason == "few_news" and c_q.news_window_days == 7,
      f"doldurmadan sonra da haber yok → few_news, 7 gün ({c_q.no_analysis_reason}, {c_q.news_window_days})")
msgs = _few_news_messages({oid, qid})
check([(m["entity"], m["params"]["days"]) for m in msgs] == [("Sessiz AŞ", 7)], f"bildirim yalnızca sessiz şirket için, 7 gün ({msgs})")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
