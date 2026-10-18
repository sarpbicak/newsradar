"""100k fiyat bariyeri — değerlendirme bağlamı sınırın altında tutuluyor mu (gerçek API yok).

Doğrular:
  (A) küçük bağlam → kırpma yok, kesin sayım (count_tokens) çağrılmıyor
  (B) sınırı aşan bağlam → en eski makaleler kırpılıyor, sonuç sınırın altında, loglanıyor
  (C) istemcide count_prompt_tokens yoksa (OpenRouter/sahte) karakter tahminiyle kırpılıyor
Çalıştır: python test_cost_guard.py
"""
import logging
import os
import tempfile

_db = os.path.join(tempfile.gettempdir(), "nr_test_cost_guard.db")
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y", NEWSRADAR_SCHEDULER="off",
    NEWSRADAR_SEED_ON_START="off", NEWSRADAR_LLM_PROVIDER="anthropic",
)

from app.analysis import pipeline  # noqa: E402
from app.analysis.pipeline import ASSESSMENT_PROMPT_TOKEN_LIMIT, _fit_assessment_context  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


class LogCap(logging.Handler):
    def __init__(self): super().__init__(); self.msgs = []
    def emit(self, r): self.msgs.append(r.getMessage())


cap = LogCap()
logging.getLogger("newsradar.analysis").addHandler(cap)

TOKENS_PER_ITEM = 1_000


class CountingClient:
    """count_prompt_tokens: makale başına 1000 token + 3000 sabit (system+tool)."""
    def __init__(self): self.counts = 0
    def count_prompt_tokens(self, *, system, user, tool):
        self.counts += 1
        return 3_000 + user.count("§") * TOKENS_PER_ITEM


def build(items):
    return "".join("§" + "x" * 2_000 for _ in items)  # makale başına ~2000 karakter


print("== A: küçük bağlam ==")
c = CountingClient()
items = list(range(10))
out = _fit_assessment_context(c, build, items, "Small")
check(out == items, "10 makale → kırpma yok")
check(c.counts == 0, "tahmin sınırın çok altında → count_tokens çağrılmadı")

print("== B: sınırı aşan bağlam (kesin sayım) ==")
c = CountingClient()
items = list(range(150))  # 3000 + 150k token
cap.msgs.clear()
out = _fit_assessment_context(c, build, items, "Big")
final = 3_000 + len(out) * TOKENS_PER_ITEM
check(final <= ASSESSMENT_PROMPT_TOKEN_LIMIT, f"kırpılmış prompt {final} ≤ {ASSESSMENT_PROMPT_TOKEN_LIMIT}")
check(out == items[: len(out)] and len(out) > 50, f"en yeniler korundu, en eskiler düştü ({len(out)} makale)")
check(any("kırpıldı" in m and "[Big]" in m for m in cap.msgs), "kırpma loglandı")

print("== C: count_prompt_tokens yok → karakter tahmini ==")
class NoCounter:
    pass
items = list(range(150))  # ~300k karakter → tahmin ~120k token
out = _fit_assessment_context(NoCounter(), build, items, "Est")
est = (len(pipeline.SYSTEM_PROMPT) + len(build(out))) / pipeline._CHARS_PER_TOKEN_EST
check(len(out) < 150 and est <= ASSESSMENT_PROMPT_TOKEN_LIMIT * 1.05,
      f"tahminle kırpıldı ({len(out)} makale, ~{int(est)} token)")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
