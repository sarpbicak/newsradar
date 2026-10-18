"""Metin kalitesi kuralları — hiçbir alan cümle ortasında bitmez (gerçek API yok).

Doğrular:
  (A) clip_to_sentence: tavan içinde → değişmez; aşınca son TAM cümlede kesilir; sınır içinde
      cümle sonu yoksa metin OLDUĞU GİBİ kalır (yarım cümle üretilmez); ondalık sayı cümle
      sonu sayılmaz
  (B) sanitize_entity_analysis: tüm metin alanlarına aynı kural (emniyet tavanları)
  (C) unterminated_fields: noktalama ile bitmeyen alan/madde yakalanır (kesik cümle testi)
  (D) yasaklı ifadeler + tekrar eden 3+ kelimelik öbekler
  (E) hüküm emniyet tavanını aşarsa değerlendirme BİR KEZ "daha kısa yaz" notuyla yeniden
      istenir; yine aşarsa son tam cümlede kesilir
  (F) prompt kuralları: sınırlar + "daha az şey söyle" + tam cümle + yasaklı ifadeler
Çalıştır: python test_text_quality.py
"""
import os
import tempfile

_db = os.path.join(tempfile.gettempdir(), "nr_test_text_quality.db")
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y", NEWSRADAR_SCHEDULER="off",
    NEWSRADAR_SEED_ON_START="off", NEWSRADAR_LLM_PROVIDER="anthropic",
)

from app.analysis.pipeline import _assess_entity_with_recovery  # noqa: E402
from app.analysis.prompts import entity_assessment_rules  # noqa: E402
from app.analysis.schemas import sanitize_entity_analysis  # noqa: E402
from app.analysis.text_quality import (  # noqa: E402
    HARD_CAPS, banned_phrase_hits, clip_to_sentence, ends_with_terminal, repeated_ngrams,
    unterminated_fields, word_count,
)

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


print("== A: clip_to_sentence ==")
short = "Kısa ve tam bir cümle."
check(clip_to_sentence(short, 10) == short, "tavan içinde → değişmez")
two = "Birinci cümle burada bitiyor. İkinci cümle ise çok uzun ve devam ediyor ve ediyor."
out = clip_to_sentence(two, 8)
check(out == "Birinci cümle burada bitiyor.", f"aşınca son tam cümlede kesildi: {out!r}")
run_on = " ".join(["kelime"] * 40) + " bitti."
check(clip_to_sentence(run_on, 28) == run_on, "sınır içinde cümle sonu yok → OLDUĞU GİBİ kaldı")
dec = "Marj 4.5 puan düştü ve hisse 3.2 oranında geriledi ama analistler yine de iyimser kaldı."
check(clip_to_sentence(dec, 6) == dec, "ondalık sayıdaki nokta cümle sonu sayılmadı")
q = 'Musk "tamamen sahte haber" dedi. Sonra başka şeyler de söyledi ve söyledi ve söyledi.'
check(clip_to_sentence(q, 7) == 'Musk "tamamen sahte haber" dedi.', "tırnak/kapanışlı cümle sonu tanındı")

print("== B: sanitize_entity_analysis ==")
long_take = " ".join(f"Cümle numarası {i} burada tamamlanıyor." for i in range(60))  # 240 kelime
d = sanitize_entity_analysis({
    "headline_verdict": "Azure büyümesi güçlü, İngiltere incelemesi ise risk yaratıyor.",
    "ai_take": long_take,
    "summary": "Özet tek cümle.",
    "top_drivers": ["Azure yüzde 43 büyüdü."],
    "what_to_verify": ["CMA kararının tarihi."],
    "invalidation": "Azure büyümesi yüzde 30'un altına inerse görüş çürür.",
}, "tr")
check(d["headline_verdict"].endswith("yaratıyor."), "kısa hüküm dokunulmadan kaldı")
check(word_count(d["ai_take"]) <= HARD_CAPS["ai_take"] and ends_with_terminal(d["ai_take"]),
      f"ai_take {word_count(d['ai_take'])} kelime ≤ {HARD_CAPS['ai_take']} ve noktalı bitiyor")
long_tr = " ".join(["kelime"] * 30)
d2 = sanitize_entity_analysis({"headline_verdict": long_tr}, "tr")
check(d2["headline_verdict"] == long_tr, "30 kelimelik noktasız TR hüküm KESİLMEDİ (yarım cümle yok)")
d3 = sanitize_entity_analysis({"headline_verdict": "Kısa bir giriş. " + " ".join(["uzun"] * 30) + "."}, "tr")
check(d3["headline_verdict"] == "Kısa bir giriş.", "tavanı aşan hüküm son tam cümlede kesildi")
d4 = sanitize_entity_analysis({"what_to_verify": ["Birinci kontrol tamam. " + " ".join(["x"] * 70) + "."]}, "en")
check(d4["what_to_verify"] == ["Birinci kontrol tamam."], "liste maddesi de aynı kurala tabi")

print("== B2: liste alanı string gelirse (Sonnet 5.5) ==")
d5 = sanitize_entity_analysis({"what_to_verify": "Google sızıntısını doğrula.\nIPO tarihini kontrol et."}, "tr")
check(d5["what_to_verify"] == ["Google sızıntısını doğrula.", "IPO tarihini kontrol et."],
      f"satırlara bölündü (karakterlere DEĞİL): {d5['what_to_verify']}")
d6 = sanitize_entity_analysis({"top_drivers": '["Azure büyüdü.", "CMA incelemesi."]'}, "en")
check(d6["top_drivers"] == ["Azure büyüdü.", "CMA incelemesi."], "JSON dizi string'i parse edildi")
d7 = sanitize_entity_analysis({"what_to_verify": "Tek bir kontrol cümlesi."}, "en")
check(d7["what_to_verify"] == ["Tek bir kontrol cümlesi."], "tek string → tek madde")

print("== C: kesik cümle denetimi ==")
good = {"headline_verdict": "Tam cümle.", "ai_take": "Bir. İki!", "summary": "Özet?",
        "invalidation": "Olursa çürür.", "top_drivers": ["A oldu."], "what_to_verify": ['"B" kontrol.']}
check(unterminated_fields(good) == [], "tüm alanlar noktalı → temiz")
bad = dict(good, headline_verdict="Tesla hisseyi 300 doların", top_drivers=["Azure büyümesi"])
fields = sorted(f for f, _ in unterminated_fields(bad))
check(fields == ["headline_verdict", "top_drivers"], f"kesik alanlar yakalandı: {fields}")

print("== D: yasaklı ifadeler + öbek tekrarı ==")
check(banned_phrase_hits("Haberler ağırlıklı olarak olumlu.", "tr") == ["ağırlıklı olarak olumlu"],
      "TR yasaklı ifade yakalandı")
check(banned_phrase_hits("Coverage is largely negative.", "en") == ["largely negative"],
      "EN yasaklı ifade yakalandı")
check(banned_phrase_hits("Azure grew 43%.", "en") == [], "temiz metin")
grams = repeated_ngrams({
    "Tesla": "Tesla's news flow leans negative after a weak quarter.",
    "Nvidia": "Nvidia's news flow leans positive on chip bookings.",
    "MSFT": "Azure grew past 100 billion dollars.",
}, n=3)
check("news flow leans" in grams and sorted(grams["news flow leans"]) == ["Nvidia", "Tesla"],
      f"tekrar eden öbek yakalandı: {list(grams)}")

print("== E: 'daha kısa yaz' tekrar denemesi ==")
LONG = " ".join(["çok"] * 35) + "."
SHORT = "Azure güçlü, İngiltere incelemesi ise risk."


class FakeClient:
    model = "fake"
    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.users = []
    def call_tool(self, *, system, user, tool, max_tokens=4096):
        self.users.append(user)
        return {"headline_verdict": self.verdicts.pop(0), "summary": "s."}


build = lambda items: "PROMPT"  # noqa: E731
c = FakeClient([SHORT])
data, _ = _assess_entity_with_recovery(c, build, [{"x": 1}], "Kısa", "tr")
check(len(c.users) == 1 and data["headline_verdict"] == SHORT, "sınır içinde → tek çağrı")
c = FakeClient([LONG, SHORT])
data, _ = _assess_entity_with_recovery(c, build, [{"x": 1}], "Uzun", "tr")
check(len(c.users) == 2 and data["headline_verdict"] == SHORT, "tavan aşıldı → bir kez yeniden, kısa yanıt alındı")
check("daha az şey söyle" in c.users[1] and "35 kelimeydi" in c.users[1],
      "ikinci prompt'ta 'daha kısa yaz' notu var")
c = FakeClient([LONG, "Kısa giriş. " + LONG])
data, _ = _assess_entity_with_recovery(c, build, [{"x": 1}], "İnatçı", "tr")
clean = sanitize_entity_analysis(data, "tr")
check(len(c.users) == 2 and clean["headline_verdict"] == "Kısa giriş.",
      "yine uzun → üçüncü çağrı YOK, sanitize son tam cümlede kesti")
c = FakeClient([" ".join(["word"] * 31) + ".", "Short verdict."])
_assess_entity_with_recovery(c, build, [{"x": 1}], "EN", "en")
check("say fewer things" in c.users[1], "EN'de not İngilizce")

print("== F: prompt kuralları ==")
for lang, needles in {
    "tr": ["en fazla 14 kelime", "en fazla 100 kelime", "daha az şey söyle", "TAM CÜMLE",
           "ağırlıklı olarak olumlu"],
    "en": ["at most 16 words", "at most 100 words", "say fewer things", "COMPLETE SENTENCES",
           "largely positive"],
}.items():
    r = entity_assessment_rules(lang)
    missing = [n for n in needles if n not in r]
    check(not missing, f"{lang} kuralları tam (eksik: {missing})")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
