"""'Nasıl çalışır?' — gerçek örnek veri (izole temp DB, uydurma yok).

Doğrular:
  (A) güncel analizli seed şirket yoksa available=False (uydurma örnek üretilmez)
  (B) NVIDIA tercih edilir; kullanıcının eklediği (seed dışı) şirket — daha güncel analizi
      olsa bile — ASLA seçilmez (gizlilik)
  (C) başlıklar gerçek: etiketler makale duygusundan (olumlu/olumsuz/nötr), 'alakasız'
      LLM'in elediği gerçek kayıttan; en fazla 4
  (D) haftalık sayı = son 7 günde toplanan + elenen; kaynak adları gerçek provider'lardan
  (E) pipeline alakasız makaleyi silerken DiscardedArticle kaydı bırakır (entity başı sınırlı)
Çalıştır: python test_how_it_works.py
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_how.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y" * 20,
                  NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
                  NEWSRADAR_LLM_PROVIDER="anthropic")

from fastapi.testclient import TestClient  # noqa: E402

from app.analysis.pipeline import _apply_article_results  # noqa: E402
from app.api.main import app  # noqa: E402
from app.api.routes_auth import get_current_user  # noqa: E402
from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import Article, DiscardedArticle, Entity, EntityAnalysis  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


class U:
    id, is_admin, is_anonymous, language = 1, False, False, "en"


now = datetime.now(timezone.utc)
init_db()
app.dependency_overrides[get_current_user] = lambda: U()


def analysis(eid, lang="en", age_h=1):
    return EntityAnalysis(entity_id=eid, language=lang, headline_verdict="Real verdict.",
                          risk_score=40, sentiment_trend="stable", top_drivers=[], summary="s.",
                          stance="bullish", conviction="medium", what_to_verify=[], invalidation="i.",
                          created_at=now - timedelta(hours=age_h))


with TestClient(app) as c:
    print("== A: örnek yoksa uydurma yok ==")
    d = c.get("/how-it-works").json()
    check(d["available"] is False and d["entity"] is None and d["headlines"] == [], f"available=False ({d})")

    with session_scope() as s:
        tsla = Entity(name="Tesla", type="ticker", query="TSLA", active=True)
        nvda = Entity(name="NVIDIA", type="ticker", query="NVDA", active=True)
        priv = Entity(name="SecretStartup", type="keyword", query="SecretStartup", active=True)
        s.add_all([tsla, nvda, priv]); s.flush()
        s.add_all([analysis(tsla.id, age_h=1), analysis(nvda.id, age_h=5), analysis(priv.id, age_h=0)])
        for i, (sent, prov) in enumerate([(0.6, "finnhub"), (-0.5, "newsapi"), (0.0, "finnhub"),
                                          (0.4, "finnhub"), (0.3, "finnhub")]):
            s.add(Article(entity_id=nvda.id, url=f"http://n/{i}", url_hash=f"n{i}", source="Src",
                          title=f"NVDA real headline {i}", description="d", provider=prov,
                          analyzed=True, relevance=0.9, sentiment=sent,
                          published_at=now - timedelta(hours=i + 1), fetched_at=now - timedelta(hours=i)))
        s.add(Article(entity_id=nvda.id, url="http://n/old", url_hash="nold", source="Src",
                      title="old", description="d", provider="finnhub", analyzed=False,
                      fetched_at=now - timedelta(days=10)))
        s.add(DiscardedArticle(entity_id=nvda.id, title="Unrelated chip story", source="Src",
                               provider="newsapi", relevance=0.1,
                               published_at=now - timedelta(hours=2, minutes=30), fetched_at=now - timedelta(hours=2)))
        nid = nvda.id

    print("== B: şirket seçimi ==")
    d = c.get("/how-it-works").json()
    check(d["available"] and d["entity"]["query"] == "NVDA", f"NVIDIA seçildi ({d['entity'] and d['entity']['query']})")
    check(d["entity"]["query"] != "SecretStartup", "seed dışı (kullanıcı eklemesi) şirket seçilmedi")
    check(d["entity"]["analysis"]["headline_verdict"] == "Real verdict.", "kart gerçek değerlendirmeden")

    print("== C: başlıklar ==")
    labels = [h["label"] for h in d["headlines"]]
    titles = [h["title"] for h in d["headlines"]]
    check(len(d["headlines"]) == 4, f"4 başlık ({len(d['headlines'])})")
    check({"positive", "negative", "irrelevant"} <= set(labels), f"olumlu + olumsuz + alakasız ({labels})")
    check("Unrelated chip story" in titles and all(t.startswith("NVDA real headline") or t == "Unrelated chip story" for t in titles),
          "başlıklar DB'den (uydurma yok)")
    check(d["headlines"] == sorted(d["headlines"], key=lambda h: h["published_at"], reverse=True), "en yeni önce")

    print("== D: sayılar ==")
    check(d["articles_week"] == 6, f"son 7 gün: 5 makale + 1 elenen = 6 ({d['articles_week']})")
    check(d["providers"] == ["Finnhub", "NewsAPI"], f"kaynaklar gerçek ({d['providers']})")

    print("== B2: kullanıcının dili yoksa / analiz eskiyse ==")
    U.language = "tr"
    check(c.get("/how-it-works").json()["available"] is False, "TR analizi yok → available=False")
    U.language = "en"

print("== E: pipeline elenen kaydı ==")
with session_scope() as s:
    a = Article(entity_id=nid, url="http://n/x", url_hash="nx", source="Src", title="Off-topic piece",
                description="d", provider="newsapi", analyzed=False, published_at=now)
    s.add(a); s.flush()
    aid = a.id
res = _apply_article_results(nid, [{"analyses": [{"id": aid, "sentiment": 0, "event_type": "other",
                                                   "risk_flags": [], "impact_horizon": "short",
                                                   "relevance": 0.05, "rationale": "r.",
                                                   "co_mentioned_entities": []}]}])
with session_scope() as s:
    gone = s.get(Article, aid) is None
    rec = s.query(DiscardedArticle).filter(DiscardedArticle.title == "Off-topic piece").one_or_none()
check(res["discarded"] == 1 and gone and rec is not None and abs(rec.relevance - 0.05) < 1e-9,
      "alakasız makale silindi, kısa kaydı kaldı (relevance 0.05)")
app.dependency_overrides.clear()

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
