"""ABD dışı şirketler + GDELT haberleri (izole temp DB, anahtarsız, ağ yok: httpx sahte).

Doğrular:
  (A) sembol → borsa/ülke/para birimi (SAP.DE, SIE.DE, ASELS.IS, THYAO.IS, 7203.T, ASML.AS; ABD,
      BRK.B ABD sınıf hissesi), sembol kökü
  (B) arama: sonuçlarda borsa · ülke · para birimi; ABD önde; bilinmeyen borsa son eki atılır
  (C) yönlendirme: ABD hisse → Finnhub haber; ABD dışı hisse + keyword → GDELT; NewsAPI yalnızca
      NEWSRADAR_NEWSAPI_ENABLED=on; ABD dışında fiyat/analist yuvası boş
  (D) kaynak yokken: ABD dışı hisse için fiyat/analist sağlayıcısına HİÇ gidilmez; kart
      exchange/country/currency dolu, fiyat None ("veri yok")
  (E) GDELT: sorgu (ifade + en/de/tr dil filtresi), ayrıştırma, istekler arası bekleme, önbellek,
      hız sınırı / düz metin hata → kibar uyarı
  (F) GDELT gürültüsü mevcut alaka filtresiyle (LLM relevance < 0.3) elenir; başlık ön-filtresi yok
Çalıştır: python test_intl.py
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_intl.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
                  FINNHUB_API_KEY="fake-key", FMP_API_KEY="fake-key", NEWSAPI_KEY="", APP_SECRET="x",
                  NEWSRADAR_GNEWS_API_KEY="")

import app.providers.gdelt as gd  # noqa: E402
from app import gdelt_breaker  # noqa: E402
import app.symbol_search as ss  # noqa: E402
from app import analyst as analyst_mod, prices as prices_mod  # noqa: E402
from app.analysis.pipeline import _prefilter  # noqa: E402
from app.api.serializers import entity_card  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import Article, Entity  # noqa: E402
from app.markets import base_symbol, market_of  # noqa: E402
from app.providers import analyst_supported, get_provider_for, price_provider_for  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


class Resp:
    def __init__(self, status=200, json_data=None, text=None):
        self.status_code, self._j = status, json_data
        import json as _json
        self.text = text if text is not None else _json.dumps(json_data or {})

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        if self._j is None:
            raise ValueError("not json")
        return self._j


print("== A: sembol → pazar")
cases = {"SAP.DE": ("XETRA", "Almanya", "Germany", "EUR"), "SIE.DE": ("XETRA", "Almanya", "Germany", "EUR"),
         "ASELS.IS": ("Borsa İstanbul", "Türkiye", "Türkiye", "TRY"), "THYAO.IS": ("Borsa İstanbul", "Türkiye", "Türkiye", "TRY"),
         "7203.T": ("Tokyo", "Japonya", "Japan", "JPY"), "ASML.AS": ("Euronext Amsterdam", "Hollanda", "Netherlands", "EUR")}
for sym, (ex, ctr, cen, cur) in cases.items():
    m = market_of(sym)
    check((m.exchange, m.country("tr"), m.country("en"), m.currency, m.is_us) == (ex, ctr, cen, cur, False), f"{sym} → {ex} · {ctr} · {cur}")
check(market_of("TSLA").is_us and market_of("TSLA").currency == "USD", "TSLA → ABD, USD")
check(market_of("BRK.B").is_us, "BRK.B (sınıf hissesi) → ABD")
check(base_symbol("THYAO.IS") == "THYAO" and base_symbol("BRK.B") == "BRK.B", "sembol kökü")

print("== B: arama")
FINNHUB_SEARCH = {"result": [
    {"symbol": "SAP.DE", "description": "SAP SE", "type": "Common Stock"},
    {"symbol": "SAP", "description": "SAP SE-SPONSORED ADR", "type": "ADR"},
    {"symbol": "SAPX.ZZ", "description": "Bilinmeyen borsa", "type": "Common Stock"},
    {"symbol": "7203.T", "description": "TOYOTA MOTOR CORP", "type": "Common Stock"},
    {"symbol": "SAP-W", "description": "Warrant", "type": "Warrant"},
]}
ss.httpx.get = lambda url, params=None, timeout=None: Resp(json_data=FINNHUB_SEARCH)
res = ss.search_symbols("SAP")
by = {r["symbol"]: r for r in res}
check(res[0]["symbol"] == "SAP" and res[0]["us_supported"], "ABD sonucu (veri olan) önde")
check(by["SAP.DE"]["exchange_name"] == "XETRA" and by["SAP.DE"]["country_tr"] == "Almanya"
      and by["SAP.DE"]["country_en"] == "Germany" and by["SAP.DE"]["currency"] == "EUR" and not by["SAP.DE"]["us_supported"],
      "SAP.DE: XETRA · Almanya · EUR")
check(by["7203.T"]["currency"] == "JPY" and by["7203.T"]["suggested_language"] == "en", "7203.T: Tokyo, JPY")
check("SAPX.ZZ" not in by and "SAP-W" not in by, "bilinmeyen borsa son eki ve hisse olmayan atıldı")

print("== C/D: yönlendirme ve kaynak yokken")
init_db()
with SessionLocal() as s:
    us = Entity(name="Tesla", type="ticker", query="TSLA", active=True)
    sap = Entity(name="SAP SE", type="ticker", query="SAP.DE", active=True)
    thy = Entity(name="TURK HAVA YOLLARI AO", type="ticker", query="THYAO.IS", active=True)
    kw = Entity(name="OpenAI", type="keyword", query="OpenAI", active=True)
    s.add_all([us, sap, thy, kw]); s.commit()
    check(get_provider_for(us).name == "finnhub", "ABD hisse → Finnhub company-news")
    check(get_provider_for(sap).name == "gdelt" and get_provider_for(kw).name == "gdelt", "ABD dışı hisse ve keyword → GDELT")
    check(price_provider_for(sap) is None and not analyst_supported(sap), "ABD dışı: fiyat ve analist yuvası boş")
    check(price_provider_for(us) is not None and analyst_supported(us), "ABD: mevcut fiyat/analist kaynakları")
    os.environ["NEWSRADAR_NEWSAPI_ENABLED"] = "on"; get_settings.cache_clear()
    check(get_provider_for(kw).name == "newsapi", "NEWSRADAR_NEWSAPI_ENABLED=on → keyword NewsAPI")
    os.environ["NEWSRADAR_NEWSAPI_ENABLED"] = "off"; get_settings.cache_clear()
    ids = {us.id, sap.id, thy.id}

calls = []


class FakePrice:
    name = "finnhub_price"

    def is_available(self):
        return True

    def quote(self, e):
        calls.append(("price", e.query))
        from app.providers.base import PriceQuote, PriceResult
        return PriceResult(provider=self.name, quote=PriceQuote(price=300.0, change_percent=1.0))


class FakeAnalyst:
    name = "fake_analyst"

    def is_available(self):
        return True

    def fetch(self, e):
        calls.append(("analyst", e.query))
        from app.providers.base import AnalystResult
        return AnalystResult(provider=self.name)


import app.providers.registry as reg  # noqa: E402
reg._PRICE_PROVIDER = FakePrice()
prices_mod.price_provider_for = reg.price_provider_for
analyst_mod.get_analyst_provider = lambda: FakeAnalyst()
analyst_mod.get_target_provider = lambda: FakeAnalyst()
prices_mod.refresh_prices(ids)
analyst_mod.refresh_analyst(ids)
check(("price", "TSLA") in calls and not any(q in ("SAP.DE", "THYAO.IS") for _, q in calls),
      f"ABD dışı hisse için fiyat/analist kaynağına hiç gidilmedi ({calls})")
with SessionLocal() as s:
    c_tr = entity_card(s, s.get(Entity, ids and sap.id), "tr")
    c_en = entity_card(s, s.get(Entity, sap.id), "en")
    c_us = entity_card(s, s.get(Entity, us.id), "tr")
check(c_tr.exchange == "XETRA" and c_tr.country == "Almanya" and c_en.country == "Germany"
      and c_tr.currency == "EUR" and c_tr.us_market is False, "kart: XETRA · Almanya/Germany · EUR, us_market=False")
check(c_tr.price is None and c_tr.analyst is None, "kart: fiyat ve analist yok (arayüz 'veri yok')")
check(c_us.us_market is True and c_us.price == 300.0 and c_us.currency == "USD", "ABD kartı: fiyat var, USD")
check(c_tr.market == "DE" and c_us.market == "US", "kart: pazar kodu (arayüz borsa adını dile göre çevirir)")

print("== E: GDELT")
with SessionLocal() as s:
    sap_e, thy_e, kw_e = s.get(Entity, sap.id), s.get(Entity, thy.id), s.get(Entity, kw.id)
    check(gd.search_terms(kw_e) == ["OpenAI"], "keyword → kendi sorgusu")
    check(gd.search_terms(sap_e) == ["SAP"], f"SAP.DE → okunur ad, 3 harfli kök eklenmez ({gd.search_terms(sap_e)})")
    check(gd.search_terms(thy_e) == ["Turk Hava Yollari", "THYAO"], f"THYAO.IS → ad + kök ({gd.search_terms(thy_e)})")
    q = gd.build_query(gd.search_terms(thy_e))
    check(q == '("Turk Hava Yollari" OR "THYAO") (sourcelang:english OR sourcelang:german OR sourcelang:turkish)', f"sorgu: {q}")
    GD = {"articles": [
        {"url": "https://ex.com/a", "title": "OpenAI unveils new model", "seendate": "20261024T103000Z", "domain": "ex.com", "language": "English"},
        {"url": "https://ex.de/b", "title": "Börse: Chipwerte fallen", "seendate": "20261024T090000Z", "domain": "ex.de", "language": "German"},
        {"url": "", "title": "boş url"},
    ]}
    sent, slept, clock = [], [], [1000.0]
    gd.time.monotonic = lambda: clock[0]
    gd.time.sleep = lambda x: (slept.append(x), clock.__setitem__(0, clock[0] + x))
    gd._last_done[0] = float("-inf")
    gd._cache.clear()
    RESP_S = 3.0  # her GDELT yanıtı 3 sn sürsün (sahte saat ilerler)

    def fake_get(url, params=None, timeout=None):
        sent.append(params)
        clock[0] += RESP_S
        return Resp(json_data=GD)
    gd.httpx.get = fake_get
    since = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
    r1 = gd.GdeltProvider().fetch(kw_e, since)
    check(len(r1.articles) == 2 and r1.articles[0].source == "ex.com"
          and r1.articles[0].published_at == datetime(2026, 10, 24, 10, 30, tzinfo=timezone.utc), "ayrıştırma: url/başlık/kaynak/tarih")
    check(sent[0]["startdatetime"] == "20261022120000" and sent[0]["mode"] == "artlist" and sent[0]["format"] == "json"
          and "sourcelang:turkish" in sent[0]["query"], "istek: başlangıç zamanı, artlist/json, dil filtresi")
    check(slept == [], "ilk istek beklemez")
    gd.GdeltProvider().fetch(kw_e, since)
    check(len(sent) == 1, "aynı sorgu 10 dk önbellekten (ikinci istek yok)")
    gd.GdeltProvider().fetch(sap_e, since)
    check(len(sent) == 2 and slept == [5.0],
          f"aralık önceki yanıtın BİTİŞİNDEN 5 sn (yanıt 3 sn sürse de; eskiden 2 sn beklerdi) ({slept})")

    print("== E2: hız sınırı → devre kesici (yeniden deneme yok, 6 saat istek yok)")
    LIMIT = "Please limit requests to one every 5 seconds or contact ..."
    seq = []

    def seq_get(url, params=None, timeout=None):
        sent.append(params)
        clock[0] += RESP_S
        return seq.pop(0)
    gd.httpx.get = seq_get
    gd._cache.clear(); slept.clear(); sent.clear()
    seq[:] = [Resp(status=200, text=LIMIT)]
    r = gd.GdeltProvider().fetch(thy_e, since)
    check(len(sent) == 1 and r.warning and r.warning["code"] == "gdelt_blocked" and not r.articles,
          f"hız sınırı yanıtı → yeniden denenmez, devre kesici kodu ({len(sent)} istek)")
    check(gdelt_breaker.open_in_memory(), "devre bu süreçte hemen açık")
    r = gd.GdeltProvider().fetch(sap_e, since + timedelta(hours=1))
    check(len(sent) == 1 and r.warning["code"] == "gdelt_blocked", "devre açıkken başka şirket için de istek yok")
    gdelt_breaker.reset_memory()
    gd.httpx.get = lambda url, params=None, timeout=None: Resp(status=200, text="The specified phrase is too short.")
    r = gd.GdeltProvider().fetch(thy_e, since + timedelta(hours=1))
    check(r.warning and r.warning["code"] == "gdelt_error" and not gdelt_breaker.open_in_memory(),
          "düz metin hata → gdelt_error, devre açılmaz")

    print("== E2b: alım (ingest) — kalıcı devre, uyarı yok, kart notu, admin durumu")
    from app import ingest as ingest_mod  # noqa: E402
    gd.httpx.get = seq_get; gd._cache.clear(); sent.clear()
    seq[:] = [Resp(status=429, text="Too many requests")]
    res = ingest_mod.fetch_for_entity(s, kw_e, manual=True); s.commit()
    check(len(sent) == 1 and res.warnings == [] and res.fetched == 0,
          f"429 → uyarı yok (her yenilemede tekrar etmesin) ({res.warnings})")
    snap = gdelt_breaker.snapshot()
    hours = (snap["until"] - snap["last_429_at"]).total_seconds() / 3600 if snap["until"] and snap["last_429_at"] else 0
    check(snap["open"] and snap["last_429_at"] is not None and abs(hours - 6) < 0.01,
          f"admin: devre açık, son 429 zamanı, 6 saat ({hours:.2f})")
    gdelt_breaker.reset_memory()   # süreç yeniden başladı: durum DB'den okunur
    res = ingest_mod.fetch_for_entity(s, thy_e, manual=True)
    check(len(sent) == 1 and res.warnings == [], "yeniden başlatmadan sonra da (DB) istek yok, uyarı yok")
    c_kw = entity_card(s, kw_e, "tr"); c_us = entity_card(s, s.get(Entity, us.id), "tr")
    check(c_kw.news_paused and not c_us.news_paused, "kart: GDELT'li şirkette sakin not (news_paused), ABD hissesinde yok")
    from app.db.models import ProviderSkip  # noqa: E402
    s.get(ProviderSkip, gdelt_breaker.KEY).until = datetime.now(timezone.utc) - timedelta(minutes=1); s.commit()
    gdelt_breaker.reset_memory()
    gd.httpx.get = fake_get; gd._cache.clear()
    res = ingest_mod.fetch_for_entity(s, kw_e, manual=True); s.commit()
    check(len(sent) == 2 and res.fetched == 2 and not gdelt_breaker.is_open(s) and not entity_card(s, kw_e, "tr").news_paused,
          "süre dolunca istekler yeniden başlar, not kalkar")
    os.environ["NEWSRADAR_GDELT_BLOCK_HOURS"] = "0.5"; get_settings.cache_clear()
    until = gdelt_breaker.trip_memory()
    check(abs((until - datetime.now(timezone.utc)).total_seconds() - 1800) < 5, "NEWSRADAR_GDELT_BLOCK_HOURS=0.5 → 30 dk")
    gdelt_breaker.reset_memory()
    os.environ.pop("NEWSRADAR_GDELT_BLOCK_HOURS"); get_settings.cache_clear()

    print("== E3: aralık ortam değişkeninden; yenileme süresine etkisi")
    os.environ["NEWSRADAR_GDELT_INTERVAL_SECONDS"] = "2"; get_settings.cache_clear()
    gd.httpx.get = fake_get
    gd._cache.clear(); slept.clear(); sent.clear(); gd._last_done[0] = clock[0]
    gd.GdeltProvider().fetch(kw_e, since + timedelta(hours=3))
    check(slept == [2.0], f"NEWSRADAR_GDELT_INTERVAL_SECONDS=2 → 2 sn ({slept})")
    os.environ["NEWSRADAR_GDELT_INTERVAL_SECONDS"] = "5"; get_settings.cache_clear()
    # 4 GDELT şirketi, yanıt 3 sn: toplam = 4×3 + 3×5 = 27 sn (aralık yanıt bitişinden).
    gd.httpx.get = fake_get; gd._cache.clear(); gd._last_done[0] = float("-inf")
    t0 = clock[0]
    for i, e in enumerate([kw_e, sap_e, thy_e, kw_e]):
        gd.GdeltProvider().fetch(e, since + timedelta(hours=10 + i))
    check(abs((clock[0] - t0) - 27.0) < 1e-6, f"4 GDELT şirketi (yanıt 3 sn): yenilemeye ~27 sn ({clock[0] - t0:.0f} sn)")

print("== E4: eşzamanlı çağrılar tek sırada (gerçek saat)")
import threading  # noqa: E402
import time as _real_time  # noqa: E402
import importlib  # noqa: E402

gd.time = importlib.import_module("time")  # sahte saati geri al
os.environ["NEWSRADAR_GDELT_INTERVAL_SECONDS"] = "0.05"; get_settings.cache_clear()
active, peak = [0], [0]
lk = threading.Lock()


def slow_get(url, params=None, timeout=None):
    with lk:
        active[0] += 1; peak[0] = max(peak[0], active[0])
    _real_time.sleep(0.03)
    with lk:
        active[0] -= 1
    return Resp(json_data=GD)


gd.httpx.get = slow_get; gd._cache.clear(); gd._last_done[0] = float("-inf")
with SessionLocal() as s:
    ents = [s.get(Entity, x) for x in (kw.id, sap.id, thy.id)]
    threads = [threading.Thread(target=gd.GdeltProvider().fetch, args=(e, since + timedelta(hours=20 + i))) for i, e in enumerate(ents * 2)]
    for th in threads: th.start()
    for th in threads: th.join()
check(peak[0] == 1, f"aynı anda en fazla 1 GDELT isteği ({peak[0]})")
os.environ["NEWSRADAR_GDELT_INTERVAL_SECONDS"] = "5"; get_settings.cache_clear()

print("== F: GDELT gürültüsü → mevcut alaka filtresi (LLM relevance < 0.3)")
import asyncio  # noqa: E402
import re  # noqa: E402

from app.analysis.pipeline import analyze_all_async  # noqa: E402
from app.analysis.schemas import ARTICLE_ANALYSIS_TOOL  # noqa: E402
from app.db.models import DiscardedArticle  # noqa: E402

with SessionLocal() as s:
    kw_e = s.get(Entity, kw.id)
    now = datetime.now(timezone.utc)
    titles = ["OpenAI unveils new model", "Börse: Chipwerte fallen", "Altman joins board of energy startup"]
    for i, title in enumerate(titles):
        s.add(Article(entity_id=kw_e.id, url=f"http://x/{i}", url_hash=f"x{i}", title=title, source="s",
                      description="", provider="gdelt", published_at=now - timedelta(hours=i + 1)))
    s.commit()
    payload, pre = _prefilter(s, kw_e, 50)
check(len(payload) == 3 and pre == 0, f"GDELT haberleri ön-filtrede elenmez, LLM'e gider ({len(payload)}, {pre})")


class RelevanceLLM:
    model = "fake"

    def call_tool(self, *, system, user, tool, max_tokens=4096):
        if tool["name"] != ARTICLE_ANALYSIS_TOOL["name"]:
            return {"headline_verdict": "v.", "summary": "s."}
        out = []
        for line in user.splitlines():
            m = re.search(r"id=(\d+)", line)
            if m:  # "Chipwerte" haberi OpenAI ile ilgisiz → düşük alaka
                out.append({"id": int(m.group(1)), "sentiment": 0.1, "event_type": "other", "risk_flags": [],
                            "impact_horizon": "short", "relevance": 0.1 if "Chipwerte" in line else 0.8,
                            "rationale": "r.", "co_mentioned_entities": []})
        return {"analyses": out}


t = asyncio.run(analyze_all_async(RelevanceLLM(), entity_ids={kw.id}))
with SessionLocal() as s:
    kept = [a.title for a in s.query(Article).filter(Article.entity_id == kw.id, Article.analyzed.is_(True))]
    dropped = [d.title for d in s.query(DiscardedArticle).filter(DiscardedArticle.entity_id == kw.id)]
check(dropped == ["Börse: Chipwerte fallen"] and len(kept) == 2, f"alakasız GDELT haberi elendi, ilgili 2 haber kaldı ({kept}, {dropped})")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
