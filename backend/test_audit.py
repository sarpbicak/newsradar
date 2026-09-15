"""Bölüm 3b/3c — herkese açık öncesi güvenlik denetimi (canlı testler).

Çalıştır: python test_audit.py
"""
import os
import tempfile

_db = os.path.join(tempfile.gettempdir(), "nr_test_audit.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_SECRET="auditsecret12345", ADMIN_USERNAME="root",
    NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_COOKIE_SECURE="off", NEWSRADAR_COOKIE_SAMESITE="lax",
    NEWSRADAR_LLM_PROVIDER="anthropic",
)

from fastapi.testclient import TestClient  # noqa: E402
from app.api.main import app  # noqa: E402
from app.db.database import init_db  # noqa: E402

init_db()
PASS = FAIL = 0
def check(cond, msg):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✓ {msg}")
    else: FAIL += 1; print(f"  ✗ FAIL: {msg}")


def anon(client):
    r = client.post("/session/bootstrap")
    return {"Authorization": f"Bearer {r.json()['token']}"}


def main():
    with TestClient(app) as client:
        print("== Güvenlik header'ları her yanıtta ==")
        r = client.get("/health")
        h = r.headers
        check(h.get("x-content-type-options") == "nosniff", "X-Content-Type-Options: nosniff")
        check(h.get("referrer-policy") == "no-referrer", "Referrer-Policy: no-referrer")
        check(h.get("x-frame-options") == "DENY", "X-Frame-Options: DENY")
        check("max-age" in (h.get("strict-transport-security") or ""), "HSTS var")
        check("default-src" in (h.get("content-security-policy") or ""), "CSP var")

        print("\n== Girdi doğrulama: aşırı uzun girdi 422 (500 DEĞİL) ==")
        A = anon(client)
        r = client.post("/entities", json={"name": "x" * 5000, "type": "keyword", "query": "y" * 5000}, headers=A)
        check(r.status_code == 422, f"aşırı uzun entity 422 (DoS değil): {r.status_code}")
        # boş isim reddedilir
        r = client.post("/entities", json={"name": "  ", "type": "keyword", "query": "  "}, headers=A)
        check(r.status_code == 422, f"boş isim 422: {r.status_code}")

        print("\n== Hata sızıntısı: temiz mesaj, stack trace YOK ==")
        r = client.get("/entities/999999/dashboard", headers=A)
        check(r.status_code == 404, f"olmayan entity 404: {r.status_code}")
        body = r.text.lower()
        check("traceback" not in body and "file \"" not in body and "sqlalchemy" not in body,
              "yanıtta stack trace / iç ayrıntı YOK")

        print("\n== Yetkilendirme: anonim admin uçlarına erişemez (403) ==")
        r = client.get("/admin/stats", headers=A)
        check(r.status_code == 403, f"anon → /admin/stats 403: {r.status_code}")
        r = client.get("/admin/users", headers=A)
        check(r.status_code == 403, f"anon → /admin/users 403: {r.status_code}")

        print("\n== Token yokken veri uçları 401 ==")
        r = client.get("/entities")
        check(r.status_code == 401, f"token'sız /entities 401: {r.status_code}")

        print("\n== Geçersiz/bozuk token 401 (çökme değil) ==")
        r = client.get("/entities", headers={"Authorization": "Bearer bozuk.token.xx"})
        check(r.status_code == 401, f"bozuk token 401: {r.status_code}")

    print(f"\n{'='*50}\nSONUÇ: {PASS} geçti, {FAIL} başarısız")
    return FAIL == 0


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
