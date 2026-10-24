"""Kota/sağlık uçtan uca: /admin/stats sağlık + haftalık maliyet, /status kota banner'ı.

TestClient + izole temp DB. Çalıştır: python test_quota_endpoints.py
"""
import os
import tempfile
import uuid

_db = os.path.join(tempfile.gettempdir(), "nr_test_qep.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="genelsifre", APP_SECRET="qep-secret-123456",
    ADMIN_USERNAME="rootadmin", NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_MAX_USERS="0", NEWSRADAR_TOKEN_TTL_DAYS="30",
    NEWSRADAR_LLM_PROVIDER="anthropic",
)

from fastapi.testclient import TestClient  # noqa: E402
from app.api.main import app  # noqa: E402

PASS = FAIL = 0
def check(cond, msg):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✓ {msg}")
    else: FAIL += 1; print(f"  ✗ FAIL: {msg}")


def main():
    with TestClient(app) as client:
        gt = client.post("/auth/login", json={"password": "genelsifre"}).json()["token"]
        # İlk kayıt = admin (rootadmin).
        r = client.post("/users/register", json={"username": "rootadmin", "password": "parola12345", "email": f"{uuid.uuid4().hex[:12]}@test.local"},
                        headers={"Authorization": f"Bearer {gt}"})
        adm = r.json()["token"]
        H = {"Authorization": f"Bearer {adm}"}

        print("== /admin/stats: sağlık + haftalık alanlar mevcut (veri yokken) ==")
        st = client.get("/admin/stats", headers=H).json()
        check("health" in st and st["health"] is not None, "stats.health mevcut")
        check(st["health"]["last_kind"] is None, "veri yok → last_kind None")
        check(st["health"]["quota_errors_24h"] == 0, "veri yok → quota_errors_24h 0")
        check("tokens_week" in st and "cost_week_usd" in st, "haftalık token + maliyet alanları var")

        print("\n== Sağlık olayları kaydedilince /admin/stats yansıtır ==")
        from app.health import record_llm_health
        record_llm_health("ok")
        record_llm_health("quota", "OpenRouter Key limit exceeded", 403)
        st2 = client.get("/admin/stats", headers=H).json()
        h = st2["health"]
        check(h["last_kind"] == "quota", f"son olay 'quota' ({h['last_kind']})")
        check(h["last_status_code"] == 403, f"son kod 403 ({h['last_status_code']})")
        check(h["quota_errors_24h"] == 1, f"24s kota hatası = 1 ({h['quota_errors_24h']})")
        check(h["last_ok_at"] is not None, "en son başarılı çağrı zamanı dolu (bir 'ok' vardı)")

        print("\n== /status: son yenileme kota hatası → banner alanı (last_summary.quota_error) ==")
        # Admin'in kendi listesine bir entity ekle ki refresh state kişiselleşsin.
        client.post("/entities", json={"name": "TestCo", "type": "keyword", "query": "TestCo"}, headers=H)
        # Refresh state'i elle 'tamamlandı + kota hatası' yap (gerçek run yerine izole).
        import app.refresh as refresh
        with refresh._state_lock:
            refresh._state.is_running = False
            refresh._state.last_user_id = _admin_id()
            refresh._state.last_summary = refresh.RefreshSummary(
                fetched_new=12, analyzed=0, quota_error=True,
                warnings=[{"code": "analysis_unavailable", "entity": None, "params": {}}],
            )
        stt = client.get("/status", headers=H).json()
        check(stt["last_summary"] is not None, "/status last_summary döndü")
        check(stt["last_summary"]["quota_error"] is True,
              f"last_summary.quota_error True → frontend banner gösterir ({stt['last_summary'].get('quota_error')})")

    print(f"\n{'='*54}\nSONUÇ: {PASS} geçti, {FAIL} başarısız")
    return FAIL == 0


def _admin_id():
    from app.db.database import session_scope
    from app.db.models import User
    with session_scope() as s:
        return s.query(User).filter(User.username == "rootadmin").first().id


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
