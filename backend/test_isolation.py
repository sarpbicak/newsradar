"""Kişisel portföy — izolasyon + havuz + kota testleri (izole temp DB, TestClient).

Çalıştır:  python test_isolation.py
Gerçek DB'ye DOKUNMAZ (NEWSRADAR_DB=/tmp/nr_test_iso.db).
"""
import os
import tempfile

# ÖNEMLİ: config lru_cache'lenir → app import'undan ÖNCE env ayarla.
_db = os.path.join(tempfile.gettempdir(), "nr_test_iso.db")
for suffix in ("", "-wal", "-shm"):
    try:
        os.remove(_db + suffix)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db,
    APP_PASSWORD="testpass",
    APP_SECRET="test-secret-0123456789",
    ADMIN_USERNAME="theadmin",           # A/B normal kalsın; admin ayrı
    NEWSRADAR_SCHEDULER="off",
    NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_MAX_ENTITIES_REGISTERED="15",  # kayıtlı kullanıcı kotası (test 15 bekliyor)
    NEWSRADAR_MAX_REFRESH_REGISTERED="5",    # yenileme kotası (test 5 bekliyor)
    NEWSRADAR_DAILY_BUDGET_USD="0",        # test'te bütçe kapalı
    NEWSRADAR_LLM_PROVIDER="anthropic",  # refresh çağırmıyoruz; anahtar gerekmez
)

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402
from app.db.database import session_scope  # noqa: E402
from app.db.models import Entity, EntityAnalysis  # noqa: E402

PASS, FAIL = 0, 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {msg}")
    else:
        FAIL += 1
        print(f"  ✗ FAIL: {msg}")


def seed_pool():
    """Havuza analizli entity'ler ekle (hiçbir watchlist'e bağlı değil)."""
    with session_scope() as db:
        for name, typ, q in [("Tesla", "ticker", "TSLA"),
                             ("Apple", "ticker", "AAPL"),
                             ("NVIDIA", "ticker", "NVDA")]:
            e = Entity(name=name, type=typ, query=q, active=False)
            db.add(e)
            db.flush()
            db.add(EntityAnalysis(
                entity_id=e.id, risk_score=50, sentiment_trend="stable",
                top_drivers=["x"], summary=f"{name} özet", stance="neutral",
                conviction="medium", what_to_verify=["y"], invalidation="z",
                articles_considered=5, headline_verdict=f"{name} hüküm",
            ))


def auth_headers(client, username, password="pw12345678"):
    """Genel giriş + kişisel kayıt → kişisel token header'ı döndür."""
    gtok = client.post("/auth/login", json={"password": "testpass"}).json()["token"]
    r = client.post("/users/register", json={"username": username, "password": password},
                    headers={"Authorization": f"Bearer {gtok}"})
    assert r.status_code == 201, f"register {username}: {r.status_code} {r.text}"
    utok = r.json()["token"]
    return {"Authorization": f"Bearer {utok}"}


def entity_id_by_name(name):
    with session_scope() as db:
        e = db.query(Entity).filter(Entity.name == name).first()
        return e.id if e else None


def main():
    with TestClient(app) as client:
        seed_pool()
        tesla = entity_id_by_name("Tesla")
        apple = entity_id_by_name("Apple")
        nvidia = entity_id_by_name("NVIDIA")

        A = auth_headers(client, "usera")
        B = auth_headers(client, "userb")

        print("\n== TEST 1: İzolasyon ==")
        # A: Tesla + Apple ekler
        client.post("/entities", json={"name": "Tesla", "type": "ticker", "query": "TSLA"}, headers=A)
        client.post("/entities", json={"name": "Apple", "type": "ticker", "query": "AAPL"}, headers=A)
        # B: NVIDIA ekler
        client.post("/entities", json={"name": "NVIDIA", "type": "ticker", "query": "NVDA"}, headers=B)

        a_list = {c["name"] for c in client.get("/entities", headers=A).json()}
        b_list = {c["name"] for c in client.get("/entities", headers=B).json()}
        check(a_list == {"Tesla", "Apple"}, f"A yalnızca Tesla+Apple görür (görülen: {a_list})")
        check(b_list == {"NVIDIA"}, f"B yalnızca NVIDIA görür (görülen: {b_list})")
        # A, NVIDIA detayına erişemez (404)
        r = client.get(f"/entities/{nvidia}/dashboard", headers=A)
        check(r.status_code == 404, f"A → NVIDIA detay 404 (alınan: {r.status_code})")
        # B, Tesla detayına erişemez
        r = client.get(f"/entities/{tesla}/dashboard", headers=B)
        check(r.status_code == 404, f"B → Tesla detay 404 (alınan: {r.status_code})")
        # A kendi Tesla'sına erişebilir
        r = client.get(f"/entities/{tesla}/dashboard", headers=A)
        check(r.status_code == 200, f"A → kendi Tesla detayı 200 (alınan: {r.status_code})")

        print("\n== TEST 2: Ortak analiz (bir kez) ==")
        n_before = None
        with session_scope() as db:
            n_before = db.query(Entity).filter(Entity.name == "Tesla").count()
        # B de Tesla ekler
        client.post("/entities", json={"name": "Tesla", "type": "ticker", "query": "TSLA"}, headers=B)
        with session_scope() as db:
            n_after = db.query(Entity).filter(Entity.name == "Tesla").count()
        check(n_before == 1 and n_after == 1, f"Tesla havuzda TEK entity (önce {n_before}, sonra {n_after})")
        # ikisi de aynı analizi görür
        a_tesla = next(c for c in client.get("/entities", headers=A).json() if c["name"] == "Tesla")
        b_tesla = next(c for c in client.get("/entities", headers=B).json() if c["name"] == "Tesla")
        check(a_tesla["analysis"]["headline_verdict"] == b_tesla["analysis"]["headline_verdict"] == "Tesla hüküm",
              "A ve B aynı Tesla analizini görür")

        print("\n== TEST 3: Havuz mantığı (çıkarma/pasifleşme) ==")
        # A Tesla'yı çıkarır; B'de hâlâ var → aktif kalır
        client.delete(f"/entities/{tesla}", headers=A)
        with session_scope() as db:
            e = db.get(Entity, tesla)
            check(e.active is True, "A çıkardı ama B'de var → Tesla AKTİF")
        a_list = {c["name"] for c in client.get("/entities", headers=A).json()}
        check("Tesla" not in a_list, "A'nın listesinde Tesla YOK artık")
        b_list = {c["name"] for c in client.get("/entities", headers=B).json()}
        check("Tesla" in b_list, "B hâlâ Tesla görür")
        # B de çıkarır → kimsede yok → pasif, ama SİLİNMEZ
        client.delete(f"/entities/{tesla}", headers=B)
        with session_scope() as db:
            e = db.get(Entity, tesla)
            check(e is not None, "Tesla SİLİNMEDİ (havuzda kalır)")
            check(e.active is False, "Kimsede yok → Tesla PASİF")

        print("\n== TEST 4: Entity kotası (15) ==")
        # usera şu an: Apple (Tesla çıktı) = 1. 14 tane daha ekle → 15, 16. reddedilsin.
        for i in range(14):
            r = client.post("/entities", json={"name": f"Co{i}", "type": "keyword", "query": f"Co{i}"}, headers=A)
            assert r.status_code == 201, f"Co{i}: {r.status_code} {r.text}"
        cnt = len(client.get("/entities", headers=A).json())
        check(cnt == 15, f"A tam 15 şirket (görülen: {cnt})")
        r = client.post("/entities", json={"name": "Over", "type": "keyword", "query": "Over"}, headers=A)
        check(r.status_code == 403, f"16. şirket reddedildi 403 (alınan: {r.status_code})")
        check("15" in r.json().get("detail", ""), f"Mesajda limit belirtiliyor: {r.json().get('detail')}")

        print("\n== TEST 5: Yenileme kotası (5/gün) ==")
        from datetime import datetime, timezone
        from app.db.models import UsageEvent, User
        from app.api.routes_refresh import _refresh_quota
        # Normal kullanıcı userd: 1 şirket + 5 yenileme olayı → 6. istek 429
        D = auth_headers(client, "userd")
        client.post("/entities", json={"name": "Apple", "type": "ticker", "query": "AAPL"}, headers=D)
        with session_scope() as db:
            uid = db.query(User).filter(User.username == "userd").first().id
            for _ in range(5):
                db.add(UsageEvent(user_id=uid, event_type="refresh",
                                  created_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        r = client.post("/refresh", headers=D)
        check(r.status_code == 429, f"6. yenileme reddedildi 429 (alınan: {r.status_code})")
        check("5/5" in r.json().get("detail", ""), f"Mesaj limiti belirtir: {r.json().get('detail')}")
        # Admin (theadmin): kota YOK — 10 olay olsa bile _refresh_quota ok döner (unit).
        adm = auth_headers(client, "theadmin")
        with session_scope() as db:
            adm_u = db.query(User).filter(User.username == "theadmin").first()
            check(adm_u.is_admin is True, "theadmin gerçekten admin")
            for _ in range(10):
                db.add(UsageEvent(user_id=adm_u.id, event_type="refresh",
                                  created_at=datetime.now(timezone.utc).replace(tzinfo=None)))
            db.flush()
            ok, _lim, _used = _refresh_quota(db, adm_u)
            check(ok is True, "Admin 10 olaydan sonra bile kota muaf (_refresh_quota ok=True)")

        print("\n== TEST 6: Yeni kullanıcı boş başlar ==")
        C = auth_headers(client, "userc")
        c_list = client.get("/entities", headers=C).json()
        check(c_list == [], f"Yeni kullanıcı BOŞ liste (görülen: {len(c_list)} kart)")

        print("\n== TEST 7: Tutorial flag (kalıcı) ==")
        me = client.get("/users/me", headers=C).json()
        check(me["tutorial_done"] is False, "Yeni kullanıcı tutorial_done=False")
        r = client.post("/users/me/tutorial-done", headers=C)
        check(r.status_code == 200 and r.json()["tutorial_done"] is True, "tutorial-done → True")
        me2 = client.get("/users/me", headers=C).json()
        check(me2["tutorial_done"] is True, "Tekrar girişte tutorial_done kalıcı True")

        print("\n== TEST 8: Admin görünürlüğü ==")
        with session_scope() as db:
            a_uid = db.query(User).filter(User.username == "usera").first().id
        # admin: kullanıcı detayında watchlist görünür
        det = client.get(f"/admin/users/{a_uid}", headers=adm).json()
        check(det["watchlist_size"] == 15, f"Admin, A'nın 15 şirketini görür (görülen: {det['watchlist_size']})")
        check(any(e["name"] == "Apple" for e in det["watchlist"]), "A'nın watchlist'inde Apple var")
        # stats: en çok takip edilen + toplam
        stats = client.get("/admin/stats", headers=adm).json()
        check(stats["total_entities"] >= 1, f"total_entities > 0 (görülen: {stats['total_entities']})")
        check(len(stats["most_followed"]) >= 1, f"most_followed dolu (görülen: {len(stats['most_followed'])})")
        # normal kullanıcı admin ucuna erişemez
        r = client.get("/admin/stats", headers=C)
        check(r.status_code == 403, f"Normal kullanıcı /admin/stats 403 (alınan: {r.status_code})")

        print("\n== TEST 9: Az şirket → hepsi büyük kart (tier=1) ==")
        F = auth_headers(client, "userf")
        for nm, ty, q in [("Tesla", "ticker", "TSLA"), ("Apple", "ticker", "AAPL"),
                          ("NVIDIA", "ticker", "NVDA")]:
            client.post("/entities", json={"name": nm, "type": ty, "query": q}, headers=F)
        lst = client.get("/entities", headers=F).json()
        check(len(lst) == 3 and all(c["tier"] == 1 for c in lst),
              f"3 şirket → hepsi tier=1 (tier'ler: {[c['tier'] for c in lst]})")
        client.post("/entities", json={"name": "Kf1", "type": "keyword", "query": "Kf1"}, headers=F)
        lst = client.get("/entities", headers=F).json()
        check(len(lst) == 4 and all(c["tier"] == 1 for c in lst),
              f"4 şirket → hâlâ hepsi tier=1 (eşik sınırı)")
        client.post("/entities", json={"name": "Kf2", "type": "keyword", "query": "Kf2"}, headers=F)
        lst = client.get("/entities", headers=F).json()
        n_big = sum(1 for c in lst if c["tier"] == 1)
        check(len(lst) == 5 and n_big < 5 and n_big <= 3,
              f"5 şirket → kademe devrede (büyük kart: {n_big}/5, ≤3 beklenir)")

        print("\n== TEST 10: Yenileme ilerlemesi KİŞİSEL ==")
        from app import refresh as R
        with session_scope() as db:
            fid = db.query(User).filter(User.username == "userf").first().id
            uid_a = db.query(User).filter(User.username == "usera").first().id
        # userf'in taraması çalışıyormuş gibi durum kur (3 entity)
        R._set_running(True, total=3, user_id=fid)
        R._set_progress(1, 3)
        st_f = client.get("/status", headers=F).json()
        check(st_f["is_running"] is True and st_f["progress_total"] == 3,
              f"userf kendi taramasını görür (1/3): running={st_f['is_running']} total={st_f['progress_total']}")
        st_a = client.get("/status", headers=A).json()
        check(st_a["is_running"] is False and st_a["progress_total"] == 0,
              f"A, userf'in taramasını GÖRMEZ (running={st_a['is_running']} total={st_a['progress_total']})")
        # tamamlanınca son özet yalnızca sahibine
        summ = R.RefreshSummary(analyzed=2, warnings=["[Kf1] test uyarı"])
        R._record_completion(summ)
        st_f2 = client.get("/status", headers=F).json()
        st_a2 = client.get("/status", headers=A).json()
        check(st_f2["last_summary"] is not None, "userf son özeti görür")
        check(st_a2["last_summary"] is None, "A, userf'in son özetini/uyarısını GÖRMEZ (sızıntı yok)")

        print("\n== TEST 11: Boş liste → yenileme başlamaz ==")
        G = auth_headers(client, "userg")
        r = client.post("/refresh", headers=G)
        check(r.status_code == 200 and r.json()["started"] is False,
              f"Boş listede yenileme başlamaz (started={r.json().get('started')})")
        check("boş" in r.json().get("message", "").lower(), f"Mesaj: {r.json().get('message')}")

        print("\n== TEST 12: last_active_at her authed istekte tazelenir ==")
        from datetime import datetime, timezone
        H = auth_headers(client, "userh")
        with session_scope() as db:
            hid = db.query(User).filter(User.username == "userh").first().id
            before = db.get(User, hid).last_active_at
        check(before is None, "Kayıt sonrası last_active_at boş (henüz veri isteği yok)")
        # Herhangi bir authed veri isteği (get_current_user'dan geçer) → tazelensin.
        client.get("/entities", headers=H)
        with session_scope() as db:
            after = db.get(User, hid).last_active_at
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        check(after is not None, "GET /entities sonrası last_active_at DOLU (siteyi gezmek sayılıyor)")
        check(after is not None and (now - after).total_seconds() < 10,
              f"last_active_at gerçek zamanlı (fark: {None if after is None else round((now-after).total_seconds(),1)}s)")
        # Admin panelinde de görünür (Test 5'teki admin header'ını yeniden kullan)
        rows = client.get("/admin/users", headers=adm).json()
        hrow = next((r for r in rows if r["username"] == "userh"), None)
        check(hrow and hrow["last_active_at"] is not None, "Admin, userh'in son aktifliğini görür")

    print(f"\n{'='*50}\nSONUÇ: {PASS} geçti, {FAIL} başarısız")
    return FAIL == 0


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)
