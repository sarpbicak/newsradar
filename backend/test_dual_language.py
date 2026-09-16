"""Bölüm 1c — iki dilli analiz: üretim (prompt), saklama, dil-farkında serileştirme,
fallback notu, dil-başına delta. Çalıştır: python test_dual_language.py"""
import os
import tempfile

_db = os.path.join(tempfile.gettempdir(), "nr_test_dual.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_SECRET="dual", NEWSRADAR_SCHEDULER="off",
    NEWSRADAR_SEED_ON_START="off", NEWSRADAR_LLM_PROVIDER="anthropic",
)

from app.analysis.prompts import build_entity_prompt, output_language_directive  # noqa: E402
from app.api.serializers import entity_card, _latest_analysis, _previous_analysis, _delta_out, risk_history  # noqa: E402
from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import Entity, EntityAnalysis  # noqa: E402

init_db()
PASS = FAIL = 0
def check(cond, msg):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✓ {msg}")
    else: FAIL += 1; print(f"  ✗ FAIL: {msg}")


def _mk_analysis(entity_id, language, risk, stance, verdict):
    return EntityAnalysis(
        entity_id=entity_id, language=language, headline_verdict=verdict,
        ai_take=f"take-{language}", risk_score=risk, sentiment_trend="stable",
        top_drivers=[f"driver-{language}"], summary=f"summary-{language}",
        stance=stance, conviction="medium", what_to_verify=[f"verify-{language}"],
        invalidation=f"inval-{language}", articles_considered=5, avg_sentiment=0.1,
    )


def main():
    print("== Prompt: çıktı dili direktifi (tr/en) ==")
    en = output_language_directive("en"); tr = output_language_directive("tr")
    # (TR direktifi "İngilizce" kelimesini YASAK bağlamında içerir; büyük harf İNGİLİZCE ayrımı yeterli.)
    check("İNGİLİZCE" in en, "output_language_directive('en') İngilizce ister")
    check("TÜRKÇE" in tr and "İNGİLİZCE" not in tr, "output_language_directive('tr') Türkçe ister")
    art = [{"id": 1, "title": "t", "sentiment": 0.2, "event_type": "product",
            "impact_horizon": "short", "rationale": "r", "source_count": 1, "risk_flags": []}]
    pe = build_entity_prompt("Tesla", "TSLA", "ticker", art, out_lang="en")
    pt = build_entity_prompt("Tesla", "TSLA", "ticker", art, out_lang="tr")
    check("İNGİLİZCE" in pe, "build_entity_prompt(out_lang=en) → İngilizce direktif")
    check("TÜRKÇE" in pt and "İNGİLİZCE" not in pt, "build_entity_prompt(out_lang=tr) → Türkçe direktif")

    print("\n== İki dilde satır + dil-farkında serileştirme ==")
    with session_scope() as s:
        e = Entity(name="Tesla", type="ticker", query="TSLA", language="en")
        s.add(e); s.flush(); eid = e.id
        s.add(_mk_analysis(eid, "tr", 50, "neutral", "TR hüküm"))
        s.add(_mk_analysis(eid, "en", 50, "neutral", "EN verdict"))
        s.flush()
        en_card = entity_card(s, e, "en")
        tr_card = entity_card(s, e, "tr")
    check(en_card.analysis.headline_verdict == "EN verdict" and en_card.analysis_language == "en",
          "EN kullanıcı → EN değerlendirme (analysis_language=en)")
    check(tr_card.analysis.headline_verdict == "TR hüküm" and tr_card.analysis_language == "tr",
          "TR kullanıcı → TR değerlendirme (analysis_language=tr)")

    print("\n== Fallback: o dilde yoksa diğer dil + analysis_language notu ==")
    with session_scope() as s:
        e2 = Entity(name="AMD", type="ticker", query="AMD", language="en")
        s.add(e2); s.flush(); eid2 = e2.id
        s.add(_mk_analysis(eid2, "tr", 40, "bullish", "sadece TR"))  # yalnızca TR
        s.flush()
        card = entity_card(s, e2, "en")  # EN ister ama yok
    check(card.analysis.headline_verdict == "sadece TR" and card.analysis_language == "tr",
          "EN yokken TR gösterilir; analysis_language=tr → arayüz 'TR üretildi' notu koyar")

    print("\n== Delta AYNI dilde hesaplanır (tr'yi en ile karıştırmaz) ==")
    with session_scope() as s:
        e3 = Entity(name="NVDA", type="ticker", query="NVDA", language="en")
        s.add(e3); s.flush(); eid3 = e3.id
        # TR: iki kayıt (risk 30 → 60, stance değişti). EN: tek kayıt.
        import time
        a1 = _mk_analysis(eid3, "tr", 30, "bearish", "tr-eski"); s.add(a1); s.flush()
        time.sleep(0.01)
        a2 = _mk_analysis(eid3, "tr", 60, "bullish", "tr-yeni"); s.add(a2); s.flush()
        time.sleep(0.01)
        aen = _mk_analysis(eid3, "en", 45, "neutral", "en-tek"); s.add(aen); s.flush()
        latest_tr = _latest_analysis(s, eid3, "tr")
        prev_tr = _previous_analysis(s, eid3, "tr")
        delta_tr = _delta_out(latest_tr, prev_tr)
        latest_en = _latest_analysis(s, eid3, "en")
        prev_en = _previous_analysis(s, eid3, "en")
        rh_tr = risk_history(s, eid3, language="tr")
        rh_en = risk_history(s, eid3, language="en")
    check(latest_tr.headline_verdict == "tr-yeni" and prev_tr.headline_verdict == "tr-eski",
          "TR latest/previous ikisi de TR (dil karışmadı)")
    check(delta_tr is not None and delta_tr.risk_delta == 30 and delta_tr.stance_changed,
          f"TR delta TR-içi hesaplandı (risk_delta=30, stance değişti): {delta_tr.risk_delta if delta_tr else None}")
    check(prev_en is None, "EN tek kayıt → önceki yok (TR ile karşılaştırmıyor)")
    check(len(rh_tr) == 2 and len(rh_en) == 1,
          f"risk_history dil filtreli (tr={len(rh_tr)}, en={len(rh_en)}) — noktalar ikiye katlanmıyor")

    print(f"\n{'='*54}\nSONUÇ: {PASS} geçti, {FAIL} başarısız")
    return FAIL == 0


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
