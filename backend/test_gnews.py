"""GNews entegrasyonu — sahte yanıtlar, gerçek istek yok, izole temp DB.

Doğrular:
  (A) anahtar yoksa anahtar kelimeli / ABD dışı şirket sessizce GDELT'ten; GNews'e istek yok
  (B) anahtar varsa birincil GNews: tam ifade sorgu, dil (en/de/tr), anahtar URL'de değil başlıkta,
      ayrıştırma, haberler "gnews" etiketiyle kaydedilir; ABD hissesi Finnhub'da kalır
  (C) GNews hata verirse GDELT yedeği; kullanıcıya uyarı yok
  (D) GNews hata + GDELT devre kesici açık → GDELT'e de istek yok, uyarı yok
  (E) istekler arası en az 1,1 sn (ücretsiz plan 1 istek/sn)
Çalıştır: python test_gnews.py
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_gnews.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
                  FINNHUB_API_KEY="fake-key", FMP_API_KEY="", NEWSAPI_KEY="", APP_SECRET="x",
                  NEWSRADAR_GNEWS_API_KEY="")

import app.providers.gdelt as gd  # noqa: E402
import app.providers.gnews as gn  # noqa: E402
from app import gdelt_breaker, ingest  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import Article, Entity  # noqa: E402
from app.providers import fallback_provider_for, get_provider_for  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


class Resp:
    def __init__(self, status=200, json_data=None, text=None):
        import json as _json
        self.status_code, self._j = status, json_data
        self.text = text if text is not None else _json.dumps(json_data or {})

    def json(self):
        if self._j is None:
            raise ValueError("not json")
        return self._j


GN = {"totalArticles": 2, "articles": [
    {"title": "Anthropic raises new funding", "description": "The AI company...", "url": "https://ex.com/a",
     "image": "https://ex.com/a.jpg", "publishedAt": "2026-10-26T08:00:00Z", "source": {"name": "Example", "url": "https://ex.com"}},
    {"title": "", "url": "https://ex.com/empty"},
    {"title": "Anthropic opens Berlin office", "description": "", "url": "https://ex.de/b",
     "publishedAt": "2026-10-25T18:30:00Z", "source": {"name": "Beispiel"}},
]}
GD = {"articles": [{"url": "https://gd.com/x", "title": "Anthropic GDELT story", "seendate": "20261026T090000Z", "domain": "gd.com"}]}

gn_calls, gd_calls, slept, clock = [], [], [], [1000.0]


def fake_gnews(status=200, data=GN, text=None):
    def get(url, params=None, headers=None, timeout=None):
        gn_calls.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {})})
        return Resp(status=status, json_data=data if status == 200 else None, text=text)
    return get


def fake_gdelt(url, params=None, timeout=None):
    gd_calls.append(params)
    return Resp(json_data=GD)


gn.httpx = type("H", (), {"get": staticmethod(fake_gnews()), "HTTPError": Exception})
gd.httpx.get = fake_gdelt
gd.time.monotonic = gn.time.monotonic = lambda: clock[0]
gd.time.sleep = gn.time.sleep = lambda x: (slept.append(x), clock.__setitem__(0, clock[0] + x))
gd.httpx.get = fake_gdelt


def set_key(v):
    os.environ["NEWSRADAR_GNEWS_API_KEY"] = v
    get_settings.cache_clear()


def reset():
    gn_calls.clear(); gd_calls.clear(); slept.clear(); gd._cache.clear(); gdelt_breaker.reset_memory()
    gn._last[0] = float("-inf"); gd._last_done[0] = float("-inf")


init_db()
with SessionLocal() as s:
    kw = Entity(name="Anthropic", type="keyword", query="Anthropic", active=True, language="de")
    thy = Entity(name="TURK HAVA YOLLARI AO", type="ticker", query="THYAO.IS", active=True)
    fr = Entity(name="LVMH", type="keyword", query="LVMH", active=True, language="fr")
    us = Entity(name="Tesla", type="ticker", query="TSLA", active=True)
    s.add_all([kw, thy, fr, us]); s.commit()
    ids = {e: e.id for e in (kw, thy, fr, us)}
since = datetime.now(timezone.utc) - timedelta(days=2)

print("== A: anahtar yok → GDELT")
set_key(""); reset()
with SessionLocal() as s:
    e = s.get(Entity, kw.id)
    check(get_provider_for(e).name == "gdelt" and fallback_provider_for(e) is None, "keyword → GDELT, yedek yok")
    check(get_provider_for(s.get(Entity, thy.id)).name == "gdelt", "ABD dışı hisse → GDELT")
    res = ingest.fetch_for_entity(s, e, manual=True); s.commit()
    check(gn_calls == [] and len(gd_calls) == 1 and res.fetched == 1 and res.warnings == [],
          f"GNews'e istek yok, GDELT'ten haber, uyarı yok ({len(gn_calls)}, {len(gd_calls)})")

print("== B: anahtar var → birincil GNews")
set_key("gn-secret-key"); reset()
with SessionLocal() as s:
    e = s.get(Entity, kw.id)
    check(get_provider_for(e).name == "gnews" and fallback_provider_for(e).name == "gdelt", "keyword → GNews, yedek GDELT")
    check(get_provider_for(s.get(Entity, thy.id)).name == "gnews", "ABD dışı hisse → GNews")
    check(get_provider_for(s.get(Entity, us.id)).name == "finnhub", "ABD hissesi → Finnhub")
    res = ingest.fetch_for_entity(s, e, manual=True); s.commit()
    call = gn_calls[0]
    check(call["params"]["q"] == '"Anthropic"' and call["params"]["in"] == "title,description"
          and call["params"]["max"] == 10 and call["params"]["sortby"] == "publishedAt", f"sorgu: tam ifade, başlık+açıklama ({call['params']})")
    check(call["params"]["lang"] == "de", "dil: entity dili (de)")
    check(call["headers"].get("X-Api-Key") == "gn-secret-key" and "apikey" not in call["params"]
          and "gn-secret-key" not in str(call["params"]), "anahtar başlıkta, URL'de değil")
    check(call["params"]["from"].endswith("Z"), "başlangıç zamanı ISO 8601 UTC")
    rows = s.query(Article).filter(Article.entity_id == kw.id, Article.provider == "gnews").all()
    check(res.fetched == 2 and len(rows) == 2 and gd_calls == [], f"2 haber (boş başlık atlandı), 'gnews' etiketi, GDELT'e gidilmedi ({res.fetched})")
    a = next(r for r in rows if r.url == "https://ex.com/a")
    check(a.source == "Example" and a.description == "The AI company..." and a.published_at is not None, "ayrıştırma: kaynak, açıklama, tarih")
    gn.httpx.get = staticmethod(fake_gnews()); gn_calls.clear()
    gn.GNewsProvider().fetch(s.get(Entity, thy.id), since)
    check(gn_calls[-1]["params"]["lang"] == "tr" and gn_calls[-1]["params"]["q"] == '"Turk Hava Yollari" OR "THYAO"',
          f"THYAO.IS: dil tr, ad + kök ({gn_calls[-1]['params']['q']})")
    gn.GNewsProvider().fetch(s.get(Entity, fr.id), since)
    check(gn_calls[-1]["params"]["lang"] == "en", "desteklenmeyen dil (fr) → en")

print("== C: GNews hata → GDELT yedeği, uyarı yok")
for status, body in ((500, '{"errors": ["Internal error"]}'), (403, '{"errors": ["You have reached your request limit for today"]}')):
    reset(); gn.httpx.get = staticmethod(fake_gnews(status=status, text=body))
    with SessionLocal() as s:
        s.query(Article).filter(Article.entity_id == kw.id).delete(); s.commit()
        res = ingest.fetch_for_entity(s, s.get(Entity, kw.id), manual=True); s.commit()
        n = s.query(Article).filter(Article.entity_id == kw.id, Article.provider == "gdelt").count()
    check(len(gn_calls) == 1 and len(gd_calls) == 1 and n == 1 and res.warnings == [],
          f"HTTP {status} → GDELT'ten 1 haber, kullanıcıya uyarı yok ({res.warnings})")
reset()
r = gn.GNewsProvider()
gn.httpx.get = staticmethod(fake_gnews(status=401, text='{"errors": ["Invalid API Key provided."]}'))
with SessionLocal() as s:
    w = r.fetch(s.get(Entity, kw.id), since).warning
check(w["code"] == "gnews_error" and w["params"]["status"] == 401 and "gn-secret-key" not in str(w),
      f"hata: kod + durum, anahtar metinde yok ({w['params']})")

print("== D: GNews hata + GDELT devre açık → istek yok, uyarı yok")
reset(); gn.httpx.get = staticmethod(fake_gnews(status=500, text="{}"))
with SessionLocal() as s:
    gdelt_breaker.persist(s); s.commit()
    res = ingest.fetch_for_entity(s, s.get(Entity, thy.id), manual=True); s.commit()
check(len(gn_calls) == 1 and gd_calls == [] and res.warnings == [], "GDELT'e istek yok, uyarı yok")
from app.db.models import ProviderSkip  # noqa: E402
with SessionLocal() as s:
    s.query(ProviderSkip).delete(); s.commit()
gdelt_breaker.reset_memory()

print("== E: istekler arası en az 1,1 sn")
reset(); gn.httpx.get = staticmethod(fake_gnews())
with SessionLocal() as s:
    gn.GNewsProvider().fetch(s.get(Entity, kw.id), since)
    gn.GNewsProvider().fetch(s.get(Entity, thy.id), since)
check(slept and abs(slept[-1] - 1.1) < 1e-9, f"ikinci istek 1,1 sn bekledi ({slept})")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
