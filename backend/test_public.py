"""Landing sayfası için oturumsuz uçlar: /public/stats ve /public/how-it-works (izole temp DB).

Doğrular:
  (A) oturum GEREKMEZ; yanıtlar 5 dk önbelleklenebilir (Cache-Control)
  (B) stats gerçek toplamlar: analyzed=True haber sayısı; tüm AI değerlendirmeleri
      (entity_analyses, her dil); farklı haber kaynağı (büyük/küçük harf ve boşluk farkı tek,
      boş kaynak sayılmaz); diller tr+en
  (C) how-it-works dili parametreden alır; seed dışı (kullanıcının eklediği) şirket — daha
      güncel analizi olsa bile — seçilmez; geçersiz dil 422
  (D) yanıtlarda kullanıcı bilgisi yok (yalnızca toplamlar / seed örneği)
Çalıştır: python test_public.py
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_public.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y" * 20,
                  NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
                  NEWSRADAR_LLM_PROVIDER="anthropic")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402
from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import Article, Entity, EntityAnalysis, User, UserWatchlist  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


now = datetime.now(timezone.utc)
init_db()


def analysis(eid, lang, age_h):
    return EntityAnalysis(entity_id=eid, language=lang, headline_verdict=f"Verdict {lang}.", risk_score=40,
                          sentiment_trend="stable", top_drivers=[], summary="s.", stance="bullish",
                          conviction="medium", what_to_verify=[], invalidation="i.",
                          created_at=now - timedelta(hours=age_h))


with session_scope() as s:
    nvda = Entity(name="NVIDIA", type="ticker", query="NVDA", active=True)
    tsla = Entity(name="Tesla", type="ticker", query="TSLA", active=True)
    priv = Entity(name="SecretStartup", type="keyword", query="SecretStartup", active=True)
    gone = Entity(name="OldCo", type="keyword", query="OldCo", active=False)
    lonely = Entity(name="NobodyWatches", type="keyword", query="NobodyWatches", active=True)
    s.add_all([nvda, tsla, priv, gone, lonely]); s.flush()
    u1 = User(username="alice", password_hash="x"); u2 = User(username="bob", password_hash="x")
    s.add_all([u1, u2]); s.flush()
    # izleme: nvda (2 kişi), priv (1), gone (pasif) → aktif ve izlenen = nvda + priv = 2
    s.add_all([UserWatchlist(user_id=u1.id, entity_id=nvda.id), UserWatchlist(user_id=u2.id, entity_id=nvda.id),
               UserWatchlist(user_id=u1.id, entity_id=priv.id), UserWatchlist(user_id=u2.id, entity_id=gone.id)])
    s.add_all([analysis(nvda.id, "tr", 3), analysis(nvda.id, "en", 3), analysis(priv.id, "en", 0)])
    # kaynaklar: "Src" ×2, " src " (aynı kaynak), "" (sayılmaz), "Other" → farklı kaynak = 2
    srcs = ["Src", "Src", " src ", "", "Other"]
    for i in range(5):
        s.add(Article(entity_id=nvda.id, url=f"http://n/{i}", url_hash=f"n{i}", source=srcs[i], title=f"NVDA {i}",
                      description="d", provider="finnhub", analyzed=i < 3, relevance=0.9, sentiment=0.5,
                      published_at=now - timedelta(hours=i + 1), fetched_at=now - timedelta(hours=i)))

with TestClient(app) as c:
    print("== A+B: /public/stats (oturumsuz)")
    r = c.get("/public/stats")
    check(r.status_code == 200, f"oturum olmadan 200 ({r.status_code})")
    check(r.headers.get("cache-control") == "public, max-age=300", f"Cache-Control: {r.headers.get('cache-control')}")
    d = r.json()
    check(d["articles_analyzed"] == 3, f"analiz edilen haber = 3 (analyzed=True) ({d['articles_analyzed']})")
    check(d["assessments"] == 3, f"AI değerlendirmesi = 3 (tüm diller) ({d['assessments']})")
    check(d["news_sources"] == 2, f"farklı haber kaynağı = 2 (boş sayılmaz, harf/boşluk farkı tek) ({d['news_sources']})")
    check(d["languages"] == ["tr", "en"], f"diller ({d['languages']})")
    check(set(d) == {"articles_analyzed", "assessments", "news_sources", "languages"}, f"yalnızca toplamlar ({sorted(d)})")

    print("== C+D: /public/how-it-works (oturumsuz)")
    for lang in ("tr", "en"):
        r = c.get("/public/how-it-works", params={"lang": lang})
        d = r.json()
        check(r.status_code == 200 and d["available"] and d["entity"]["query"] == "NVDA",
              f"lang={lang}: NVIDIA seçildi, seed dışı SecretStartup değil ({d.get('entity') and d['entity']['query']})")
        check(d["entity"]["analysis"]["headline_verdict"] == f"Verdict {lang}.", f"lang={lang}: değerlendirme o dilde")
    check(c.get("/public/how-it-works", params={"lang": "de"}).status_code == 422, "geçersiz dil → 422")
    body = c.get("/public/how-it-works", params={"lang": "en"}).text
    check("alice" not in body and "bob" not in body and "SecretStartup" not in body, "yanıtta kullanıcı/özel şirket yok")
    check(c.get("/how-it-works").status_code == 401, "oturumlu /how-it-works hâlâ korumalı (401)")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
