"""Kesilmede batch bölme testi — sahte client (gerçek API yok, izole temp DB).

Doğrular: (1) kesilmede batch bölünüp tamamlanıyor, makale kaybı yok; (2) bölme
logları görünüyor; (3) tek makale bile kesilirse atlanıp uyarı ekleniyor (sonsuz
döngü yok); (4) kesilme DIŞI hatalar bölünmüyor.
"""
import logging
import os
import re
import tempfile

_db = os.path.join(tempfile.gettempdir(), "nr_test_trunc.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y", NEWSRADAR_SCHEDULER="off",
    NEWSRADAR_SEED_ON_START="off", NEWSRADAR_BATCH_SIZE="10",
    NEWSRADAR_LLM_PROVIDER="anthropic",
)

from app.analysis.claude_client import ClaudeError, TruncationError  # noqa: E402
from app.analysis.pipeline import analyze_entity_sync  # noqa: E402
from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import Article, Entity  # noqa: E402

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


class FakeClient:
    """Batch'te >threshold makale varsa TruncationError; değilse geçerli analiz döndürür.
    mode='error' → kesilme DIŞI ClaudeError (bölünmemeli)."""
    model = "fake-model"
    def __init__(self, threshold=3, mode="truncate"):
        self.threshold, self.mode = threshold, mode
        self.batch_calls = []  # her makale-batch çağrısındaki makale sayısı

    def call_tool(self, *, system, user, tool, max_tokens=4096):
        if tool["name"] == "record_article_analyses":
            ids = [int(x) for x in re.findall(r"\[id=(\d+)\]", user)]
            self.batch_calls.append(len(ids))
            if self.mode == "error":
                raise ClaudeError("fake rate-limit / bağlantı hatası")
            if len(ids) > self.threshold:
                raise TruncationError(f"fake truncation ({len(ids)} makale)")
            return {"analyses": [
                {"id": i, "sentiment": 0.1, "event_type": "other", "risk_flags": [],
                 "impact_horizon": "short", "relevance": 0.8, "rationale": "ok"} for i in ids]}
        # entity değerlendirme aracı → geçerli assessment
        return {"headline_verdict": "test hüküm", "ai_take": "test yorum",
                "risk_score": 40, "sentiment_trend": "stable", "top_drivers": ["a", "b", "c"],
                "summary": "test özet", "stance": "neutral", "conviction": "medium",
                "what_to_verify": ["x"], "invalidation": "y"}


# Başlık-benzerliği dedup'ı (Jaccard, len>=4 token) TETİKLENMESİN diye her makaleye
# ÇAKIŞMAYAN benzersiz kelimeler ver (rakamlar len<4 olduğu için atılır → aynılaşır).
_VOCAB = ("earnings product lawsuit merger expansion recall partnership hiring "
          "factory patent dividend export import upgrade downgrade rollout buyback "
          "settlement guidance outlook contract subsidy tariff").split()
_seed_n = 0
def seed_entity(n_articles=10):
    global _seed_n
    _seed_n += 1
    tag = f"FAKE{_seed_n}"
    with session_scope() as db:
        e = Entity(name=f"FakeCo{_seed_n}", type="ticker", query=tag, active=True)
        db.add(e); db.flush()
        for i in range(n_articles):
            w1, w2 = _VOCAB[(2 * i) % len(_VOCAB)], _VOCAB[(2 * i + 1) % len(_VOCAB)]
            db.add(Article(
                entity_id=e.id, url=f"http://x/{tag}/{i}", url_hash=f"h{tag}{i}",
                title=f"{w1} {w2} {tag}{i}", source="src", description="özet " * 10,
                provider="test", analyzed=False, prefiltered=False,
            ))
        return e.id


def analyzed_count(eid):
    with session_scope() as db:
        return db.query(Article).filter(Article.entity_id == eid,
                                        Article.analyzed.is_(True)).count()


def main():
    init_db()
    cap = LogCap()
    # basicConfig çağrılmadığı için INFO logları düşer → logger'ı INFO'ya çek + handler ekle.
    lg = logging.getLogger("newsradar.analysis")
    lg.setLevel(logging.INFO)
    lg.addHandler(cap)

    print("== TEST A: 10 makale, threshold=3 → bölünerek TAM tamamlanır ==")
    eid = seed_entity(10)
    fc = FakeClient(threshold=3, mode="truncate")
    cap.msgs.clear()
    totals = analyze_entity_sync(eid, fc)
    n = analyzed_count(eid)
    check(n == 10, f"10/10 makale analiz edildi — KAYIP YOK (analyzed={n})")
    check(fc.batch_calls[0] == 10, f"İlk çağrı 10 makale (görülen: {fc.batch_calls[0]})")
    check(any(c <= 3 for c in fc.batch_calls) and len(fc.batch_calls) > 1,
          f"Batch bölündü (çağrı boyutları: {fc.batch_calls})")
    split_logs = [m for m in cap.msgs if "kesildi" in m and "yeniden deneniyor" in m]
    check(len(split_logs) >= 1, f"Bölme logları var ({len(split_logs)} satır, ör: {split_logs[:1]})")

    print("\n== TEST B: her şey kesilir (threshold=0) → tek makaleye iner, atlar, döngü yok ==")
    eid2 = seed_entity(4)
    fc2 = FakeClient(threshold=0, mode="truncate")
    totals2 = analyze_entity_sync(eid2, fc2)
    n2 = analyzed_count(eid2)
    skip_warns = [w for w in totals2.warnings if w["code"] == "article_truncated"]
    check(n2 == 0, f"Hiçbiri analiz edilemedi (analyzed={n2})")
    check(len(skip_warns) == 4, f"Her makale için 'atlandı' uyarısı (4 beklenir: {len(skip_warns)})")
    check(min(fc2.batch_calls) == 1, f"Tek makaleye kadar indi (en küçük çağrı: {min(fc2.batch_calls)})")

    print("\n== TEST C: kesilme DIŞI hata → BÖLÜNMEZ (tek çağrı, uyar + devam) ==")
    eid3 = seed_entity(10)
    fc3 = FakeClient(mode="error")
    totals3 = analyze_entity_sync(eid3, fc3)
    n3 = analyzed_count(eid3)
    check(n3 == 0, f"Hata → analiz yok (analyzed={n3})")
    check(len(fc3.batch_calls) == 1, f"BÖLÜNMEDİ — tek çağrı (görülen: {len(fc3.batch_calls)} çağrı)")
    check(any(w["code"] == "batch_error" for w in totals3.warnings), "Uyarı kodu batch_error (bölünmedi)")

    print(f"\n{'='*50}\nSONUÇ: {PASS} geçti, {FAIL} başarısız")
    return FAIL == 0


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
