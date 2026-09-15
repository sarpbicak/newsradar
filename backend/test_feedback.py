"""Geri bildirim + admin gelen kutusu — canlı testler (kanıt).

Çalıştır: python test_feedback.py
"""
import os
import tempfile

_db = os.path.join(tempfile.gettempdir(), "nr_test_feedback.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_SECRET="fbsecret12345", ADMIN_USERNAME="root",
    NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_COOKIE_SECURE="off", NEWSRADAR_COOKIE_SAMESITE="lax",
    NEWSRADAR_LLM_PROVIDER="anthropic",
    NEWSRADAR_FEEDBACK_PER_IP_HOUR="5",
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


def register(client, username, password):
    r = client.post("/users/register", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]


def main():
    with TestClient(app) as client:
        print("== İlk kayıt admin olur (ADMIN_USERNAME=root) ==")
        admin_h, admin_u = register(client, "root", "adminpass1")
        check(admin_u["is_admin"] is True, "root admin oldu")

        print("\n== Anon geri bildirim gönderebilir (hesap ZORUNLU değil) ==")
        A = anon(client)
        r = client.post("/feedback", json={"message": "Harika bir araç, teşekkürler!"}, headers=A)
        check(r.status_code == 200 and r.json()["ok"] is True, f"anon feedback 200: {r.status_code}")

        print("\n== Token'sız (tamamen anonim) de gönderebilir ==")
        r = client.post("/feedback", json={"message": "Girişsiz yazıyorum", "contact": "me@example.com"})
        check(r.status_code == 200, f"token'sız feedback 200: {r.status_code}")

        print("\n== Kayıtlı kullanıcı feedback → user_id bağlanır ==")
        u_h, u_obj = register(client, "ayse", "sifre1234")
        r = client.post("/feedback", json={"message": "Grafikler çok net oldu", "contact": "@ayse"}, headers=u_h)
        check(r.status_code == 200, f"kayıtlı feedback 200: {r.status_code}")

        print("\n== Boş / whitespace mesaj reddedilir (422) ==")
        r = client.post("/feedback", json={"message": "   "}, headers=A)
        check(r.status_code == 422, f"boş mesaj 422: {r.status_code}")
        r = client.post("/feedback", json={"message": ""}, headers=A)
        check(r.status_code == 422, f"boş string 422: {r.status_code}")

        print("\n== Aşırı uzun mesaj reddedilir (2000+ → 422) ==")
        r = client.post("/feedback", json={"message": "x" * 2001}, headers=A)
        check(r.status_code == 422, f"2001 karakter 422: {r.status_code}")

        print("\n== Hız sınırı: IP başına saatte 5 (6. → 429) ==")
        # Bu IP (testclient) şu ana kadar 3 BAŞARILI gönderdi (422'ler endpoint'e
        # ulaşmadan reddedildiği için sayaca girmez). 4. ve 5. geçmeli, 6. 429.
        r4 = client.post("/feedback", json={"message": "dördüncü"}, headers=A)
        r5 = client.post("/feedback", json={"message": "beşinci"}, headers=A)
        r6 = client.post("/feedback", json={"message": "altıncı"}, headers=A)
        check(r4.status_code == 200 and r5.status_code == 200,
              f"4. ve 5. gönderim 200: {r4.status_code}/{r5.status_code}")
        check(r6.status_code == 429, f"6. gönderim 429 (spam sınırı): {r6.status_code}")

        print("\n== Admin gelen kutusu: hepsi görünür, okunmamış önce ==")
        r = client.get("/admin/feedback", headers=admin_h)
        check(r.status_code == 200, f"admin feedback 200: {r.status_code}")
        fb = r.json()
        check(len(fb) == 5, f"5 geçerli feedback kayıtlı: {len(fb)}")
        check(all(f["is_read"] is False for f in fb), "hepsi okunmamış")
        # Anon gönderenler "anonim" (username None), kayıtlı 'ayse' görünür.
        names = {f["username"] for f in fb}
        check(None in names, "anonim gönderen username None")
        check("ayse" in names, "kayıtlı gönderen 'ayse' görünür")
        # Cihaz tespiti (testclient UA yok → bilinmiyor kabul; alan mevcut).
        check(all("device" in f for f in fb), "device alanı her satırda var")

        print("\n== Okundu işaretleme + stats sayacı ==")
        target = fb[0]["id"]
        r = client.post(f"/admin/feedback/{target}/read", headers=admin_h)
        check(r.status_code == 204, f"okundu 204: {r.status_code}")
        stats = client.get("/admin/stats", headers=admin_h).json()
        check(stats["unread_feedback"] == 4, f"okunmamış 4'e düştü: {stats['unread_feedback']}")
        # Tekrar liste: okunmuş en sona düşer.
        fb2 = client.get("/admin/feedback", headers=admin_h).json()
        check(fb2[-1]["id"] == target and fb2[-1]["is_read"] is True, "okunan en sona indi")

        print("\n== İZOLASYON: normal kullanıcı gelen kutusuna erişemez (403) ==")
        r = client.get("/admin/feedback", headers=u_h)
        check(r.status_code == 403, f"normal kullanıcı → /admin/feedback 403: {r.status_code}")
        r = client.get("/admin/feedback", headers=A)
        check(r.status_code == 403, f"anon → /admin/feedback 403: {r.status_code}")
        r = client.post(f"/admin/feedback/{target}/read", headers=u_h)
        check(r.status_code == 403, f"normal kullanıcı okundu işaretleyemez 403: {r.status_code}")

        print("\n== Olmayan feedback okundu → 404 ==")
        r = client.post("/admin/feedback/999999/read", headers=admin_h)
        check(r.status_code == 404, f"olmayan feedback 404: {r.status_code}")

    print(f"\n{'='*50}\nSONUÇ: {PASS} geçti, {FAIL} başarısız")
    return FAIL == 0


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
