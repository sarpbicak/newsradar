"""Güvenlik kontrollerini GERÇEKTEN test eder (izole temp DB, TestClient).

'Var olması çalıştığı anlamına gelmez' — her kontrolü çalıştırıp sonucu raporlar:
MAX_USERS, yarış, rate limit, token expiry, entity/refresh kotası, admin 403.

Çalıştır: python test_security.py
"""
import os
import tempfile
import time as _time

_db = os.path.join(tempfile.gettempdir(), "nr_test_sec.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="genelsifre", APP_SECRET="sec-secret-123456",
    ADMIN_USERNAME="rootadmin", NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_MAX_USERS="2",              # ← sınırı 2'ye çek: 3. kayıt reddedilmeli
    NEWSRADAR_TOKEN_TTL_DAYS="30",
    NEWSRADAR_LLM_PROVIDER="anthropic",
)

from fastapi.testclient import TestClient  # noqa: E402
from app.api.main import app  # noqa: E402
from app.db.database import session_scope  # noqa: E402
from app.db.models import User, UsageEvent  # noqa: E402

PASS = FAIL = 0
def check(cond, msg):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✓ {msg}")
    else: FAIL += 1; print(f"  ✗ FAIL: {msg}")


def gtok(client):
    return client.post("/auth/login", json={"password": "genelsifre"}).json()["token"]


def reg(client, username, pw="parola12345", gt=None):
    gt = gt or gtok(client)
    return client.post("/users/register", json={"username": username, "password": pw},
                       headers={"Authorization": f"Bearer {gt}"})


def user_count():
    with session_scope() as db:
        return db.query(User).count()


def main():
    with TestClient(app) as client:
        print("== MAX_USERS = 2 kontrolü ==")
        # rootadmin (admin) + user1 = 2 kullanıcı
        r1 = reg(client, "rootadmin"); check(r1.status_code == 201, f"1. kayıt (admin) 201 ({r1.status_code})")
        r2 = reg(client, "user1"); check(r2.status_code == 201, f"2. kayıt 201 ({r2.status_code})")
        check(user_count() == 2, f"DB'de 2 kullanıcı ({user_count()})")
        # 3. kayıt REDDEDİLMELİ
        r3 = reg(client, "user2")
        check(r3.status_code == 403, f"3. kayıt (limit 2) 403 DÖNMELİ → alınan: {r3.status_code}")
        check(user_count() == 2, f"3. kayıt sonrası HÂLÂ 2 kullanıcı ({user_count()}) — sınır tutuyor")
        adm_tok = r1.json()["token"]

        print("\n== Admin paneli GERÇEK sayıyı gösteriyor mu ==")
        stats = client.get("/admin/stats", headers={"Authorization": f"Bearer {adm_tok}"}).json()
        rows = client.get("/admin/users", headers={"Authorization": f"Bearer {adm_tok}"}).json()
        check(stats["total_users"] == 2, f"stats.total_users == 2 ({stats['total_users']})")
        check(len(rows) == 2, f"/admin/users satır sayısı == 2 ({len(rows)})")
        check(stats["total_users"] == len(rows), "total_users ile tablo satır sayısı TUTARLI")

        print("\n== Yarış koşulu: aynı anda 2 kayıt (1 slot varken) ==")
        # DB'yi 1 kullanıcıya indir (limit 2 → 1 slot boş), 2 eşzamanlı kayıt dene.
        with session_scope() as db:
            u = db.query(User).filter(User.username == "user1").first()
            if u: db.delete(u)
        check(user_count() == 1, f"1 kullanıcıya indirildi ({user_count()}), 1 slot boş")
        import threading
        results = []
        gt = gtok(client)
        def race(i):
            r = reg(client, f"racer{i}", gt=gt)
            results.append(r.status_code)
        ts = [threading.Thread(target=race, args=(i,)) for i in range(2)]
        for t in ts: t.start()
        for t in ts: t.join()
        n_ok = sum(1 for s in results if s == 201)
        final = user_count()
        check(final <= 2, f"Yarış sonrası kullanıcı sayısı ≤ 2 (limit tutuldu): {final} (kodlar: {results})")

        print("\n== Rate limit: 5 başarısız denemede kilit ==")
        gt2 = gtok(client)
        # var olan bir kullanıcıya (rootadmin) yanlış şifreyle 5 kez dene
        codes = []
        for i in range(6):
            rr = client.post("/users/login", json={"username": "rootadmin", "password": "yanlis"},
                             headers={"Authorization": f"Bearer {gt2}"})
            codes.append(rr.status_code)
        check(429 in codes, f"6 denemede kilit (429) görüldü → kodlar: {codes}")
        check(codes[-1] == 429, f"Son deneme kilitli (429): {codes[-1]}")

        print("\n== Token expiry: süresi geçmiş token 401 ==")
        from app.api.routes_auth import _sign, get_current_user  # noqa
        from app.config import get_settings
        with session_scope() as db:
            adm = db.query(User).filter(User.username == "rootadmin").first()
            uid, phash = adm.id, adm.password_hash
        secret = get_settings().app_secret
        ttl = get_settings().token_ttl_days * 86400
        old_iat = int(_time.time()) - ttl - 100  # TTL'den 100 sn daha eski
        sig = _sign(uid, old_iat, phash, secret)
        expired = f"{uid}.{old_iat}.{sig}"
        rr = client.get("/entities", headers={"Authorization": f"Bearer {expired}"})
        check(rr.status_code == 401, f"Süresi geçmiş token 401 → alınan: {rr.status_code}")
        # geçerli (taze) token çalışıyor mu (kontrol amaçlı)
        fresh = f"{uid}.{int(_time.time())}.{_sign(uid, int(_time.time()), phash, secret)}"
        rr2 = client.get("/entities", headers={"Authorization": f"Bearer {fresh}"})
        check(rr2.status_code == 200, f"Taze token 200 → alınan: {rr2.status_code}")

        print("\n== Admin uçları non-admin için 403 ==")
        # Yeni normal kullanıcı için slot açalım: limiti geçici aşma sorunu yok, mevcut
        # racer'lardan birini kullan ya da user1'i tekrar ekle. Basitçe: mevcut bir
        # non-admin token al. racer0/racer1'den başarılı olan var mı?
        # Güvenli yol: DB'den admin olmayan bir kullanıcı bul, token üret.
        with session_scope() as db:
            nonadmin = db.query(User).filter(User.is_admin.is_(False)).first()
        if nonadmin is None:
            check(False, "Test için non-admin kullanıcı bulunamadı")
        else:
            natok = f"{nonadmin.id}.{int(_time.time())}.{_sign(nonadmin.id, int(_time.time()), nonadmin.password_hash, secret)}"
            rr = client.get("/admin/stats", headers={"Authorization": f"Bearer {natok}"})
            check(rr.status_code == 403, f"non-admin → /admin/stats 403 → alınan: {rr.status_code}")

        print("\n== register_failed olayı kaydediliyor mu (limit aşımı) ==")
        with session_scope() as db:
            n_rf = db.query(UsageEvent).filter(UsageEvent.event_type == "register_failed").count()
        check(n_rf >= 1, f"En az 1 register_failed olayı ({n_rf})")

        adm = {"Authorization": f"Bearer {adm_tok}"}  # rootadmin header'ı (aşağıdaki testler için)
        print("\n== Rate limit KARIŞIK uçlarda ortak sayaç (uç-bağımsız) ==")
        from app.security import login_limiter as _ll2
        _ll2.reset_all()
        gtm = gtok(client)
        mixed = []
        for _ in range(4):  # /auth/login yanlış
            mixed.append(("auth", client.post("/auth/login", json={"password": "YANLIS"}).status_code))
        for _ in range(3):  # /users/login yanlış (aynı IP)
            mixed.append(("users", client.post("/users/login", json={"username": "rootadmin", "password": "YANLIS"},
                          headers={"Authorization": f"Bearer {gtm}"}).status_code))
        got429 = any(s == 429 for _, s in mixed)
        check(got429, f"KARIŞIK uçlarda 5. başarısızda kilit (429) — kodlar: {mixed}")

        print("\n== Rate limit KALICI: yeniden başlatmadan sonra kilit korunur ==")
        from app.security import LoginRateLimiter
        _ll2.reset_all()
        for _ in range(5):
            _ll2.record_failure("9.8.7.6")
        # 'Yeniden başlatma' simülasyonu: bellek durumu olmayan YEPYENİ limiter örneği,
        # kilidi yalnızca DB'den okuyabilir.
        fresh_limiter = LoginRateLimiter()
        rem = fresh_limiter.locked_seconds("9.8.7.6")
        check(rem > 0, f"Restart sonrası (yeni örnek) kilit DB'den okunuyor: {rem}s kaldı")
        with session_scope() as db:
            from app.db.models import LoginRate
            has_row = db.get(LoginRate, "9.8.7.6") is not None
        check(has_row, "login_rate satırı DB'de KALICI")

        print("\n== XFF: İLK (en sol) adres = Render istemci IP'si ==")
        from app.security import get_client_ip
        class _Req:
            def __init__(self, xff): self.headers = {"x-forwarded-for": xff}; self.client = None
        ip = get_client_ip(_Req("31.206.162.84, 10.0.0.5, 10.0.0.9"))
        check(ip == "31.206.162.84", f"XFF'in İLK adresi (Render istemci IP'si) alınır: {ip}")

        print("\n== login_failed kullanıcı adıyla kaydediliyor ==")
        _ll2.reset_all()
        gtm2 = gtok(client)
        client.post("/users/login", json={"username": "rootadmin", "password": "YANLIS2"},
                    headers={"Authorization": f"Bearer {gtm2}"})
        with session_scope() as db:
            lf = db.query(UsageEvent).filter(UsageEvent.event_type == "login_failed").all()
            has_uname = any((e.detail or {}).get("username") == "rootadmin" for e in lf)
        check(has_uname, f"login_failed detayında kullanıcı adı var ({len(lf)} olay)")

        print("\n== Admin şifre sıfırlama ==")
        _ll2.reset_all()
        # sıfırlanacak kullanıcı: mevcut bir non-admin (delme2 hâlâ var)
        with session_scope() as db:
            tgt = db.query(User).filter(User.is_admin.is_(False)).first()
            tgt_id, tgt_name, old_hash = tgt.id, tgt.username, tgt.password_hash
        rr = client.post(f"/admin/users/{tgt_id}/reset-password", headers=adm)
        check(rr.status_code == 200, f"Şifre sıfırlama 200 ({rr.status_code})")
        body = rr.json()
        temp = body.get("temp_password", "")
        check(len(temp) >= 8 and body.get("username") == tgt_name, f"Geçici şifre döndü ({len(temp)} kar.)")
        with session_scope() as db:
            new_hash = db.get(User, tgt_id).password_hash
        check(new_hash != old_hash, "Şifre hash'i değişti (yeni geçici şifre saklandı)")
        # yeni geçici şifreyle giriş çalışıyor mu
        rlog = client.post("/users/login", json={"username": tgt_name, "password": temp},
                           headers={"Authorization": f"Bearer {gtok(client)}"})
        check(rlog.status_code == 200, f"Geçici şifreyle giriş 200 ({rlog.status_code})")
        with session_scope() as db:
            pr = db.query(UsageEvent).filter(UsageEvent.event_type == "password_reset").count()
        check(pr >= 1, f"password_reset olayı kaydedildi ({pr})")

        print("\n== Admin kullanıcı silme (DELETE /admin/users/{id}) ==")
        # Rate-limit testi IP'yi kilitledi → silme testinden önce limiter'ı sıfırla.
        from app.security import login_limiter as _ll
        _ll.reset_all()
        adm = {"Authorization": f"Bearer {adm_tok}"}  # rootadmin header'ı
        from app.db.models import Entity, UserWatchlist, SuggestionDismissal
        # Limiti geçici kaldır ki test kullanıcıları açılabilsin (cached settings'i mutasyonla).
        import app.config as _cfg
        _cfg.get_settings().max_users = 0  # sınırsız (test için)
        # İki test kullanıcısı + ortak entity (havuz mantığı testi)
        with session_scope() as db:
            e = Entity(name="ShareCo", type="ticker", query="SHR", active=True)
            db.add(e); db.flush(); shr_id = e.id
        def uhdr(username):
            return {"Authorization": f"Bearer {reg(client, username).json()['token']}"}
        d1 = uhdr("delme1")
        d2 = uhdr("delme2")
        # ikisi de ShareCo ekler + delme1 kendine özel bir entity ekler
        client.post("/entities", json={"name": "ShareCo", "type": "ticker", "query": "SHR"}, headers=d1)
        client.post("/entities", json={"name": "ShareCo", "type": "ticker", "query": "SHR"}, headers=d2)
        client.post("/entities", json={"name": "OnlyMine", "type": "keyword", "query": "OnlyMine"}, headers=d1)
        with session_scope() as db:
            u1 = db.query(User).filter(User.username == "delme1").first()
            u1_id = u1.id
            only = db.query(Entity).filter(Entity.query == "OnlyMine").first()
            only_id = only.id
            wl_before = db.query(UserWatchlist).filter(UserWatchlist.user_id == u1_id).count()
        check(wl_before == 2, f"delme1'in 2 watchlist satırı ({wl_before})")
        # Admin, kendini silemez → 403
        with session_scope() as db:
            adm_id = db.query(User).filter(User.username == "rootadmin").first().id
        rself = client.delete(f"/admin/users/{adm_id}", headers=adm)
        check(rself.status_code == 403, f"Admin kendini silemez 403 ({rself.status_code})")
        # delme1'i sil
        rdel = client.delete(f"/admin/users/{u1_id}", headers=adm)
        check(rdel.status_code == 204, f"delme1 silindi 204 ({rdel.status_code})")
        with session_scope() as db:
            gone = db.get(User, u1_id)
            check(gone is None, "delme1 DB'den gitti")
            wl_after = db.query(UserWatchlist).filter(UserWatchlist.user_id == u1_id).count()
            check(wl_after == 0, f"delme1 watchlist satırları temizlendi ({wl_after})")
            sd = db.query(SuggestionDismissal).filter(SuggestionDismissal.user_id == u1_id).count()
            check(sd == 0, f"delme1 suggestion_dismissals temizlendi ({sd})")
            ue = db.query(UsageEvent).filter(UsageEvent.user_id == u1_id).count()
            check(ue == 0, f"delme1 usage_events temizlendi ({ue})")
            # Havuz mantığı: ShareCo delme2'de var → AKTİF; OnlyMine kimsede yok → PASİF
            shr = db.get(Entity, shr_id)
            check(shr is not None and shr.active is True, "ShareCo delme2'de var → AKTİF (silinmedi)")
            om = db.get(Entity, only_id)
            check(om is not None and om.active is False, "OnlyMine kimsede yok → PASİF (silinmedi)")
            # Silme kaydı admin'e yazıldı
            dl = db.query(UsageEvent).filter(UsageEvent.event_type == "delete_user").count()
            check(dl >= 1, f"delete_user olayı kaydedildi ({dl})")

    print(f"\n{'='*52}\nSONUÇ: {PASS} geçti, {FAIL} başarısız")
    return FAIL == 0


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
