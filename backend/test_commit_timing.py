"""Commit zamanlaması — yazma uçları YANIT GÖNDERİLMEDEN ÖNCE commit eder (izole temp DB).

Sorun: get_db varsayılan (scope="request") yield-bağımlılığıydı; yield sonrası commit
yanıt gönderildikten SONRA çalışıyordu → istemci 200/204 alıp hemen ardından eski veriyi
görebiliyordu (F29: silinen kullanıcının token'ı ara ara 200) ve commit başarısız olsa da
istemciye "başarılı" deniyordu.

Yöntem: uygulama, ASGI `send`'i yakalayan ince bir sarmalayıcıyla çağrılır. Yanıtın
BAŞLIKLARI (http.response.start) gönderildiği anda, istek oturumundan BAĞIMSIZ bir
sqlite3 bağlantısıyla DB okunur. WAL modunda bağımsız okuyucu yalnızca COMMIT edilmiş
veriyi görür → "istemci yanıtı aldığında veri kalıcı mı?" sorusu yarışsız, deterministik
cevaplanır (TestClient tüm ASGI çağrısının bitmesini beklediği için tek başına yetmez).

Doğrular:
  (A) POST /session/bootstrap: yeni anon kullanıcı yanıt anında kalıcı; token hemen çalışır
  (B) POST /users/me/guide-dismiss: bayrak yanıt anında kalıcı
  (C) GET  /entities/{id}/dashboard: view_entity olayı (GET'te yazma) yanıt anında kalıcı
  (D) DELETE /entities/{id}: watchlist satırı + remove_entity olayı yanıt anında kalıcı
  (E) POST /feedback: geri bildirim satırı yanıt anında kalıcı
  (F) DELETE /admin/users/{id}: kullanıcı yanıt anında silinmiş; token'ı hemen 401 (F29)
  (G) POST /chat (SSE, sahte LLM): chat olayı akış BAŞLAMADAN kalıcı; akış sorunsuz
      tamamlanır; akış içindeki kendi-oturumlu yazma (LLM kullanım kaydı) da kalıcı
  (H) commit başarısız → 500 (200 DEĞİL) + değişiklik geri alınmış
  (I) tüm route'larda get_db scope="function" (aynı istekte tek oturum + erken commit)
Çalıştır: python test_commit_timing.py
"""
import ast
import logging
import os
import pathlib
import sqlite3
import tempfile

_db = os.path.join(tempfile.gettempdir(), "nr_test_commit_timing.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="testpass", APP_SECRET="test-secret-commit-timing",
    ADMIN_USERNAME="theadmin", NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_DAILY_BUDGET_USD="0", NEWSRADAR_LLM_PROVIDER="anthropic",
    NEWSRADAR_MAX_USERS="0", NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR="0",
    NEWSRADAR_FEEDBACK_PER_IP_HOUR="0",
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event, select  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from app.api import routes_chat  # noqa: E402
from app.api.main import app  # noqa: E402
from app.db.database import SessionLocal, get_db, init_db, session_scope  # noqa: E402
from app.db.models import Entity, User, UserWatchlist  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


def q(sql, *args):
    """İstek oturumundan BAĞIMSIZ bağlantı — yalnızca commit edilmiş veriyi görür."""
    con = sqlite3.connect(_db, timeout=5)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


class Probe:
    """ASGI sarmalayıcı: yanıt başlıkları gönderildiği AN `fn()`'i çalıştırıp sonucu saklar."""

    def __init__(self, inner):
        self.inner = inner
        self.fn = None
        self.seen = None
        self.status = None

    async def __call__(self, scope, receive, send):
        async def _send(msg):
            if msg["type"] == "http.response.start":
                self.status = msg["status"]
                if self.fn is not None:
                    self.seen = self.fn()
            await send(msg)
        await self.inner(scope, receive, _send)

    def arm(self, fn):
        self.fn, self.seen, self.status = fn, None, None


init_db()
probe = Probe(app)
client = TestClient(probe, raise_server_exceptions=False)


def register(username, password="pw12345678"):
    r = client.post("/users/register", json={"username": username, "password": password})
    assert r.status_code == 201, r.text
    return r.json()["token"], r.json()["user"]["id"]


def bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


admin_tok, admin_id = register("theadmin")
tok, uid = register("ayse")
h = bearer(tok)
with session_scope() as s:
    e1 = Entity(name="Tesla", type="ticker", query="TSLA")
    e2 = Entity(name="Nvidia", type="ticker", query="NVDA")
    s.add_all([e1, e2]); s.flush()
    s.add_all([UserWatchlist(user_id=uid, entity_id=e1.id),
               UserWatchlist(user_id=uid, entity_id=e2.id)])
    tsla_id, nvda_id = e1.id, e2.id


def events(user_id, etype):
    return q("SELECT COUNT(*) FROM usage_events WHERE user_id=? AND event_type=?",
             user_id, etype)[0][0]


print("== A: /session/bootstrap — yeni anon kullanıcı yanıt anında kalıcı ==")
before = q("SELECT COUNT(*) FROM users")[0][0]
probe.arm(lambda: q("SELECT COUNT(*) FROM users")[0][0])
r = client.post("/session/bootstrap")
check(r.status_code == 200, f"bootstrap 200 ({r.status_code})")
check(probe.seen == before + 1, f"yanıt anında anon kullanıcı commit edilmiş ({before}→{probe.seen})")
anon_tok = r.json()["token"]
fresh = TestClient(app)  # cookie'siz istemci: yalnızca token ile doğrula
check(fresh.get("/users/me", headers=bearer(anon_tok)).status_code == 200,
      "yeni anon token hemen ardından 200")

print("== B: /users/me/guide-dismiss — bayrak yanıt anında kalıcı ==")
probe.arm(lambda: q("SELECT guide_dismissed FROM users WHERE id=?", uid)[0][0])
r = client.post("/users/me/guide-dismiss", headers=h)
check(r.status_code == 200 and r.json()["guide_dismissed"] is True, f"guide-dismiss 200 ({r.status_code})")
check(probe.seen == 1, f"yanıt anında guide_dismissed=1 commit edilmiş ({probe.seen})")

print("== C: GET dashboard — view_entity olayı yanıt anında kalıcı ==")
n0 = events(uid, "view_entity")
probe.arm(lambda: events(uid, "view_entity"))
r = client.get(f"/entities/{tsla_id}/dashboard", headers=h)
check(r.status_code == 200, f"dashboard 200 ({r.status_code})")
check(probe.seen == n0 + 1, f"yanıt anında view_entity commit edilmiş ({n0}→{probe.seen})")

print("== D: DELETE /entities/{id} — watchlist + olay yanıt anında kalıcı ==")
probe.arm(lambda: (
    q("SELECT COUNT(*) FROM user_watchlist WHERE user_id=? AND entity_id=?", uid, nvda_id)[0][0],
    events(uid, "remove_entity"),
))
r = client.delete(f"/entities/{nvda_id}", headers=h)
check(r.status_code == 204, f"delete entity 204 ({r.status_code})")
check(probe.seen == (0, 1), f"yanıt anında watchlist satırı silinmiş + olay yazılmış ({probe.seen})")
ids = [c["id"] for c in client.get("/entities", headers=h).json()]
check(nvda_id not in ids, "hemen ardından GET /entities silineni göstermiyor")

print("== E: POST /feedback — satır yanıt anında kalıcı ==")
probe.arm(lambda: q("SELECT COUNT(*) FROM feedback WHERE message=?", "commit zamanlaması")[0][0])
r = client.post("/feedback", json={"message": "commit zamanlaması"}, headers=h)
check(r.status_code == 200, f"feedback 200 ({r.status_code})")
check(probe.seen == 1, f"yanıt anında feedback commit edilmiş ({probe.seen})")

print("== F: DELETE /admin/users/{id} — silinen kullanıcının token'ı hemen 401 (F29) ==")
del_tok, del_id = register("todelete")
probe.arm(lambda: q("SELECT COUNT(*) FROM users WHERE id=?", del_id)[0][0])
r = client.delete(f"/admin/users/{del_id}", headers=bearer(admin_tok))
check(r.status_code == 204, f"admin delete 204 ({r.status_code})")
check(probe.seen == 0, f"yanıt anında kullanıcı silinmiş ({probe.seen} satır)")
check(client.get("/users/me", headers=bearer(del_tok)).status_code == 401,
      "silinen kullanıcının token'ı hemen ardından 401")

print("== G: POST /chat (SSE) — olay akıştan önce kalıcı, akış çalışır ==")
from app import budget  # noqa: E402


class FakeChat:
    """Gerçek LLM YOK: birkaç parça üretir, akış sırasında KENDİ oturumuyla kullanım yazar."""

    def stream_chat(self, *, system, messages, max_tokens):
        yield "Merhaba"
        budget.record_llm_call("fake-chat-model", "chat", 3, 2, 0, 0)
        yield " dünya"


_orig_provider = routes_chat.get_llm_provider
routes_chat.get_llm_provider = lambda purpose: FakeChat()
try:
    c0 = events(uid, "chat")
    probe.arm(lambda: events(uid, "chat"))
    r = client.post("/chat", json={"entity_id": tsla_id,
                                   "messages": [{"role": "user", "content": "Ne oldu?"}]},
                    headers=h)
finally:
    routes_chat.get_llm_provider = _orig_provider
check(r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream"),
      f"chat 200 + SSE ({r.status_code})")
check(probe.seen == c0 + 1, f"chat olayı akış başlamadan commit edilmiş ({c0}→{probe.seen})")
body = r.text
check("event: delta" in body and "Merhaba" in body and " dünya" in body
      and "event: done" in body and "event: error" not in body,
      "akış tüm parçaları + done ile tamamlandı (oturum kapanması akışı bozmadı)")
check(q("SELECT COUNT(*) FROM llm_usage WHERE model='fake-chat-model'")[0][0] == 1,
      "akış içindeki kendi-oturumlu kullanım kaydı kalıcı")

print("== H: commit başarısız → 500, değişiklik geri alınmış ==")
_fail_next = {"on": False}


@event.listens_for(SessionLocal, "before_commit")
def _boom(_session):
    if _fail_next["on"]:
        _fail_next["on"] = False
        raise OperationalError("COMMIT", {}, Exception("simüle: database is locked"))


logging.getLogger("newsradar.db").setLevel(logging.CRITICAL)  # beklenen hata logu
_fail_next["on"] = True
probe.arm(None)
r = client.post("/users/me/tutorial-done", headers=h)
check(probe.status == 500 and r.status_code == 500,
      f"commit hatasında istemci 500 alır, 200 DEĞİL (gönderilen={probe.status})")
detail = r.json().get("detail", "") if r.headers.get("content-type", "").startswith("application/json") else ""
check("kaydedilemedi" in detail and "locked" not in detail,
      f"genel hata mesajı, iç ayrıntı sızmıyor ({detail!r})")
check(q("SELECT tutorial_done FROM users WHERE id=?", uid)[0][0] == 0,
      "başarısız commit'te tutorial_done kalıcı OLMADI")
event.remove(SessionLocal, "before_commit", _boom)
r = client.post("/users/me/tutorial-done", headers=h)
check(r.status_code == 200 and q("SELECT tutorial_done FROM users WHERE id=?", uid)[0][0] == 1,
      "hata geçince aynı istek başarılı ve kalıcı")

print("== I: tüm route'larda get_db scope='function' ==")


def _walk(dep, out, path):
    for sub in dep.dependencies:
        if sub.call is get_db:
            out.append((path, sub.scope))
        _walk(sub, out, path)


def _routes(routes):
    """Route'ları düzleştir (yeni FastAPI include_router'ı _IncludedRouter ile sarar)."""
    for r in routes:
        inner = getattr(r, "original_router", None)
        if inner is not None:
            yield from _routes(inner.routes)
        else:
            yield r


found = []
for route in _routes(app.routes):
    dep = getattr(route, "dependant", None)
    if dep is not None:
        _walk(dep, found, f"{','.join(sorted(getattr(route, 'methods', []) or []))} {route.path}")
bad = sorted({p for p, sc in found if sc != "function"})
check(len(found) > 30, f"get_db kullanan route bağımlılıkları bulundu ({len(found)})")
check(not bad, f"scope='function' olmayan get_db kullanımı yok ({bad[:5]})")

# Kaynak taraması (FastAPI sürümünden bağımsız): app/ altındaki HER Depends(get_db ...)
# çağrısı scope="function" taşımalı (router-düzeyi bağımlılıklar dahil).
src_bad, src_n = [], 0
for f in pathlib.Path(__file__).parent.joinpath("app").rglob("*.py"):
    for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
        if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Depends"
                and node.args and getattr(node.args[0], "id", None) == "get_db"):
            src_n += 1
            sc = [k.value.value for k in node.keywords
                  if k.arg == "scope" and isinstance(k.value, ast.Constant)]
            if sc != ["function"]:
                src_bad.append(f"{f.name}:{node.lineno}")
check(src_n > 30 and not src_bad,
      f"kaynakta {src_n} Depends(get_db) — hepsi scope='function' ({src_bad[:5]})")

print(f"\nSONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
