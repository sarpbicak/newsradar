"""Kayıtta e-posta: zorunlu, biçim, benzersiz (küçük harf), e-postayla giriş, eski hesaba
ekleme, NULL hariç kısmi index, admin listesi (izole temp DB, anahtarsız).

Çalıştır: python test_email.py
"""
import os
import tempfile

_db = os.path.join(tempfile.gettempdir(), "nr_test_email.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="genelsifre", APP_SECRET="em-secret-1234567890",
    ADMIN_USERNAME="rootadmin", NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_MAX_USERS="0", NEWSRADAR_TRUSTED_PROXY="render", NEWSRADAR_COOKIE_SECURE="off",
    NEWSRADAR_COOKIE_SAMESITE="lax", NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR="0",
)

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402
from app.db.database import SessionLocal, engine  # noqa: E402
from app.db.models import User  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


_ip = [0]


def xff():
    """Her istek farklı IP: art arda bilinçli hatalar IP kilidine (429) takılmasın."""
    _ip[0] += 1
    return {"X-Forwarded-For": f"198.51.100.{_ip[0]}"}


def reg(c, username, email, pw="parola12345"):
    body = {"username": username, "password": pw}
    if email is not None:
        body["email"] = email
    return c.post("/users/register", json=body, headers=xff())


with TestClient(app) as c:
    print("== Kayıt: zorunlu + biçim")
    check(reg(c, "rootadmin", "admin@example.com").status_code == 201, "admin kaydı (e-postalı) 201")
    r = reg(c, "nomail", None)
    check(r.status_code == 422 and "e-posta" in r.json()["detail"].lower(), f"e-postasız kayıt 422 ({r.status_code})")
    for bad in ("plain", "a@b", "a b@c.com", "@example.com", "x@example", "a@@b.com"):
        check(reg(c, "badmail", bad).status_code == 422, f"geçersiz biçim reddedilir: {bad!r}")

    print("== Benzersiz (büyük/küçük harf duyarsız), küçük harfle saklanır")
    r = reg(c, "alice", "  Alice@Example.COM ")
    check(r.status_code == 201 and r.json()["user"]["email"] == "alice@example.com", f"küçük harf + kırpma ({r.json().get('user', {}).get('email')})")
    r = reg(c, "alice2", "ALICE@example.com")
    check(r.status_code == 409, f"aynı e-posta farklı harfle 409 ({r.status_code})")

    print("== Giriş: kullanıcı adı ya da e-posta")
    check(c.post("/users/login", headers=xff(), json={"username": "alice", "password": "parola12345"}).status_code == 200, "kullanıcı adıyla giriş")
    r = c.post("/users/login", headers=xff(), json={"username": "ALICE@example.com", "password": "parola12345"})
    check(r.status_code == 200 and r.json()["user"]["username"] == "alice", f"e-postayla giriş ({r.status_code})")
    check(c.post("/users/login", headers=xff(), json={"username": "alice@example.com", "password": "yanlis1234"}).status_code == 401, "yanlış şifre 401")
    check(c.post("/users/login", headers=xff(), json={"username": "kimse@example.com", "password": "parola12345"}).status_code == 401, "bilinmeyen e-posta 401")

    print("== Misafirden hesaba geçiş: e-posta zorunlu")
    c.cookies.clear()
    anon = c.post("/session/bootstrap").json()
    AH = {"Authorization": f"Bearer {anon['token']}"}
    r = c.post("/users/upgrade", json={"username": "guestup", "password": "parola12345"}, headers=AH)
    check(r.status_code == 422, f"e-postasız upgrade 422 ({r.status_code})")
    r = c.post("/users/upgrade", json={"username": "guestup", "password": "parola12345", "email": "alice@example.com"}, headers=AH)
    check(r.status_code == 409, f"kullanılan e-postayla upgrade 409 ({r.status_code})")
    r = c.post("/users/upgrade", json={"username": "guestup", "password": "parola12345", "email": "guest@example.com"}, headers=AH)
    check(r.status_code == 200 and r.json()["user"]["email"] == "guest@example.com", f"upgrade e-postayla 200 ({r.status_code})")

    print("== Eski hesap (e-postasız) → hesap menüsünden ekleme; birden çok NULL serbest")
    with SessionLocal() as s:
        for name in ("eski1", "eski2"):
            s.add(User(username=name, password_hash="x", email=None))
        s.commit()
    check(True, "iki e-postasız eski hesap aynı anda var (kısmi index NULL'ları saymaz)")
    lg = c.post("/users/login", headers=xff(), json={"username": "alice", "password": "parola12345"}).json()
    H = {"Authorization": f"Bearer {lg['token']}"}
    r = c.post("/users/me/email", json={"email": "alice.new@example.com"}, headers=H)
    check(r.status_code == 200 and r.json()["email"] == "alice.new@example.com", f"e-posta değiştir/ekle ({r.status_code})")
    r = c.post("/users/me/email", json={"email": "guest@example.com"}, headers=H)
    check(r.status_code == 409, f"başkasının e-postası 409 ({r.status_code})")
    r = c.post("/users/me/email", json={"email": "bozuk"}, headers=H)
    check(r.status_code == 422, f"geçersiz biçim 422 ({r.status_code})")
    c.cookies.clear()
    anon2 = c.post("/session/bootstrap").json()
    r = c.post("/users/me/email", json={"email": "x@example.com"}, headers={"Authorization": f"Bearer {anon2['token']}"})
    check(r.status_code == 403, f"misafir e-posta ekleyemez (önce hesap) ({r.status_code})")

    print("== Index ve admin listesi")
    with engine.begin() as conn:
        idx = conn.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name='ux_users_email'").scalar()
    check(idx and "UNIQUE" in idx.upper() and "WHERE" in idx.upper(), f"kısmi benzersiz index ({idx})")
    adm = c.post("/users/login", headers=xff(), json={"username": "rootadmin", "password": "parola12345"}).json()
    rows = c.get("/admin/users", headers={"Authorization": f"Bearer {adm['token']}"}).json()
    emails = {r["username"]: r.get("email") for r in rows}
    check(emails.get("alice") == "alice.new@example.com" and emails.get("eski1") is None, f"admin listesinde e-posta ({emails.get('alice')})")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
