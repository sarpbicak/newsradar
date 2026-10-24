"""Az haberli şirket: pencereden eski haber kaydedilmez, kart analiz yokluğunun NEDENİNİ
söyler, yenileme bildirimi sessiz kalmaz (izole temp DB, anahtarsız, sahte sağlayıcı).

Doğrular:
  (A) Finnhub `from` yalnızca gün alır → pencere başlangıcından eski haber gelir; kaydedilmez
      (too_old sayılır), pencere içindeki kaydedilir.
  (B) Kart: analiz yok + bekleyen haber yok → no_analysis_reason="few_news"; bekleyen haber
      varsa "pending"; news_window_days lookback'ten.
  (C) Kişisel yenileme bildirimi: analizi ve bekleyen haberi olmayan şirket için few_news
      mesajı (şirket adıyla); zamanlayıcı (entity_ids=None) için mesaj yok.
Çalıştır: python test_few_news.py
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_few_news.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
                  NEWSRADAR_LOOKBACK_HOURS="48")

import app.ingest as ingest  # noqa: E402
from app.api.serializers import entity_card  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import Article, Entity  # noqa: E402
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

    def is_available(self):
        return True

    def fetch(self, entity, since):
        return ProviderResult(provider="finnhub", articles=[
            FetchedArticle(url="http://x/old", title="Eski haber", published_at=now - timedelta(hours=60)),
            FetchedArticle(url="http://x/new", title="Yeni haber", published_at=now - timedelta(hours=3)),
        ])


init_db()
ingest.get_provider_for = lambda e: FakeProvider()
with SessionLocal() as s:
    ocgn = Entity(name="OCUGEN INC", type="ticker", query="OCGN", active=True)
    quiet = Entity(name="Sessiz Şirket", type="keyword", query="Sessiz", active=True)
    s.add_all([ocgn, quiet]); s.commit()
    print("== A: pencereden eski haber kaydedilmez")
    res = ingest.fetch_for_entity(s, ocgn)
    titles = [a.title for a in s.query(Article).filter(Article.entity_id == ocgn.id)]
    check(res.too_old == 1 and titles == ["Yeni haber"], f"eski atlandı, yeni kaydedildi (too_old={res.too_old}, {titles})")

    print("== B: kart analiz yokluğunun nedenini söyler")
    c = entity_card(s, ocgn, "tr")
    check(c.analysis is None and c.no_analysis_reason == "pending", f"bekleyen haber var → pending ({c.no_analysis_reason})")
    check(c.news_window_days == 2, f"pencere 48 sa → 2 gün ({c.news_window_days})")
    c2 = entity_card(s, quiet, "tr")
    check(c2.no_analysis_reason == "few_news", f"haber yok → few_news ({c2.no_analysis_reason})")
    # Bekleyen haber süresi geçince (expired) de few_news.
    for a in s.query(Article).filter(Article.entity_id == ocgn.id):
        a.expired = True
    s.commit()
    check(entity_card(s, ocgn, "tr").no_analysis_reason == "few_news", "tek haber süresi geçmiş → few_news")
    ids = {ocgn.id, quiet.id}

print("== C: yenileme bildirimi sessiz kalmaz")
msgs = _few_news_messages(ids)
codes = sorted((m["code"], m["entity"], m["params"]["days"]) for m in msgs)
check(codes == [("few_news", "Ocugen", 2), ("few_news", "Sessiz Şirket", 2)], f"iki şirket için few_news, görünen adla ({codes})")
check(_few_news_messages(None) == [], "zamanlayıcı yenilemesinde mesaj yok")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
