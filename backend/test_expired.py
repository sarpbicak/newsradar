"""Lookback dışı bekleyen makaleler EXPIRED — LLM'e hiç gönderilmez (izole temp DB).

Doğrular:
  (A) yayın tarihi lookback dışındaki bekleyen → expired; içindeki → bekler
  (B) yayın tarihi yoksa çekilme tarihine bakılır
  (C) zaten analiz edilmiş ya da ön-filtrelenmiş eski makaleye dokunulmaz
  (D) analyze_all_async yalnızca pencere içindekileri LLM'e gönderir; totals.expired
  (E) idempotent; kuyruk (queued) ve /entities/{id}/dashboard sayıları expired'ı dışlar
Çalıştır: python test_expired.py
"""
import asyncio
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_expired.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y" * 20,
                  NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
                  NEWSRADAR_LLM_PROVIDER="anthropic", NEWSRADAR_LOOKBACK_HOURS="48",
                  NEWSRADAR_DAILY_BUDGET_USD="0")

from app.analysis.pipeline import analyze_all_async, expire_stale_pending  # noqa: E402
from app.analysis.schemas import ARTICLE_ANALYSIS_TOOL  # noqa: E402
from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import PREFILTER_VERSION, Article, Entity  # noqa: E402
from app.refresh import _queued_count  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


now = datetime.now(timezone.utc)
init_db()
with session_scope() as s:
    e = Entity(name="Exp", type="keyword", query="Exp", active=True, language="en")
    s.add(e); s.flush()
    eid = e.id
    words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]

    def art(i, **kw):
        base = dict(entity_id=eid, url=f"http://x/{i}", url_hash=f"h{i}", source="s",
                    title=f"{words[i]} {words[(i + 3) % 8]}{i} story{i * 11}",
                    description="d", provider="t", analyzed=False, prefiltered=False)
        base.update(kw)
        return Article(**base)

    s.add(art(0, published_at=now - timedelta(hours=1)))                    # pencere içi → kalır
    s.add(art(1, published_at=now - timedelta(hours=47)))                   # pencere içi → kalır
    s.add(art(2, published_at=now - timedelta(hours=49)))                   # dışı → expired
    s.add(art(3, published_at=now - timedelta(days=30)))                    # dışı → expired
    s.add(art(4, published_at=None, fetched_at=now - timedelta(days=5)))    # tarihsiz, eski çekim → expired
    s.add(art(5, published_at=None, fetched_at=now - timedelta(hours=2)))   # tarihsiz, yeni çekim → kalır
    s.add(art(6, published_at=now - timedelta(days=9), analyzed=True, relevance=0.9))  # analiz edilmiş → dokunma
    s.add(art(7, published_at=now - timedelta(days=9), prefiltered=True,
              prefilter_version=PREFILTER_VERSION))                         # ön-filtreli → dokunma

print("== A/B/C: expire_stale_pending ==")
n = expire_stale_pending()
check(n == 3, f"3 bekleyen expired işaretlendi ({n})")
with session_scope() as s:
    exp = sorted(int(a.url.rsplit("/", 1)[1]) for a in s.query(Article).filter(Article.expired.is_(True)))
check(exp == [2, 3, 4], f"doğru makaleler: lookback dışı + tarihsiz eski çekim ({exp})")
check(expire_stale_pending() == 0, "idempotent (ikinci çalıştırma 0)")

print("== D: LLM'e yalnızca pencere içindekiler gider ==")
with session_scope() as s:  # yeni bir eski bekleyen: analiz sırasında işaretlenmeli
    s.add(Article(entity_id=eid, url="http://x/9", url_hash="h9", source="s", title="india juliet late9",
                  description="d", provider="t", analyzed=False, prefiltered=False,
                  published_at=now - timedelta(days=3)))
sent_ids = []


class Client:
    model = "fake"
    def call_tool(self, *, system, user, tool, max_tokens=4096):
        if tool["name"] != ARTICLE_ANALYSIS_TOOL["name"]:
            return {"headline_verdict": "v.", "summary": "s."}
        ids = [int(x) for x in re.findall(r"id=(\d+)", user)]
        sent_ids.extend(ids)
        return {"analyses": [{"id": i, "sentiment": 0.1, "event_type": "other", "risk_flags": [],
                              "impact_horizon": "short", "relevance": 0.9, "rationale": "r.",
                              "co_mentioned_entities": []} for i in ids]}


t = asyncio.run(analyze_all_async(Client(), entity_ids={eid}))
with session_scope() as s:
    url_of = {a.id: int(a.url.rsplit("/", 1)[1]) for a in s.query(Article)}
sent = sorted(url_of[i] for i in sent_ids)
check(sent == [0, 1, 5], f"LLM'e yalnızca pencere içindekiler gitti ({sent})")
check(t.expired == 1 and t.llm_articles == 3, f"totals.expired=1 (yeni eski makale), llm_articles=3 ({t.expired}, {t.llm_articles})")

print("== E: sayılar ==")
check(_queued_count({eid}) == 0, f"kuyruk expired'ı dışlıyor ({_queued_count({eid})})")
from fastapi.testclient import TestClient  # noqa: E402
from app.api import routes_dashboard  # noqa: E402
from app.api.main import app  # noqa: E402
from app.api.routes_auth import get_current_user  # noqa: E402
from app.db.models import User, UserWatchlist  # noqa: E402

with session_scope() as s:
    u = User(username="u1", password_hash="x")
    s.add(u); s.flush()
    s.add(UserWatchlist(user_id=u.id, entity_id=eid))
    uid = u.id
app.dependency_overrides[get_current_user] = lambda: SimpleUser()


class SimpleUser:
    id, is_admin, language, is_anonymous = uid, False, "tr", False


with TestClient(app) as c:
    st = c.get(f"/entities/{eid}/dashboard").json()["article_status"]
check(st["pending"] == 0 and st["expired"] == 4, f"dashboard: pending=0, expired=4 ({st})")
app.dependency_overrides.clear()

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
