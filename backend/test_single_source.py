"""TR/EN tek kaynak değerlendirme (gerçek API yok, izole temp DB, sahte LLM).

Doğrular:
  (A) şirket başına TEK değerlendirme çağrısı (EN) + TR için TEK çeviri çağrısı; tek kayıt ("all")
  (B) TR ve EN kart: aynı risk, yön, kısa/uzun vade hükmü, etken yönleri, takip listesi sayısı;
      metinler kendi dilinde
  (C) çeviri hükmü/riski/yönü DEĞİŞTİREMEZ (araç şemasında yoklar; fazladan alan yok sayılır)
  (D) çeviri geçersizse (madde sayısı tutmuyor) bir kez yeniden; yine geçersizse TR yazılmaz →
      TR kart 'bu dilde yok' (başka hüküm göstermez), sonraki yenileme tamamlar
  (E) Ask AI bağlamı kartla aynı kaynaktan (aynı risk/vade hükmü, kullanıcının dilinde metin)
Çalıştır: python test_single_source.py
"""
import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_single_source.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ["NEWSRADAR_ENABLE_DE"] = "on"  # Almanca bayrağı açıkken (DE testleri)
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y", NEWSRADAR_SCHEDULER="off",
    NEWSRADAR_SEED_ON_START="off", NEWSRADAR_LLM_PROVIDER="anthropic", NEWSRADAR_DAILY_BUDGET_USD="0",
)

from sqlalchemy import select  # noqa: E402

from app.analysis.pipeline import analyze_all_async  # noqa: E402
from app.analysis.schemas import ENTITY_ANALYSIS_TOOL, TRANSLATION_TOOL  # noqa: E402
from app.api.routes_chat import _build_context  # noqa: E402
from app.api.serializers import entity_card  # noqa: E402
from app.db.database import SessionLocal, init_db, session_scope  # noqa: E402
from app.db.models import Article, Entity, EntityAnalysis  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


now = datetime.now(timezone.utc)
EN = {
    "headline_verdict": "Deliveries fell 8%, but the Megapack backlog keeps growing.",
    "ai_take": "Tesla's deliveries missed. Energy storage is the bright spot.",
    "risk_score": 63, "sentiment_trend": "worsening",
    "top_drivers": ["Deliveries fell 8%.", "Megapack orders rose."], "top_driver_directions": ["down", "up"],
    "summary": "The delivery miss dominates this week.", "stance": "bearish", "conviction": "medium",
    "what_to_verify": ["Check the Q3 delivery figure.", "Watch the Megapack backlog."],
    "invalidation": "A delivery rebound would undo this view.",
    "short_term": {"verdict": "negative", "summary": "The delivery miss weighs on this week.",
                   "drivers": [{"text": "Deliveries fell 8%.", "direction": "down"},
                               {"text": "China price cuts did not help.", "direction": "down"}]},
    "long_term": {"verdict": "positive", "summary": "Energy storage carries the long-term picture.",
                  "drivers": [{"text": "Megapack orders rose 40%.", "direction": "up"},
                              {"text": "Battery costs keep falling.", "direction": "up"},
                              {"text": "EV competition squeezes margins.", "direction": "down"}]},
}
TR_WORDS = {"Deliveries fell 8%.": "Teslimatlar yüzde 8 düştü.", "Megapack orders rose.": "Megapack siparişleri arttı.",
            "The delivery miss dominates this week.": "Teslimat kaçırması bu haftaya damga vuruyor."}


def tr_of(v):
    return TR_WORDS.get(v, f"Türkçe karşılık ({len(v)} harf).") if v else ""


def de_of(v):
    return f"Deutsche Fassung ({len(v)} Zeichen)." if v else ""


class Fake:
    model = "fake"

    def __init__(self, bad_translations=0, sneaky=False):
        self.assess = self.translate = 0
        self.bad, self.sneaky = bad_translations, sneaky

    def call_tool(self, *, system, user, tool, max_tokens=4096):
        if tool["name"] == TRANSLATION_TOOL["name"]:
            self.translate += 1
            src, _ = json.JSONDecoder().raw_decode(user.split("JSON:\n", 1)[1])
            conv = de_of if "plain German" in user else tr_of
            out = {k: ([conv(x) for x in v] if isinstance(v, list) else conv(v)) for k, v in src.items()}
            if self.bad > 0 and conv is de_of:
                return out
            if self.bad > 0:
                self.bad -= 1
                out["top_drivers"] = out["top_drivers"][:1]  # madde eksik → geçersiz
            if self.sneaky:  # çeviri hükmü/riski değiştirmeye çalışır → yok sayılmalı
                out.update(risk_score=10, stance="bullish", short_term={"verdict": "very_positive"})
            return out
        if tool["name"] == ENTITY_ANALYSIS_TOOL["name"]:
            self.assess += 1
            return json.loads(json.dumps(EN))
        return {"analyses": []}


def mk_entity(name, query):
    with session_scope() as s:
        e = Entity(name=name, type="ticker", query=query, active=True, language="en")
        s.add(e); s.flush()
        for i in range(4):
            s.add(Article(entity_id=e.id, url=f"http://{query}/{i}", url_hash=f"{query}{i}", title=f"{name} {i}",
                          source="s", description="d", provider="t", analyzed=True, prefiltered=False,
                          analyzed_at=now - timedelta(hours=1), published_at=now - timedelta(days=i),
                          sentiment=-0.2, event_type="other", relevance=0.9))
        return e.id


def cards(eid):
    with session_scope() as s:
        e = s.get(Entity, eid)
        return entity_card(s, e, "tr"), entity_card(s, e, "en")


init_db()
print("== A: tek çağrı + tek kayıt ==")
tid = mk_entity("Tesla", "TSLA")
f = Fake()
asyncio.run(analyze_all_async(f, entity_ids={tid}))
with session_scope() as s:
    rows = s.scalars(select(EntityAnalysis).where(EntityAnalysis.entity_id == tid)).all()
    langs = [(r.language, sorted(r.texts or {})) for r in rows]
check(f.assess == 1 and f.translate == 2, f"1 değerlendirme + 2 çeviri çağrısı (TR, DE) ({f.assess}, {f.translate})")
check(langs == [("all", ["de", "en", "tr"])], f"tek kayıt, üç dilin metni ({langs})")

print("== B: TR ve EN aynı hüküm ==")
tr, en = cards(tid)
ta, ea = tr.analysis, en.analysis
check(ta.risk_score == ea.risk_score == 63 and ta.stance == ea.stance == "bearish", "aynı risk ve yön")
check(ta.short_term.verdict == ea.short_term.verdict == "negative"
      and ta.long_term.verdict == ea.long_term.verdict == "positive", "aynı kısa/uzun vade hükmü")
check([d.direction for d in ta.long_term.drivers] == [d.direction for d in ea.long_term.drivers] == ["up", "up", "down"]
      and ta.driver_directions == ea.driver_directions == ["down", "up"], "aynı etken yönleri (vade + genel)")
check(len(ta.what_to_verify) == len(ea.what_to_verify) == 2, "aynı takip listesi (madde sayısı)")
check(ta.top_drivers[0] == "Teslimatlar yüzde 8 düştü." and ea.top_drivers[0] == "Deliveries fell 8%.",
      "metinler kendi dilinde")
with session_scope() as s:
    de = entity_card(s, s.get(Entity, tid), "de")
check(de.analysis is not None and de.analysis_language == "de" and de.analysis.risk_score == 63
      and de.analysis.stance == "bearish" and de.analysis.short_term.verdict == "negative"
      and de.analysis.top_drivers[0].startswith("Deutsche Fassung"),
      "DE: aynı hüküm/risk, metin Almanca")
check(ta.long_term.drivers[0].text.startswith("Türkçe karşılık") and ea.long_term.drivers[0].text == "Megapack orders rose 40%.",
      "vade etken metinleri de çevrildi")
check(tr.analysis_language == "tr" and en.analysis_language == "en" and not tr.analysis_missing_language,
      "analysis_language istenen dil")

print("== C: çeviri hükmü değiştiremez ==")
props = TRANSLATION_TOOL["input_schema"]["properties"]
check(not any(k in props for k in ("risk_score", "stance", "verdict", "short_term", "direction")),
      "çeviri şemasında hüküm/risk/yön alanı yok")
sid = mk_entity("Sneaky", "SNK")
asyncio.run(analyze_all_async(Fake(sneaky=True), entity_ids={sid}))
tr2, en2 = cards(sid)
check(tr2.analysis.risk_score == 63 and tr2.analysis.stance == "bearish"
      and tr2.analysis.short_term.verdict == "negative", "çevirinin fazladan alanları yok sayıldı")

print("== D: çeviri geçersiz ==")
bid = mk_entity("Bad", "BAD")
f = Fake(bad_translations=2)
asyncio.run(analyze_all_async(f, entity_ids={bid}))
tr3, en3 = cards(bid)
check(f.translate == 3, f"geçersiz TR çevirisi bir kez yeniden istendi, DE bir kez ({f.translate})")
check(en3.analysis is not None and tr3.analysis is None and tr3.analysis_missing_language,
      "TR yazılmadı → TR kart 'bu dilde yok' (başka hüküm yok), EN normal")
f = Fake()
asyncio.run(analyze_all_async(f, entity_ids={bid}))
tr4, _ = cards(bid)
check(f.assess == 0 and f.translate == 1 and tr4.analysis is not None
      and tr4.analysis.risk_score == en3.analysis.risk_score,
      f"sonraki yenileme eksik TR çevirisini yeniden değerlendirmeden tamamladı ({f.assess}, {f.translate})")

print("== E: Ask AI aynı kaynaktan ==")
db = SessionLocal()
try:
    e = db.get(Entity, tid)
    ctx_tr, ctx_en = _build_context(db, e, "tr"), _build_context(db, e, "en")
finally:
    db.close()
check("risk=63/100" in ctx_tr and "risk=63/100" in ctx_en and "yön=bearish" in ctx_tr, "aynı risk ve yön")
check("Kısa vade (~7 gün): negative" in ctx_tr and "Uzun vade (30-90 gün): positive" in ctx_en, "aynı vade hükümleri")
check("Teslimat kaçırması bu haftaya damga vuruyor." in ctx_tr and "The delivery miss dominates" in ctx_en
      and "Teslimat kaçırması" not in ctx_en, "metin kullanıcının dilinde")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
