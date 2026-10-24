"""Kısa görünen ad (display_name) — kolon migration'ı + backfill + API (izole temp DB).

Doğrular:
  (A) eski DB'de (kolon yok) init_db kolonu ekler; bilinen uzun adlar doldurulur,
      bilinmeyen ad NULL kalır; ikinci init_db idempotent, elle verilen değer korunur
  (B) display_name_for: ek/noktalama/parantez normalizasyonu, bilinmeyen → None,
      kısa ad adla aynıysa → None
  (C) API: GET /entities kartında display_name; POST /entities yeni entity'ye kısa adı
      yazar; admin kullanıcı detayı listesinde display_name
Çalıştır: python test_display_name.py
"""
import os
import sqlite3
import tempfile
import uuid

_db = os.path.join(tempfile.gettempdir(), "nr_test_display_name.db")
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

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


# --- Eski şema: display_name kolonu OLMAYAN entities tablosu (canlı DB'nin bugünkü hali) ---
OLD_ROWS = [
    ("Advanced Micro Devices", "ticker", "AMD"),
    ("Meta Platforms Inc", "ticker", "META"),
    ("Space Exploration Technologies", "ticker", "SPCX"),
    ("Alphabet Inc.", "ticker", "GOOGL"),
    ("NVIDIA Corporation", "ticker", "NVDA"),
    ("Tesla", "ticker", "TSLA"),
    ("Bilinmeyen Girişim", "keyword", "Bilinmeyen Girişim"),
    ("OCUGEN INC", "ticker", "OCGN"),  # tamamı büyük harf → bir kerelik okunur ad
]
con = sqlite3.connect(_db)
con.execute(
    "CREATE TABLE entities (id INTEGER PRIMARY KEY, name VARCHAR(200) NOT NULL, "
    "type VARCHAR(20) NOT NULL, query VARCHAR(200) NOT NULL, "
    "language VARCHAR(5) NOT NULL DEFAULT 'en', active BOOLEAN NOT NULL DEFAULT 1, "
    "created_at DATETIME NOT NULL, CONSTRAINT uq_entity_type_query UNIQUE (type, query))"
)
for n, t, q in OLD_ROWS:
    con.execute("INSERT INTO entities (name, type, query, created_at) VALUES (?, ?, ?, "
                "'2026-10-01 00:00:00')", (n, t, q))
con.commit()
con.close()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.database import engine, init_db, session_scope  # noqa: E402
from app.db.models import Entity  # noqa: E402
from app.entity_names import backfill_display_names, display_name_for  # noqa: E402


def display_map():
    with session_scope() as s:
        return {e.name: e.display_name for e in s.scalars(select(Entity)).all()}


print("== A: migration + backfill ==")
init_db()
with engine.begin() as conn:
    cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(entities)")}
check("display_name" in cols, "entities.display_name kolonu eklendi")
dm = display_map()
check(dm["Advanced Micro Devices"] == "AMD", f"Advanced Micro Devices → AMD ({dm['Advanced Micro Devices']})")
check(dm["Meta Platforms Inc"] == "Meta", f"Meta Platforms Inc → Meta ({dm['Meta Platforms Inc']})")
check(dm["Space Exploration Technologies"] == "SpaceX", "Space Exploration Technologies → SpaceX")
check(dm["Alphabet Inc."] == "Google", "Alphabet Inc. → Google")
check(dm["NVIDIA Corporation"] == "NVIDIA", "NVIDIA Corporation → NVIDIA")
check(dm["Tesla"] is None, "zaten kısa ad (Tesla) → NULL")
check(dm["Bilinmeyen Girişim"] is None, "bilinmeyen ad → NULL")
check(dm["OCUGEN INC"] == "Ocugen", f"mevcut kayıt: OCUGEN INC → Ocugen ({dm['OCUGEN INC']})")

# Elle verilen değer korunur; ikinci init_db idempotent (hata yok, değer değişmez).
with session_scope() as s:
    e = s.scalar(select(Entity).where(Entity.query == "AMD"))
    e.display_name = "AMD Inc (elle)"
init_db()
with engine.begin() as conn:
    n2 = backfill_display_names(conn)
dm2 = display_map()
check(dm2["Advanced Micro Devices"] == "AMD Inc (elle)",
      "dolu display_name'e backfill dokunmaz (elle verilen korunur)")
check(n2 == 0, f"ikinci backfill hiçbir satırı değiştirmez ({n2})")

print("== B: display_name_for ==")
check(display_name_for("ADVANCED MICRO DEVICES INC") == "AMD", "büyük harf + Inc → AMD")
check(display_name_for("Meta Platforms, Inc. (Class A)") == "Meta", "virgül/parantez/sınıf → Meta")
check(display_name_for("META PLATFORMS INC-CLASS A") == "Meta", "Finnhub biçimi 'INC-CLASS A' → Meta")
check(display_name_for("Amazon.com, Inc.") == "Amazon", "Amazon.com, Inc. → Amazon")
check(display_name_for("ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş.") == "Aselsan",
      "Türkçe büyük harf (İ) + A.Ş. → Aselsan")
check(display_name_for("Space Exploration Technologies Corp.") == "SpaceX", "… Corp. → SpaceX")
check(display_name_for("SpaceX") is None, "kısa ad = ad → None")
check(display_name_for("Anthropic") is None, "bilinmeyen → None")
check(display_name_for("") is None, "boş → None")
# Tamamı büyük harf resmi adlar okunur hale gelir; kısaltmalar ve karışık harfli adlar korunur.
check(display_name_for("OCUGEN INC") == "Ocugen", f"OCUGEN INC → Ocugen ({display_name_for('OCUGEN INC')})")
check(display_name_for("BANK OF AMERICA CORP") == "Bank of America", "bağlaç küçük, ek atılır")
check(display_name_for("PROCTER & GAMBLE CO") == "Procter & Gamble", "& korunur, sondaki Co atılır")
check(display_name_for("AT&T INC") == "AT&T", "AT&T kısaltma olarak kalır")
check(display_name_for("IBM") is None and display_name_for("AMD") is None, "kısa kısaltma = ad → None")
check(display_name_for("Plug Power") is None, "karışık harfli ad dokunulmaz")

print("== C: API ==")
from app.api.main import app  # noqa: E402
from app.db.models import User, UserWatchlist  # noqa: E402

client = TestClient(app)


def auth_headers(username, password="pw12345678"):
    gtok = client.post("/auth/login", json={"password": "testpass"}).json()["token"]
    r = client.post("/users/register", json={"username": username, "password": password, "email": f"{uuid.uuid4().hex[:12]}@test.local"},
                    headers={"Authorization": f"Bearer {gtok}"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


admin = auth_headers("theadmin")
h = auth_headers("alice")
with session_scope() as s:
    uid = s.scalar(select(Entity.id).where(Entity.query == "SPCX"))

with session_scope() as s:
    alice = s.scalar(select(User).where(User.username == "alice"))
    s.add(UserWatchlist(user_id=alice.id, entity_id=uid))
    alice_id = alice.id
cards = client.get("/entities", headers=h).json()
check(len(cards) == 1 and cards[0]["display_name"] == "SpaceX" and
      cards[0]["name"] == "Space Exploration Technologies",
      f"GET /entities kartında display_name=SpaceX, name korunur ({cards})")
r = client.post("/entities", json={"name": "Taiwan Semiconductor Manufacturing Co Ltd",
                                   "type": "ticker", "query": "TSM"}, headers=h)
check(r.status_code == 201 and r.json()["display_name"] == "TSMC",
      f"POST /entities yeni entity'ye kısa ad yazar ({r.status_code} {r.json().get('display_name')})")
r = client.post("/entities", json={"name": "Anthropic", "type": "keyword", "query": "Anthropic"},
                headers=h)
check(r.status_code == 201 and r.json()["display_name"] is None,
      "bilinmeyen ad → display_name null (arayüz name'e düşer)")
det = client.get(f"/admin/users/{alice_id}", headers=admin)
wl = det.json().get("watchlist", []) if det.status_code == 200 else []
check(any(w.get("display_name") == "SpaceX" for w in wl),
      f"admin kullanıcı detayı watchlist'inde display_name ({det.status_code})")
st = client.get("/admin/stats", headers=admin)
mf = st.json().get("most_followed", []) if st.status_code == 200 else []
check(any(m.get("display_name") == "SpaceX" for m in mf),
      f"admin stats most_followed'da display_name ({st.status_code})")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
