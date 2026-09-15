"""Bölüm 2 — kademeli kotalar + sistem bütçesi + maliyet takibi (izole temp DB).

Çalıştır: python test_quotas.py
"""
import os
import tempfile
import time as _time

_db = os.path.join(tempfile.gettempdir(), "nr_test_quota.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="gp", APP_SECRET="qsecret1234567890",
    ADMIN_USERNAME="root", NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_MAX_ENTITIES_ANON="3", NEWSRADAR_MAX_ENTITIES_REGISTERED="10",
    NEWSRADAR_MAX_REFRESH_ANON="1", NEWSRADAR_MAX_REFRESH_REGISTERED="3",
    NEWSRADAR_DAILY_TOKEN_BUDGET="0", NEWSRADAR_DAILY_ENTITY_ADD_CAP="0",
    NEWSRADAR_LLM_PROVIDER="anthropic",
)

from fastapi.testclient import TestClient  # noqa: E402
from app.api.main import app  # noqa: E402
from app.api.routes_auth import _sign, hash_password  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.database import session_scope  # noqa: E402
from app.db.models import User, LlmUsage  # noqa: E402
from app import budget  # noqa: E402

PASS = FAIL = 0
def check(cond, msg):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✓ {msg}")
    else: FAIL += 1; print(f"  ✗ FAIL: {msg}")


def mk_user(username, is_anonymous=False, is_admin=False):
    with session_scope() as db:
        u = User(username=username, password_hash=hash_password("pw12345678"),
                 is_anonymous=is_anonymous, is_admin=is_admin)
        db.add(u); db.flush()
        return u.id, u.password_hash


def hdr(uid, phash):
    secret = get_settings().app_secret
    iat = int(_time.time())
    return {"Authorization": f"Bearer {uid}.{iat}.{_sign(uid, iat, phash, secret)}"}


def add_entity(client, h, name, q):
    return client.post("/entities", json={"name": name, "type": "keyword", "query": q}, headers=h)


def main():
    with TestClient(app) as client:
        print("== Kademeli entity kotası ==")
        # Anonim: 3 max
        aid, ah = mk_user("anon:dev1", is_anonymous=True)
        A = hdr(aid, ah)
        for i in range(3):
            check(add_entity(client, A, f"An{i}", f"an{i}").status_code == 201, f"anon {i+1}. entity 201")
        r = add_entity(client, A, "An3", "an3")
        check(r.status_code == 403 and "3" in r.json().get("detail", ""),
              f"anon 4. entity 403 (limit 3): {r.status_code}")
        # Kayıtlı: 10 max (3'ten fazla ekleyebilmeli)
        rid, rh = mk_user("reguser", is_anonymous=False)
        R = hdr(rid, rh)
        for i in range(10):
            add_entity(client, R, f"Rg{i}", f"rg{i}")
        n_reg = len(client.get("/entities", headers=R).json())
        check(n_reg == 10, f"kayıtlı kullanıcı 10 entity ekleyebildi ({n_reg})")
        r = add_entity(client, R, "Rg10", "rg10")
        check(r.status_code == 403, f"kayıtlı 11. entity 403 (limit 10): {r.status_code}")
        # Admin: limitsiz (15 ekle)
        adid, adh = mk_user("root", is_admin=True)
        AD = hdr(adid, adh)
        for i in range(15):
            add_entity(client, AD, f"Ad{i}", f"ad{i}")
        check(len(client.get("/entities", headers=AD).json()) == 15, "admin 15+ entity ekleyebildi (limitsiz)")

        print("\n== Kademeli yenileme kotası (/status'ta limit) ==")
        st_a = client.get("/status", headers=A).json()
        st_r = client.get("/status", headers=R).json()
        st_ad = client.get("/status", headers=AD).json()
        check(st_a["refresh_limit"] == 1, f"anon refresh_limit=1 ({st_a['refresh_limit']})")
        check(st_r["refresh_limit"] == 3, f"kayıtlı refresh_limit=3 ({st_r['refresh_limit']})")
        check(st_ad["refresh_limit"] == 0, f"admin refresh_limit=0/sınırsız ({st_ad['refresh_limit']})")
        check(st_a["entity_limit"] == 3 and st_r["entity_limit"] == 10,
              f"entity_limit kademeli (anon={st_a['entity_limit']}, kayıtlı={st_r['entity_limit']})")

        print("\n== Sistem bütçesi: token kaydı + tavan ==")
        check(budget.daily_tokens_used() == 0, "başta bugün 0 token")
        budget.record_llm_usage(600, 400)  # 1000 token
        check(budget.daily_tokens_used() == 1000, f"1000 token kaydedildi ({budget.daily_tokens_used()})")
        get_settings().daily_token_budget = 1500  # tavanı test için ayarla
        check(budget.is_budget_exceeded() is False, "1000/1500 → aşılmadı")
        budget.record_llm_usage(300, 300)  # +600 → 1600
        check(budget.is_budget_exceeded() is True, f"1600/1500 → AŞILDI ({budget.daily_tokens_used()})")
        # /status bütçe durumunu yansıtıyor
        st = client.get("/status", headers=R).json()
        check(st["budget_exceeded"] is True and st["tokens_today"] == 1600,
              f"/status budget_exceeded=True, tokens_today={st['tokens_today']}")
        # Bütçe doluyken PIPELINE GUARD: analyze_all_async yeni LLM çağrısı YAPMAMALI.
        import asyncio
        from app.db.models import Entity, Article
        from app.analysis.pipeline import analyze_all_async
        with session_scope() as db:
            e = Entity(name="BudgetCo", type="ticker", query="BDG", active=True)
            db.add(e); db.flush()
            for i in range(5):
                db.add(Article(entity_id=e.id, url=f"http://b/{i}", url_hash=f"bh{i}",
                               title=f"alpha{i} beta{i} gamma{i}", source="s",
                               description="özet", provider="t", analyzed=False, prefiltered=False))
        class FakeClient:
            model = "fake"
            total_prompt_tokens = 0; total_completion_tokens = 0; call_count = 0
            def __init__(self): self.calls = 0
            def call_tool(self, **kw):
                self.calls += 1
                return {"analyses": []}
        get_settings().daily_token_budget = 1500  # 1600 kullanıldı → aşıldı
        fc = FakeClient()
        asyncio.run(analyze_all_async(fc, entity_ids={e.id}))
        check(fc.calls == 0, f"Bütçe doluyken LLM çağrısı YAPILMADI (çağrı: {fc.calls})")
        get_settings().daily_token_budget = 0  # geri kapat

        print("\n== Maliyet takibi (admin stats) ==")
        get_settings().daily_token_budget = 0
        stats = client.get("/admin/stats", headers=AD).json()
        check(stats["tokens_today"] == 1600, f"admin stats tokens_today=1600 ({stats['tokens_today']})")
        expected_cost = round(1600/1_000_000 * get_settings().token_unit_cost_usd, 2)
        check(abs(stats["cost_today_usd"] - expected_cost) < 1e-6,
              f"maliyet ~${stats['cost_today_usd']} (beklenen ${expected_cost})")

        print("\n== Günlük entity-ekleme sistem sınırı ==")
        # TAZE kayıtlı kullanıcı (per-user limitine takılmasın); bugün sistemde zaten çok
        # entity oluşturuldu → düşük tavan → YENİ entity oluşturma reddedilmeli.
        fid, fh = mk_user("freshuser", is_anonymous=False)
        F = hdr(fid, fh)
        get_settings().daily_entity_add_cap = 2
        r = add_entity(client, F, "CapTest", "captest_new")
        check(r.status_code == 429 and "kapasite" in r.json().get("detail", "").lower(),
              f"günlük entity ekleme tavanı 429: {r.status_code} {r.json().get('detail','')}")
        get_settings().daily_entity_add_cap = 0

    print(f"\n{'='*50}\nSONUÇ: {PASS} geçti, {FAIL} başarısız")
    return FAIL == 0


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
