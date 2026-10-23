"""İçerik kalitesi — şablon çöküşü + dil sızıntısı (gerçek API yok, izole temp DB).

Doğrular:
  (A) yeni yasaklı kalıplar: EN 'news is mixed', 'mixed news', 'is mixed:/,', 'news (is) balanced';
      TR 'haberler karışık', 'karışık haber', 'haber akışı dengeli' (Türkçe büyük/küçük harf)
  (B) prompt: "Haberlerin karışık olduğunu söyleme…" (TR) + EN eşdeğeri + 2 örnek; çıktı dili
      direktifi yasak kelimeleri sayıyor
  (C) dil sızıntısı tespiti: TR'de already/however/…/the (tam kelime), EN'de Türkçe kelime/harf;
      özel adlar (The Verge, Türk Telekom, Koç) tetiklemez
  (D) sızıntı → mevcut tek seferlik tekrar denemesi notla tetiklenir (TR ve EN)
  (E) aynı taramada >3 entity'nin hükmü aynı ilk 3 kelimeyle başlarsa uyarı loglanır (3'te değil)
Çalıştır: python test_content_quality.py
"""
import asyncio
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_content_quality.db")
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

from app.analysis.pipeline import _assess_entity_with_recovery, analyze_all_async  # noqa: E402
from app.analysis.prompts import entity_assessment_rules, output_language_directive  # noqa: E402
from app.analysis.schemas import ENTITY_ANALYSIS_TOOL  # noqa: E402
from app.analysis.text_quality import (  # noqa: E402
    banned_phrase_hits, headline_openings, language_leak_hits,
)
from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import Article, Entity  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


print("== A: yeni yasaklı kalıplar ==")
for t, exp in [
    ("Tesla news is mixed after the delivery miss.", ["news is mixed"]),
    ("Mixed news: Azure grew but capex rose.", ["mixed news"]),
    ("The picture is mixed: margins fell.", ["is mixed:"]),
    ("Sentiment is mixed, with chips strong.", ["is mixed,"]),
    ("News is balanced between AI wins and China risk.", ["news is balanced"]),
    ("Overall news balanced for Apple.", ["news balanced"]),
    ("NVIDIA NEWS IS MIXED.", ["news is mixed"]),
]:
    check(banned_phrase_hits(t, "en") == exp, f"EN: {t!r} → {banned_phrase_hits(t, 'en')}")
for t, exp in [
    ("Haberler karışık, marjlar baskıda.", ["haberler karışık"]),
    ("HABERLER KARIŞIK.", ["haberler karışık"]),
    ("Karışık haberler: Azure büyüdü ama harcama arttı.", ["karışık haberler"]),
    ("KARIŞIK HABER akışı sürüyor.", ["karışık haber"]),
    ("Haber akışı dengeli görünüyor.", ["haber akışı dengeli"]),
    ("Haber akışı oldukça DENGELİ.", ["haber akışı oldukça dengeli"]),
]:
    check(banned_phrase_hits(t, "tr") == exp, f"TR: {t!r} → {banned_phrase_hits(t, 'tr')}")
for t, lang in [
    ("Analysts mixed their targets after the call.", "en"),
    ("Mixed-signal chips drove the quarter.", "en"),
    ("The balance sheet is strong.", "en"),
    ("Karışım tesisi açıldı; denge bozulmadı.", "tr"),
]:
    check(banned_phrase_hits(t, lang) == [], f"temiz: {t!r}")

print("== B: prompt talimatları ==")
rt, re_ = entity_assessment_rules("tr"), entity_assessment_rules("en")
check("Haberlerin karışık olduğunu söyleme. Somut gerilimi tek cümlede anlat: hangi olumlu "
      "gelişme, hangi olumsuz gelişmeyle çatışıyor." in rt, "TR kuralı birebir var")
check("NEVER SAY THE NEWS IS MIXED" in re_ and "which positive development clashes with which "
      "negative one" in re_, "EN eşdeğeri var")
check(rt.count("İyi örnekler") == 1 and rt.count(" / '") == 1 and re_.count(" / '") == 1,
      "her iki dilde 2 iyi örnek")
check("'karışık haber(ler)'" in rt and "'mixed news'" in re_, "yeni yasaklı ifadeler prompt listesinde")
dtr, den = output_language_directive("tr"), output_language_directive("en")
check(all(w in dtr for w in ("already", "however", "although", "because", "while", "still",
                              "which", "also", "the")) and "YALNIZCA Türkçe" in dtr,
      "TR direktifi yasak İngilizce kelimeleri sayıyor")
check("YALNIZCA İngilizce" in den and "ğ, ş, ı, ü, ö, ç" in den, "EN direktifi Türkçe harfleri yasaklıyor")
check("10) DİL" in rt and "10) LANGUAGE" in re_, "kural bloğunda da dil kuralı (10)")

print("== C: dil sızıntısı tespiti ==")
check(language_leak_hits("Ancak piyasanın already tepki vermesi riskli.", "tr") == ["already"],
      "TR: 'already' yakalandı")
check(language_leak_hits("However, marjlar düştü; still güçlü, which önemli, also, because, "
                         "although, while.", "tr")
      == ["however", "still", "which", "also", "because", "although", "while"],
      "TR: tüm liste tam kelime olarak")
check(language_leak_hits("Hisse the sınırda.", "tr") == ["the"], "TR: küçük 'the' yakalandı")
check(language_leak_hits("The Verge'e göre Theranos davası, Stillwater ve Whilestar.", "tr") == [],
      "TR: 'The Verge' (özel ad) ve kelime içi eşleşme tetiklemez")
check(language_leak_hits("Revenue rose ve margins improved için.", "en") == ["ve", "için"],
      "EN: Türkçe kelimeler yakalandı")
check(language_leak_hits("The stock fell after şirketin guidance.", "en") == ["şirketin"],
      "EN: Türkçe harfli kelime yakalandı")
check(language_leak_hits("Türk Telekom and Koç Holding rose; Zürich office opened.", "en") == [],
      "EN: büyük harfli özel adlar tetiklemez")

print("== D: sızıntı → tek seferlik tekrar denemesi ==")


class Fake:
    model = "fake"

    def __init__(self, outs):
        self.outs, self.users = list(outs), []

    def call_tool(self, *, system, user, tool, max_tokens=4096):
        self.users.append(user)
        return self.outs.pop(0)


build = lambda items: "PROMPT"  # noqa: E731
LEAK_TR = {"headline_verdict": "Azure büyüdü.", "summary": "Piyasanın already tepki vermesi olası.",
           "top_drivers": ["Azure yüzde 43 büyüdü."]}
OK_TR = {"headline_verdict": "Azure büyüdü.", "summary": "Piyasanın zaten tepki vermesi olası.",
         "top_drivers": ["Azure yüzde 43 büyüdü."]}
c = Fake([LEAK_TR, OK_TR])
data, _ = _assess_entity_with_recovery(c, build, [{"x": 1}], "Sızıntı", "tr")
check(len(c.users) == 2 and data == OK_TR, "TR sızıntı → bir kez yeniden, temiz yanıt kullanıldı")
check("İngilizce kelime karıştı ('already')" in c.users[1], "not bulunan kelimeyi söylüyor")
c = Fake([{"headline_verdict": "Azure büyüdü.", "summary": "s.",
           "what_to_verify": ["Bulut gelirinin still arttığını doğrula."]}, OK_TR])
_assess_entity_with_recovery(c, build, [{"x": 1}], "Liste", "tr")
check(len(c.users) == 2, "liste maddesindeki sızıntı da tetikler")
LEAK_EN = {"headline_verdict": "Azure grew 43%.", "summary": "Margins fell ve capex rose."}
OK_EN = {"headline_verdict": "Azure grew 43%.", "summary": "Margins fell and capex rose."}
c = Fake([LEAK_EN, OK_EN])
data, _ = _assess_entity_with_recovery(c, build, [{"x": 1}], "EN", "en")
check(len(c.users) == 2 and data == OK_EN and "mixed Turkish" in c.users[1],
      "EN'de Türkçe kelime → İngilizce notla bir kez yeniden")
c = Fake([LEAK_TR, LEAK_TR])
data, _ = _assess_entity_with_recovery(c, build, [{"x": 1}], "İnatçı", "tr")
check(len(c.users) == 2 and data == LEAK_TR, "yine sızıntı → üçüncü çağrı YOK (döngü yok)")
c = Fake([OK_TR])
_assess_entity_with_recovery(c, build, [{"x": 1}], "Temiz", "tr")
check(len(c.users) == 1, "temiz metin → tek çağrı")

print("== E: şablon çöküşü uyarısı ==")
g = headline_openings({
    "Tesla": ("Tesla news is mixed: deliveries fell.", ["Tesla", "TSLA"]),
    "NVIDIA": ("NVIDIA's news is mixed on China.", ["NVIDIA", "NVDA"]),
    "AMD": ("Advanced Micro Devices news is mixed.", ["Advanced Micro Devices", "AMD"]),
    "Apple": ("Apple news is mixed after WWDC.", ["Apple"]),
    "MSFT": ("Azure grew 43% in Q4.", ["Microsoft", "MSFT"]),
}, n_words=3, max_same=3)
check(list(g) == ["<x> news is"] and sorted(g["<x> news is"]) == ["AMD", "Apple", "NVIDIA", "Tesla"],
      f"entity adı yok sayılıp 4 aynı açılış bulundu: {g}")
check(headline_openings({k: ("Mixed news: x.", [k]) for k in ("A1", "B2", "C3")}) == {},
      "3 entity → eşik aşılmadı (>3 gerekir)")

cap = []


class Cap(logging.Handler):
    def emit(self, r):
        cap.append((r.levelno, r.getMessage()))


lg = logging.getLogger("newsradar.analysis")
lg.addHandler(Cap()); lg.setLevel(logging.INFO)


class FakeAssess:
    model = "fake"

    def call_tool(self, *, system, user, tool, max_tokens=4096):
        if tool["name"] != ENTITY_ANALYSIS_TOOL["name"]:
            return {"analyses": []}
        name = user.split("Varlık: ", 1)[1].split(" (", 1)[0]
        if "CRITICAL RULES" in user:
            return {"headline_verdict": f"{name} shares rose after strong demand.", "summary": "S."}
        # TR açılışları farklı ("<x> 65 birim", "<x> 66 birim" …) → TR'de uyarı beklenmez.
        return {"headline_verdict": f"{name} {ord(name[0])} birim büyüdü.", "summary": "Ö."}


init_db()
now = datetime.now(timezone.utc)


def add_entities(names):
    ids = set()
    with session_scope() as s:
        for n in names:
            e = Entity(name=n, type="keyword", query=n, active=True)
            s.add(e); s.flush(); ids.add(e.id)
            s.add(Article(entity_id=e.id, url=f"http://x/{n}", url_hash=f"h-{n}", title=f"{n} t",
                          source="s", description="d", provider="t", analyzed=True,
                          analyzed_at=now - timedelta(hours=1), prefiltered=False,
                          sentiment=0.1, event_type="other", relevance=0.9))
    return ids


ids4 = add_entities(["Alfa", "Beta", "Gama", "Delta"])
cap.clear()
asyncio.run(analyze_all_async(FakeAssess(), entity_ids=ids4))
warns = [m for lvl, m in cap if lvl == logging.WARNING and m.startswith("[şablon]")]
check(len(warns) == 1 and "4 entity'nin en hükmü" in warns[0] and "'<x> shares rose'" in warns[0],
      f"4 entity aynı EN açılış → tek uyarı: {warns}")
check(not any(" tr hükmü" in m for m in warns), "farklı TR açılışları → TR uyarısı yok")

ids3 = add_entities(["Epsilon", "Zeta", "Eta"])
cap.clear()
asyncio.run(analyze_all_async(FakeAssess(), entity_ids=ids3))
check(not [m for lvl, m in cap if m.startswith("[şablon]")], "3 entity aynı açılış → uyarı yok (eşik >3)")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
