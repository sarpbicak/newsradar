"""Mükerrer entity (aynı şirket iki kayıt) + salt okunur içerik raporu (izole temp DB).

Doğrular:
  (A) entity_names: SPCX "Space Exploration Technologies" ↔ keyword "SpaceX" aynı şirket;
      AMD ticker ↔ "AMD" keyword; Google ↔ Alphabet; farklı şirketler eşleşmez; ticker
      sembolü tek başına anahtar değil
  (B) POST /entities: listede aynı şirket başka kayıtla varsa 409 + code=duplicate_entity +
      duplicate_of (kısa adıyla); birebir aynısı → code=already_in_watchlist; başka
      kullanıcı serbestçe ekler; mevcut mükerrerler SİLİNMEZ
  (C) öneriler: listedeki şirketin başka adla önerisi gizlenir; eski arayüzden eklenirse 409
  (D) content-report: tr/en durumları (GÜNCEL/ESKİ/EKSİK), mükerrer grup, DB'ye YAZMAZ
Çalıştır: python test_duplicate_entity.py
"""
import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_duplicate.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="testpass", APP_SECRET="test-secret-0123456789",
    ADMIN_USERNAME="theadmin", NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_DAILY_BUDGET_USD="0", NEWSRADAR_LLM_PROVIDER="anthropic",
    NEWSRADAR_MAX_ENTITIES_REGISTERED="20",
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.api.main import app  # noqa: E402
from app.content_report import collect, open_readonly, render  # noqa: E402
from app.db.database import engine, init_db, session_scope  # noqa: E402
from app.db.models import Entity, EntityAnalysis, Suggestion, User  # noqa: E402
from app.entity_names import company_keys, duplicate_groups  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


def same(a, b):
    return bool(company_keys(*a) & company_keys(*b))


print("== A: aynı şirket tespiti ==")
check(same(("Space Exploration Technologies", "ticker", "SPCX"), ("SpaceX", "keyword", "SpaceX")),
      "SPCX ticker ↔ SpaceX keyword")
check(same(("Advanced Micro Devices Inc", "ticker", "AMD"), ("AMD", "keyword", "AMD")),
      "AMD ticker (uzun ad) ↔ AMD keyword")
check(same(("Alphabet Inc Class A", "ticker", "GOOGL"), ("Google", "keyword", "Google")),
      "Alphabet ↔ Google")
check(same(("Space X", "keyword", "Space X"), ("SpaceX", "keyword", "SpaceX")), "boşluk farkı")
check(not same(("Tesla", "ticker", "TSLA"), ("SpaceX", "keyword", "SpaceX")), "Tesla ≠ SpaceX")
check(not same(("Ford Motor", "ticker", "F"), ("F", "keyword", "F")),
      "ticker sembolü tek başına anahtar değil (F)")
groups = duplicate_groups([
    {"id": 1, "name": "Space Exploration Technologies", "type": "ticker", "query": "SPCX"},
    {"id": 2, "name": "SpaceX", "type": "keyword", "query": "SpaceX"},
    {"id": 3, "name": "Tesla", "type": "ticker", "query": "TSLA"},
])
check(len(groups) == 1 and sorted(e["id"] for e in groups[0]) == [1, 2], f"grup: {groups}")

print("== B: POST /entities mükerrer uyarısı ==")
init_db()
client = TestClient(app)


def auth_headers(username, password="pw12345678"):
    gtok = client.post("/auth/login", json={"password": "testpass"}).json()["token"]
    r = client.post("/users/register", json={"username": username, "password": password, "email": f"{uuid.uuid4().hex[:12]}@test.local"},
                    headers={"Authorization": f"Bearer {gtok}"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


ha, hb = auth_headers("ali"), auth_headers("veli")
r = client.post("/entities", json={"name": "Space Exploration Technologies", "type": "ticker",
                                   "query": "SPCX"}, headers=ha)
check(r.status_code == 201 and r.json()["display_name"] == "SpaceX", "SPCX eklendi (kısa ad SpaceX)")
spcx_id = r.json()["id"]
r = client.post("/entities", json={"name": "SpaceX", "type": "keyword", "query": "SpaceX"}, headers=ha)
body = r.json()
check(r.status_code == 409 and body.get("code") == "duplicate_entity",
      f"aynı şirket keyword olarak → 409 duplicate_entity ({r.status_code} {body.get('code')})")
check(body.get("detail") == "Bu şirket zaten listende: SpaceX", f"detail düz metin: {body.get('detail')!r}")
dup = body.get("duplicate_of") or {}
check(dup.get("id") == spcx_id and dup.get("display_name") == "SpaceX"
      and dup.get("name") == "Space Exploration Technologies" and dup.get("type") == "ticker"
      and dup.get("query") == "SPCX", f"duplicate_of mevcut entity'yi veriyor: {dup}")
with session_scope() as s:
    n_spacex = s.scalar(select(func.count()).select_from(Entity).where(Entity.query == "SpaceX"))
check(n_spacex == 0, "mükerrer entity oluşturulmadı")
r = client.post("/entities", json={"name": "Space Exploration Technologies", "type": "ticker",
                                   "query": "SPCX"}, headers=ha)
check(r.status_code == 409 and r.json().get("code") == "already_in_watchlist"
      and r.json()["duplicate_of"]["id"] == spcx_id, "birebir aynısı → 409 already_in_watchlist")
r = client.post("/entities", json={"name": "SpaceX", "type": "keyword", "query": "SpaceX"}, headers=hb)
check(r.status_code == 201, "başka kullanıcı (listesinde SPCX yok) SpaceX'i ekleyebilir")
kw_id = r.json()["id"]
r = client.post("/entities", json={"name": "Space Exploration Technologies", "type": "ticker",
                                   "query": "SPCX"}, headers=hb)
check(r.status_code == 409 and r.json()["duplicate_of"]["id"] == kw_id
      and r.json()["detail"] == "Bu şirket zaten listende: SpaceX",
      "ters yön: keyword SpaceX varken SPCX ticker → 409")
r = client.post("/entities", json={"name": "Tesla", "type": "ticker", "query": "TSLA"}, headers=ha)
check(r.status_code == 201, "farklı şirket normal eklenir")
with session_scope() as s:
    n_pool = s.scalar(select(func.count()).select_from(Entity))
check(n_pool == 3, f"havuzdaki mevcut kayıtlar silinmedi/birleştirilmedi ({n_pool})")

print("== C: öneriler ==")
with session_scope() as s:
    sug = Suggestion(name="SpaceX", ticker=None, is_public=False, norm_key="n:spacex",
                     mention_count=5, source_entity_ids=[spcx_id], source_language="en")
    s.add(sug); s.flush(); sug_id = sug.id
names = [x["name"] for x in client.get("/suggestions", headers=ha).json()]
check("SpaceX" not in names, f"SPCX takipçisine 'SpaceX' önerisi gösterilmez ({names})")
r = client.post(f"/suggestions/{sug_id}/add", headers=ha)
check(r.status_code == 409 and r.json().get("code") == "duplicate_entity"
      and r.json()["duplicate_of"]["id"] == spcx_id, f"öneriden mükerrer ekleme → 409 ({r.status_code})")

print("== D: content-report (salt okunur) ==")
now = datetime.now(timezone.utc)


def mk(eid, lang, at):
    return EntityAnalysis(entity_id=eid, language=lang, headline_verdict="v.", ai_take="t.",
                          risk_score=40, sentiment_trend="stable", top_drivers=[], summary="s.",
                          stance="neutral", conviction="low", what_to_verify=[], invalidation="i.",
                          articles_considered=1, created_at=at)


with session_scope() as s:
    tsla = s.scalar(select(Entity).where(Entity.query == "TSLA"))
    s.add(mk(tsla.id, "tr", now - timedelta(hours=30)))
    s.add(mk(tsla.id, "en", now - timedelta(hours=2)))
    s.add(EntityAnalysis(entity_id=spcx_id, language="tr", headline_verdict="Hisse already düştü.",
                         ai_take="", risk_score=60, sentiment_trend="stable", top_drivers=[],
                         summary="Özet.", stance="neutral", conviction="low", what_to_verify=[],
                         invalidation="i.", articles_considered=1, created_at=now))
with engine.connect() as conn:
    conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")


def digest():
    h = hashlib.sha256()
    for sfx in ("", "-wal"):
        if os.path.exists(_db + sfx):
            h.update(open(_db + sfx, "rb").read())
    return h.hexdigest()


before = digest()
con = open_readonly(_db)
data = collect(con, stale_hours=24, now=now)
by_q = {e["query"]: e for e in data["entities"]}
check(by_q["TSLA"]["langs"]["tr"]["status"] == "ESKİ" and by_q["TSLA"]["langs"]["en"]["status"] == "GÜNCEL",
      "Tesla: tr ESKİ (30 sa), en GÜNCEL")
check(by_q["SPCX"]["langs"]["en"]["status"] == "EKSİK" and by_q["SPCX"]["langs"]["tr"]["leaks"] == ["already"],
      "SPCX: en EKSİK, tr metninde dil sızıntısı işaretlendi")
check(len(data["duplicates"]) == 1 and sorted(e["query"] for e in data["duplicates"][0]) == ["SPCX", "SpaceX"],
      "mükerrer grup: SPCX + SpaceX")
text = render(data)
check("== (a)" in text and "== (b)" in text and "EKSİK" in text and "Space Exploration Technologies" in text,
      "render iki bölümü basıyor")
try:
    con.execute("UPDATE entities SET name = 'x'")
    wrote = True
except sqlite3.OperationalError:
    wrote = False
con.close()
check(not wrote, "bağlantı salt okunur (yazma reddedildi)")
env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "FINNHUB_API_KEY", "NEWSAPI_KEY")}
p = subprocess.run([sys.executable, "-m", "app.cli", "content-report", "--db", _db],
                   capture_output=True, text=True, env=env, timeout=60,
                   cwd=os.path.dirname(os.path.abspath(__file__)))
check(p.returncode == 0 and "Mükerrer entity grupları" in p.stdout and "SPCX" in p.stdout,
      f"CLI: python -m app.cli content-report (rc={p.returncode}) {p.stderr[-300:]}")
check(digest() == before, "rapor DB dosyasını değiştirmedi")
with session_scope() as s:
    check(s.scalar(select(User).where(User.username == "ali")) is not None, "veri yerinde")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
