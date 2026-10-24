"""Kısa / uzun vade: aynı değerlendirme çağrısında iki vade (gerçek API yok, izole temp DB).

Doğrular:
  (A) tool şeması: short_term/long_term zorunlu, strict-uyumlu (her nesnede tüm alanlar
      required + additionalProperties false); mevcut alanlar duruyor
  (B) sanitize: geçerli vade, eksik → None, çelişkili hüküm → mixed, insufficient_data → boş
  (C) veri eşiği: 7 günde <2 haber → kısa vade "yetersiz veri" (modelden bağımsız)
  (D) istem: haber satırlarında tarih damgası, vade sayıları, yetersiz veri talimatı, kural 11 (TR/EN)
  (E) kalite: vade hükmü↔etken çelişkisi, vade metnindeki yasaklı ifade ve dil sızıntısı bir kez
      yeniden istetir; ikinci yanıt da çelişkiliyse kayıtta "mixed"
  (F) DB: kolonlar idempotent, kayıt → API (AnalysisOut); eski kayıt None
Çalıştır: python test_horizons.py
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_horizons.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y", NEWSRADAR_SCHEDULER="off",
    NEWSRADAR_SEED_ON_START="off", NEWSRADAR_LLM_PROVIDER="anthropic", NEWSRADAR_DAILY_BUDGET_USD="0",
)

from sqlalchemy import select  # noqa: E402

from app.analysis.pipeline import _assess_entity_with_recovery, _write_assessment  # noqa: E402
from app.analysis.prompts import build_entity_prompt, entity_assessment_rules  # noqa: E402
from app.analysis.schemas import (  # noqa: E402
    ENTITY_ANALYSIS_TOOL, apply_horizon_floor, horizon_counts, sanitize_entity_analysis,
)
from app.api.serializers import analysis_out  # noqa: E402
from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import Entity, EntityAnalysis  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


now = datetime.now(timezone.utc)
BASE = {
    "headline_verdict": "Teslimatlar düştü ama Optimus takvimi öne çekildi.",
    "ai_take": "Teslimat sayısı zayıf.", "risk_score": 62, "sentiment_trend": "worsening",
    "top_drivers": ["Teslimatlar yüzde 8 düştü."], "top_driver_directions": ["down"],
    "summary": "Teslimat düşüşü öne çıkıyor.", "stance": "bearish", "conviction": "medium",
    "what_to_verify": ["Çeyrek teslimat rakamını doğrula."], "invalidation": "Teslimatlar toparlanırsa.",
}
SHORT_NEG = {"verdict": "negative", "summary": "Teslimat düşüşü bu hafta baskı yaratıyor.",
             "drivers": [{"text": "Teslimatlar yüzde 8 düştü.", "direction": "down"},
                         {"text": "Çin satışları geriledi.", "direction": "down"},
                         {"text": "Optimus takvimi öne çekildi.", "direction": "up"}]}
LONG_POS = {"verdict": "positive", "summary": "Enerji depolama işi büyümeyi taşıyor.",
            "drivers": [{"text": "Megapack siparişleri arttı.", "direction": "up"},
                        {"text": "Batarya maliyeti düşüyor.", "direction": "up"}]}
LONG_BAD = {**LONG_POS, "drivers": [{"text": "Marjlar daralıyor.", "direction": "down"},
                                    {"text": "Rekabet sertleşiyor.", "direction": "down"},
                                    {"text": "Megapack siparişleri arttı.", "direction": "up"}]}

print("== A: şema ==")
props = ENTITY_ANALYSIS_TOOL["input_schema"]["properties"]
req = ENTITY_ANALYSIS_TOOL["input_schema"]["required"]
check({"short_term", "long_term"} <= set(req), "short_term/long_term zorunlu")
check(all(k in props for k in ("headline_verdict", "top_drivers", "stance", "risk_score")), "mevcut alanlar duruyor")


def strict_ok(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            if set(node.get("required", [])) != set(node.get("properties", {})) or node.get("additionalProperties") is not False:
                return False
        return all(strict_ok(v) for v in node.values())
    if isinstance(node, list):
        return all(strict_ok(v) for v in node)
    return True


check(strict_ok(ENTITY_ANALYSIS_TOOL["input_schema"]), "strict: her nesnede tüm alanlar required + additionalProperties=false")
check(props["short_term"]["properties"]["verdict"]["enum"] ==
      ["very_negative", "negative", "neutral", "positive", "very_positive", "insufficient_data"], "5 kademe + yetersiz veri")

print("== B: sanitize ==")
c = sanitize_entity_analysis({**BASE, "short_term": SHORT_NEG, "long_term": LONG_POS}, "tr")
check(c["short_term"]["verdict"] == "negative" and len(c["short_term"]["drivers"]) == 3, "geçerli kısa vade")
check(c["long_term"]["drivers"][0] == {"text": "Megapack siparişleri arttı.", "direction": "up"}, "etken metni + yön")
check(sanitize_entity_analysis(BASE, "tr")["short_term"] is None, "eski çıktı (vade yok) → None")
check(sanitize_entity_analysis({**BASE, "long_term": LONG_BAD}, "tr")["long_term"]["verdict"] == "mixed",
      "olumlu hüküm ama etkenler çoğunlukla down → mixed")
nd = sanitize_entity_analysis({**BASE, "short_term": {"verdict": "insufficient_data", "drivers": [{"text": "x.", "direction": "up"}], "summary": "y."}}, "tr")
check(nd["short_term"] == {"verdict": "insufficient_data", "drivers": [], "summary": ""}, "yetersiz veri → boş etken/özet")
check(sanitize_entity_analysis({**BASE, "short_term": {"verdict": "bullish"}}, "tr")["short_term"] is None, "geçersiz hüküm → None")

print("== C: veri eşiği ==")
pay = [{"published_at": now - timedelta(days=1)}, {"published_at": now - timedelta(days=20)},
       {"published_at": now - timedelta(days=40)}, {"published_at": None}]
cnt = horizon_counts(pay, now)
check(cnt == {"short_term": 1, "long_term": 3}, f"sayım: {cnt}")
floored = apply_horizon_floor(sanitize_entity_analysis({**BASE, "short_term": SHORT_NEG, "long_term": LONG_POS}, "tr"), cnt)
check(floored["short_term"]["verdict"] == "insufficient_data", "7 günde 1 haber → kısa vade yetersiz veri")
check(floored["long_term"]["verdict"] == "positive", "uzun vade (3 haber) korunur")
check(horizon_counts([{"published_at": (now - timedelta(days=2)).isoformat()}], now)["short_term"] == 1, "ISO metin tarih de sayılır")

print("== D: istem ==")
arts = [{"title": "Teslimatlar düştü", "sentiment": -0.5, "event_type": "earnings", "impact_horizon": "short",
         "risk_flags": [], "rationale": "", "source_count": 1, "published_at": now - timedelta(days=3)},
        {"title": "Megapack rekoru", "sentiment": 0.6, "event_type": "product", "impact_horizon": "long",
         "risk_flags": [], "rationale": "", "source_count": 1, "published_at": now - timedelta(days=30)}]
p = build_entity_prompt("Tesla", "TSLA", "ticker", arts, out_lang="tr")
d3 = (now - timedelta(days=3)).strftime("%Y-%m-%d")
check(f"[{d3}, 3 gün önce]" in p, "haber satırında tarih damgası")
check("son 7 günde 1 haber, son 90 günde 2 haber" in p, "vade sayıları istemde")
check("Kısa vade için veri YETERSİZ" in p and "Uzun vade için veri YETERSİZ" in p, "yetersiz veri talimatı")
check("11) İKİ VADE" in entity_assessment_rules("tr") and "11) TWO HORIZONS" in entity_assessment_rules("en"), "kural 11 TR/EN")
p_ok = build_entity_prompt("Tesla", "TSLA", "ticker", arts * 2, out_lang="en")
check("YETERSİZ" not in p_ok, "yeterli veri → talimat yok")
check("bugün" in build_entity_prompt("X", "X", "ticker", [{**arts[0], "published_at": now}]), "bugünkü haber: 'bugün'")


class Fake:
    model = "fake"

    def __init__(self, outs):
        self.outs, self.users = list(outs), []

    def call_tool(self, *, system, user, tool, max_tokens=4096):
        self.users.append(user)
        return self.outs.pop(0)


build = lambda items: "PROMPT"  # noqa: E731
print("== E: kalite denetimi ==")
good = {**BASE, "short_term": SHORT_NEG, "long_term": LONG_POS}
bad = {**BASE, "short_term": SHORT_NEG, "long_term": LONG_BAD}
f = Fake([bad, good])
data, _ = _assess_entity_with_recovery(f, build, [{"x": 1}], "Tesla", "tr")
check(len(f.users) == 2 and data == good, "çelişkili vade → bir kez yeniden, tutarlı yanıt kullanıldı")
check("long_term hükmü etken yönleriyle çelişti" in f.users[1], "not hangi vadeyi söylüyor")
f = Fake([bad, bad])
data, _ = _assess_entity_with_recovery(f, build, [{"x": 1}], "Tesla", "tr")
check(len(f.users) == 2, "yine çelişkili → üçüncü çağrı yok")
f = Fake([{**good, "short_term": {**SHORT_NEG, "summary": "Haberler karışık görünüyor."}}, good])
_assess_entity_with_recovery(f, build, [{"x": 1}], "Tesla", "tr")
check(len(f.users) == 2, "vade özetinde yasaklı ifade → yeniden")
f = Fake([{**good, "long_term": {**LONG_POS, "drivers": [{"text": "Megapack already büyüdü.", "direction": "up"}]}}, good])
_assess_entity_with_recovery(f, build, [{"x": 1}], "Tesla", "tr")
check(len(f.users) == 2, "vade etkeninde dil sızıntısı → yeniden")
f = Fake([good])
_assess_entity_with_recovery(f, build, [{"x": 1}], "Tesla", "tr")
check(len(f.users) == 1, "temiz → tek çağrı (ek LLM çağrısı yok)")

print("== F: DB + API ==")
init_db(); init_db()  # idempotent
with session_scope() as s:
    e = Entity(name="Tesla", type="ticker", query="TSLA", active=True)
    s.add(e); s.flush(); eid = e.id
    s.add(EntityAnalysis(entity_id=eid, language="tr", risk_score=50, sentiment_trend="stable", top_drivers=[],
                         summary="eski.", stance="neutral", conviction="low", what_to_verify=[], invalidation="x.",
                         created_at=now - timedelta(days=2)))
with session_scope() as s:
    old = analysis_out(s.scalars(select(EntityAnalysis).where(EntityAnalysis.entity_id == eid)).one())
check(old.short_term is None and old.long_term is None, "eski kayıt → vade None (tek etiket)")
_write_assessment(eid, bad, 3, -0.1, "tr", {"short_term": 3, "long_term": 3})
with session_scope() as s:
    row = s.scalars(select(EntityAnalysis).where(EntityAnalysis.entity_id == eid)
                    .order_by(EntityAnalysis.created_at.desc())).first()
    out = analysis_out(row)
check(out.short_term.verdict == "negative" and out.short_term.drivers[0].direction == "down", "kayıt → API kısa vade")
check(out.long_term.verdict == "mixed", "tekrar denemeden sonra çelişkili kalan → 'mixed' kaydedildi")
check(out.headline_verdict == BASE["headline_verdict"] and out.stance == "bearish", "mevcut alanlar korunur")
_write_assessment(eid, good, 1, 0.0, "tr", {"short_term": 1, "long_term": 1})
with session_scope() as s:
    row = s.scalars(select(EntityAnalysis).where(EntityAnalysis.entity_id == eid)
                    .order_by(EntityAnalysis.created_at.desc())).first()
    out = analysis_out(row)
check(out.short_term.verdict == "insufficient_data" and out.long_term.verdict == "insufficient_data",
      "az haber → iki vade de yetersiz veri")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
