"""Gizlilik metni kodla uyumlu mu — IP saklama temizliği + /privacy-info (izole temp DB).

Doğrular:
  (A) prune_ip_records: N günden eski + kilidi bitmiş login_rate satırları silinir; taze
      satır ve hâlâ kilitli satır KALIR
  (B) başarısız giriş/kayıt olaylarında eski detail.ip silinir, olayın kendisi ve diğer
      alanlar kalır; taze olaydaki ip kalır; başka olay tipleri etkilenmez
  (C) /privacy-info girişsiz erişilebilir; değerler config'ten gelir (LLM sağlayıcı adı,
      barındırma, iletişim adresi, IP saklama süresi)
  (D) provider env'i değişince sağlayıcı adı da değişir (tek kaynak)
Çalıştır: python test_privacy.py
"""
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_privacy.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y" * 20, NEWSRADAR_SCHEDULER="off",
    NEWSRADAR_SEED_ON_START="off", NEWSRADAR_LLM_PROVIDER="anthropic",
    NEWSRADAR_IP_RETENTION_DAYS="7", NEWSRADAR_CONTACT_EMAIL="privacy@example.com",
    NEWSRADAR_HOSTING_PROVIDER="Render",
)

from fastapi.testclient import TestClient  # noqa: E402

from app.analysis.llm import provider_display_name  # noqa: E402
from app.api.main import app  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import LoginRate, UsageEvent, User  # noqa: E402
from app.security import prune_ip_records  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


def now():
    return datetime.now(timezone.utc)


init_db()
old, fresh = now() - timedelta(days=8), now() - timedelta(days=1)
with session_scope() as s:
    s.add(LoginRate(ip="1.1.1.1", attempts="[]", locked_until=0.0, updated_at=old))       # silinmeli
    s.add(LoginRate(ip="2.2.2.2", attempts="[]", locked_until=0.0, updated_at=fresh))     # kalmalı
    s.add(LoginRate(ip="3.3.3.3", attempts="[]", locked_until=time.time() + 600, updated_at=old))  # kilitli → kalmalı
    s.add(LoginRate(ip="user:alice", attempts="[]", locked_until=0.0, updated_at=old))    # hesap anahtarı → silinmeli
    u = User(username="admin", password_hash="x", is_admin=True)
    s.add(u); s.flush()
    s.add(UsageEvent(user_id=u.id, event_type="login_failed", created_at=old,
                     detail={"ip": "1.1.1.1", "username": "bob"}))
    s.add(UsageEvent(user_id=u.id, event_type="register_failed", created_at=old,
                     detail={"ip": "4.4.4.4", "reason": "taken", "username": "eve"}))
    s.add(UsageEvent(user_id=u.id, event_type="login_failed", created_at=fresh,
                     detail={"ip": "5.5.5.5", "username": "bob"}))
    s.add(UsageEvent(user_id=u.id, event_type="view_entity", created_at=old,
                     detail={"ip": "9.9.9.9", "entity_id": 1}))  # başka tip: dokunulmamalı

print("== A/B: prune_ip_records ==")
res = prune_ip_records()
check(res == {"login_rate": 2, "events": 2}, f"silinen sayılar doğru ({res})")
with session_scope() as s:
    ips = sorted(r.ip for r in s.query(LoginRate))
    check(ips == ["2.2.2.2", "3.3.3.3"], f"taze ve kilitli satır kaldı, eskiler silindi ({ips})")
    evs = {(e.event_type, e.created_at < fresh - timedelta(hours=1)): e.detail for e in s.query(UsageEvent)}
    check(evs[("login_failed", True)] == {"username": "bob"}, "eski login_failed: ip silindi, olay + username kaldı")
    check(evs[("register_failed", True)] == {"reason": "taken", "username": "eve"}, "eski register_failed: ip silindi")
    check(evs[("login_failed", False)].get("ip") == "5.5.5.5", "taze olaydaki ip kaldı")
    check(evs[("view_entity", True)].get("ip") == "9.9.9.9", "başka olay tipine dokunulmadı")
check(prune_ip_records() == {"login_rate": 0, "events": 0}, "idempotent (ikinci çalıştırma 0)")

print("== C: /privacy-info ==")
with TestClient(app) as client:
    r = client.get("/privacy-info")
    check(r.status_code == 200, f"girişsiz erişilebilir ({r.status_code})")
    d = r.json()
    check(d == {"llm_provider": "Anthropic (Claude API)", "hosting_provider": "Render",
                "contact_email": "privacy@example.com", "ip_retention_days": 7}, f"değerler config'ten: {d}")

print("== D: sağlayıcı adı tek kaynaktan ==")
st = get_settings()
st.llm_provider, st.llm_base_url = "openrouter", "https://openrouter.ai/api/v1"
check(provider_display_name() == "OpenRouter", f"openrouter → {provider_display_name()}")
st.llm_base_url = "https://integrate.api.nvidia.com/v1"
check(provider_display_name() == "NVIDIA", f"nvidia base_url → {provider_display_name()}")
st.llm_base_url = "https://llm.example.org/v1"
check(provider_display_name() == "llm.example.org", "bilinmeyen endpoint → host adı")
st.llm_provider = "anthropic"
st.contact_email = ""
with TestClient(app) as client:
    check(client.get("/privacy-info").json()["contact_email"] is None, "iletişim adresi boşsa None (metin genel ifadeye düşer)")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
