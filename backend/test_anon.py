"""Bölüm 1 — anonim cihaz oturumu + hesaba yükseltme + izolasyon (izole temp DB).

Çalıştır: python test_anon.py
"""
import os
import tempfile

_db = os.path.join(tempfile.gettempdir(), "nr_test_anon.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_SECRET="anonsecret1234567", ADMIN_USERNAME="root",
    NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_MAX_ENTITIES_ANON="3", NEWSRADAR_DAILY_BUDGET_USD="0",
    NEWSRADAR_COOKIE_SECURE="off", NEWSRADAR_COOKIE_SAMESITE="lax",  # http testserver
    NEWSRADAR_LLM_PROVIDER="anthropic",
)

from fastapi.testclient import TestClient  # noqa: E402
from app.api.main import app  # noqa: E402
from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import User, UserWatchlist  # noqa: E402

init_db()  # 'with TestClient' kullanmadığımız için tabloları elle oluştur

PASS = FAIL = 0
def check(cond, msg):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✓ {msg}")
    else: FAIL += 1; print(f"  ✗ FAIL: {msg}")


def new_device_client():
    """Kendi cookie kavanozu olan yeni TestClient = yeni cihaz."""
    return TestClient(app)


def main():
    print("== Anon bootstrap: şifresiz oturum + cookie ==")
    A = new_device_client()
    r = A.post("/session/bootstrap")
    check(r.status_code == 200, f"bootstrap 200 (şifre gerektirmedi): {r.status_code}")
    body = r.json()
    tokA = body["token"]
    check(body["user"]["is_anonymous"] is True, "kullanıcı is_anonymous=True (misafir)")
    check(app.state if False else "nr_device" in r.cookies or "nr_device" in A.cookies,
          "HttpOnly device cookie yazıldı")
    hA = {"Authorization": f"Bearer {tokA}"}

    print("\n== Aynı cihaz (cookie) → AYNI kullanıcı ==")
    r2 = A.post("/session/bootstrap")  # cookie jar aynı
    check(r2.json()["user"]["id"] == body["user"]["id"], "aynı cookie → aynı anon kullanıcı (yeni değil)")
    with session_scope() as db:
        n_users = db.query(User).count()
    check(n_users == 1, f"tek anon kullanıcı oluştu ({n_users})")

    print("\n== Anon kullanıcı uygulamayı kullanabiliyor (kota 3) ==")
    for i in range(3):
        rr = A.post("/entities", json={"name": f"E{i}", "type": "keyword", "query": f"e{i}"}, headers=hA)
        check(rr.status_code == 201, f"anon {i+1}. entity 201")
    rr = A.post("/entities", json={"name": "E3", "type": "keyword", "query": "e3"}, headers=hA)
    check(rr.status_code == 403, f"anon 4. entity 403 (kota 3): {rr.status_code}")

    print("\n== İki farklı cihaz → İZOLASYON ==")
    B = new_device_client()  # yeni cookie jar = yeni cihaz
    rb = B.post("/session/bootstrap")
    tokB = rb.json()["token"]; hB = {"Authorization": f"Bearer {tokB}"}
    check(rb.json()["user"]["id"] != body["user"]["id"], "cihaz B farklı anon kullanıcı")
    B.post("/entities", json={"name": "OnlyB", "type": "keyword", "query": "onlyb"}, headers=hB)
    a_list = {c["name"] for c in A.get("/entities", headers=hA).json()}
    b_list = {c["name"] for c in B.get("/entities", headers=hB).json()}
    check("OnlyB" not in a_list, f"A, B'nin listesini GÖRMÜYOR (A: {a_list})")
    check(a_list == {"E0", "E1", "E2"} and b_list == {"OnlyB"}, "iki cihaz listeleri izole")

    print("\n== Hesaba yükseltme (liste korunur) ==")
    up = A.post("/users/upgrade", json={"username": "alice", "password": "parola12345"}, headers=hA)
    check(up.status_code == 200, f"upgrade 200 ({up.status_code})")
    check(up.json()["user"]["is_anonymous"] is False and up.json()["user"]["username"] == "alice",
          "artık kalıcı hesap (is_anonymous=False, username=alice)")
    new_tok = up.json()["token"]
    a_list2 = {c["name"] for c in A.get("/entities", headers={"Authorization": f"Bearer {new_tok}"}).json()}
    check(a_list2 == {"E0", "E1", "E2"}, f"upgrade sonrası liste KORUNDU ({a_list2})")
    # yeni şifreyle giriş (genel şifre kapısı YOK)
    lg = new_device_client().post("/users/login", json={"username": "alice", "password": "parola12345"})
    check(lg.status_code == 200, f"yeni şifreyle giriş 200 (genel kapı yok): {lg.status_code}")
    # eski anon token (upgrade'den önce) artık geçersiz (pwhash değişti)
    old = A.get("/users/me", headers=hA)
    check(old.status_code == 401, f"upgrade öncesi token geçersiz (pwhash değişti): {old.status_code}")

    print("\n== Kayıt genel şifre GEREKTİRMİYOR (herkese açık) ==")
    rg = new_device_client().post("/users/register", json={"username": "bob", "password": "parola12345"})
    check(rg.status_code == 201, f"register 201 (genel token'sız): {rg.status_code}")

    print(f"\n{'='*50}\nSONUÇ: {PASS} geçti, {FAIL} başarısız")
    return FAIL == 0


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
