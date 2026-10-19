"""Zaman damgaları UTC-aware — 'X önce' hesabı saat dilimine göre kaymaz (izole temp DB).

Doğrular:
  (A) DB'den okunan tüm zaman damgaları UTC-aware (UTCDateTime); naive girdi UTC sayılır
  (B) API zaman damgalarını '+00:00' ekiyle serileştirir (tarayıcı yerel saat sanmaz)
  (C) 'son başarılı çağrı' az önce kaydedildiyse ~0 sn önce (eskiden Berlin'de 2 sa)
  (D) mevcut naive satırlar (eski veri) da UTC olarak okunur; karşılaştırmalar aware
  (E) admin model kırılımında legacy satırın adı
Çalıştır: python test_timezone.py
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_tz.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y" * 20,
                  NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
                  NEWSRADAR_LLM_PROVIDER="anthropic", TZ="Europe/Berlin")
import time  # noqa: E402
time.tzset()

from app import budget  # noqa: E402
from app.db.database import engine, init_db, session_scope  # noqa: E402
from app.db.models import LlmHealthEvent, LlmUsage  # noqa: E402
from app.health import health_snapshot, record_llm_health  # noqa: E402
from app.api.schemas import AdminHealthOut  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


init_db()
check(time.strftime("%Z") in ("CET", "CEST"), f"test süreci Berlin saatinde ({time.strftime('%Z')})")

print("== A/C: kayıt ve okuma ==")
record_llm_health("ok")
snap = health_snapshot()
last_ok = snap["last_ok_at"]
check(last_ok.tzinfo is not None and last_ok.utcoffset() == timedelta(0), f"last_ok_at UTC-aware ({last_ok!r})")
age = (datetime.now(timezone.utc) - last_ok).total_seconds()
check(0 <= age < 5, f"'son başarılı çağrı' ~{age:.1f} sn önce (2 saat DEĞİL)")

print("== B: serileştirme ==")
js = AdminHealthOut(**snap).model_dump_json()
check('"last_ok_at":"' in js and ('+00:00"' in js or 'Z"' in js), f"JSON'da UTC eki var: {js[js.find('last_ok_at'):][:50]}")

print("== D: eski naive satırlar ==")
with engine.begin() as c:
    c.exec_driver_sql("INSERT INTO llm_health_events (created_at, kind) VALUES (?, 'ok')",
                      ((datetime.now(timezone.utc) + timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S.%f"),))
snap2 = health_snapshot()
check(snap2["last_ok_at"].tzinfo is not None, "ham naive satır da UTC-aware okundu")
check(abs((datetime.now(timezone.utc) - snap2["last_ok_at"]).total_seconds()) < 5, "naive satır UTC kabul edildi (kayma yok)")
with session_scope() as s:
    s.add(LlmUsage(model=None, prompt_tokens=10, completion_tokens=5, total_tokens=15, calls=1,
                   created_at=datetime.now(timezone.utc) - timedelta(hours=1)))
check(budget.daily_tokens_used() >= 0, "günlük sayaç aware karşılaştırmayla çalışıyor")

print("== E: legacy etiketi (admin model kırılımı) ==")
rows = budget.usage_breakdown(datetime.now(timezone.utc) - timedelta(days=1))
check(any(r["model"] == "openrouter (legacy, cost not tracked)" for r in rows),
      f"legacy satır adı ({[r['model'] for r in rows]})")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
