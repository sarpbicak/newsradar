"""Sağlayıcı kalıcı kota hatası (403 key limit / 402 bakiye) — tek uyarı + erken durdurma.

Doğrular:
  (A) call_tool sürekli 403 → yenileme İLK hatada durur: TEK kota uyarısı, batch başına
      uyarı YOK (eski hata: 89 aynı uyarı), call_tool çağrısı toplam batch sayısından çok az.
  (B) 402/403 → ProviderQuotaError; 500 gibi diğer statüler → sıradan ClaudeError (durdurmaz).
  (C) totals.quota_error True + status_code taşınıyor (sağlık paneli için).

Sahte client, gerçek API yok, izole temp DB. Çalıştır: python test_provider_quota.py
"""
import asyncio
import os
import re
import tempfile

_db = os.path.join(tempfile.gettempdir(), "nr_test_quota.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y", NEWSRADAR_SCHEDULER="off",
    NEWSRADAR_SEED_ON_START="off", NEWSRADAR_BATCH_SIZE="10",
    NEWSRADAR_LLM_PROVIDER="anthropic", NEWSRADAR_ANALYSIS_CONCURRENCY="4",
)

from app.analysis.claude_client import ClaudeError, ProviderQuotaError  # noqa: E402
from app.analysis.pipeline import analyze_all_async  # noqa: E402
from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import Article, Entity  # noqa: E402

PASS = FAIL = 0
def check(cond, msg):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✓ {msg}")
    else: FAIL += 1; print(f"  ✗ FAIL: {msg}")


class QuotaClient:
    """call_tool her zaman ProviderQuotaError(403) atar; çağrı sayısını sayar (thread-güvenli
    değil ama to_thread çağrıları semaphore=concurrency ile sınırlı; sayaç yaklaşık yeter)."""
    model = "fake-model"
    total_prompt_tokens = 0
    total_completion_tokens = 0
    call_count = 0

    def __init__(self, status_code=403):
        self.status_code = status_code
        self.calls = 0

    def call_tool(self, *, system, user, tool, max_tokens=4096):
        self.calls += 1
        raise ProviderQuotaError(f"Key limit exceeded ({self.status_code})", self.status_code)


class ErrorClient(QuotaClient):
    """Kota DIŞI hata (ör. 500) → sıradan ClaudeError. Durdurmamalı; her batch denenmeli."""
    def call_tool(self, *, system, user, tool, max_tokens=4096):
        self.calls += 1
        raise ClaudeError("500 sunucu hatası")


_VOCAB = ("earnings product lawsuit merger expansion recall partnership hiring "
          "factory patent dividend export import upgrade downgrade rollout buyback "
          "settlement guidance outlook contract subsidy tariff").split()
_seed_n = 0
def seed_entity(n_articles=10):
    global _seed_n
    _seed_n += 1
    tag = f"QCO{_seed_n}"
    with session_scope() as db:
        e = Entity(name=f"QuotaCo{_seed_n}", type="ticker", query=tag, active=True)
        db.add(e); db.flush()
        for i in range(n_articles):
            w1, w2 = _VOCAB[(2 * i) % len(_VOCAB)], _VOCAB[(2 * i + 1) % len(_VOCAB)]
            db.add(Article(
                entity_id=e.id, url=f"http://x/{tag}/{i}", url_hash=f"h{tag}{i}",
                title=f"{w1} {w2} {tag}{i}", source="src", description="özet " * 10,
                provider="test", analyzed=False, prefiltered=False,
            ))
        return e.id


def main():
    init_db()

    print("== TEST A: sürekli 403 → TEK uyarı, erken durdurma (89 uyarı YOK) ==")
    n_entities, arts = 8, 10
    for _ in range(n_entities):
        seed_entity(arts)
    fc = QuotaClient(status_code=403)
    totals = asyncio.run(analyze_all_async(fc, entity_ids=None))

    quota_warns = [w for w in totals.warnings if w["code"] == "analysis_unavailable"]
    per_batch_warns = [w for w in totals.warnings if w["code"] in ("batch_error", "assessment_failed")]
    # Batch sayısı ≈ entity başına ceil(10/batch_size)=1 → 8 batch + 8 entity değerlendirme çağrısı.
    # Düzeltme olmasa call_tool ~16+ kez çağrılır ve ~16 uyarı birikir. Düzeltmeyle: ~concurrency kadar.
    check(totals.quota_error is True, "totals.quota_error = True")
    check(totals.quota_status_code == 403, f"status_code taşındı (403): {totals.quota_status_code}")
    check(len(quota_warns) == 1, f"TAM 1 kota uyarısı (görülen: {len(quota_warns)})")
    check(len(per_batch_warns) == 0, f"Batch/değerlendirme başına uyarı YOK (görülen: {len(per_batch_warns)})")
    check(len(totals.warnings) == 1, f"Toplam uyarı = 1 (89 değil): {len(totals.warnings)} → {totals.warnings}")
    # Erken durdurma: ağ çağrısı toplam iş kaleminden (16) belirgin az olmalı.
    total_workitems = n_entities * 2  # kaba: batch + değerlendirme
    check(fc.calls < total_workitems, f"call_tool erken durdu: {fc.calls} < {total_workitems} (her iş denenmedi)")
    print(f"    (bilgi: call_tool {fc.calls} kez çağrıldı, concurrency=4)")

    print("\n== TEST B: 402 (bakiye) da ProviderQuotaError → aynı davranış ==")
    for _ in range(4):
        seed_entity(arts)
    fc2 = QuotaClient(status_code=402)
    totals2 = asyncio.run(analyze_all_async(fc2, entity_ids=None))
    check(totals2.quota_error and totals2.quota_status_code == 402, "402 → quota_error + status_code=402")
    check(len([w for w in totals2.warnings if w["code"] == "analysis_unavailable"]) == 1, "402 → tek uyarı")

    print("\n== TEST C: kota DIŞI hata (500) → DURDURMAZ (her batch denenir, quota_error False) ==")
    ids = [seed_entity(arts) for _ in range(3)]
    fc3 = ErrorClient()
    totals3 = asyncio.run(analyze_all_async(fc3, entity_ids=set(ids)))
    check(totals3.quota_error is False, "500 hatası → quota_error False (kota değil)")
    # Her entity için en az bir batch + değerlendirme denendi (durmadı).
    check(fc3.calls >= 3, f"500'de durmadı — her entity denendi (call_tool {fc3.calls} kez)")
    check(any(w["code"] == "batch_error" for w in totals3.warnings), "500 → sıradan batch_error uyarısı (kota uyarısı değil)")

    print("\n== TEST D: ProviderQuotaError, ClaudeError alt sınıfı (pipeline'in genel yakalaması bozulmaz) ==")
    check(issubclass(ProviderQuotaError, ClaudeError), "ProviderQuotaError ⊂ ClaudeError")

    print(f"\n{'='*54}\nSONUÇ: {PASS} geçti, {FAIL} başarısız")
    return FAIL == 0


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
