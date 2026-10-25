"""Çerezsiz ziyaretçi sayacı (izole temp DB, anahtarsız).

Doğrular:
  (A) aynı kişi (IP+UA) aynı gün TEK ziyaretçi, her görüntüleme ayrı sayılır
  (B) ertesi gün: tuz yenilenir, eskisi silinir → aynı kişi FARKLI özet; ham IP/UA saklanmaz
  (C) botlar (UA listesi, Lighthouse, Playwright/headless, curl, boş UA) ve admin sayılmaz
  (D) kaynak: yönlendiren alan adı (www. atılır), kendi sitemiz / http dışı → doğrudan
  (E) istatistik: 30 günlük seri, en çok gelen 5 kaynak, landing → uygulama geçiş oranı
  (F) uçlar: POST /public/pv 204 (admin token'ıyla sayılmaz), GET /admin/visits yalnızca admin
Çalıştır: python test_visits.py
"""
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_visits.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(NEWSRADAR_DB=_db, NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
                  APP_SECRET="v-secret-1234567890", ADMIN_USERNAME="rootadmin", NEWSRADAR_TRUSTED_PROXY="render",
                  NEWSRADAR_CORS_ORIGINS="https://newsradarapp.com,https://www.newsradarapp.com",
                  NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR="0", NEWSRADAR_MAX_USERS="0")

from fastapi.testclient import TestClient  # noqa: E402

from app import visits as V  # noqa: E402
from app.api.main import app  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import PageView, VisitSalt  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


CHROME = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
D1 = datetime(2026, 10, 24, 10, tzinfo=timezone.utc)
D2 = D1 + timedelta(days=1)
init_db()

print("== A: aynı kişi aynı gün tek")
with SessionLocal() as s:
    for page in ("landing", "app", "detail"):
        V.record_view(s, page, "https://www.linkedin.com/feed/", "203.0.113.7", CHROME, now=D1)
    V.record_view(s, "landing", None, "203.0.113.8", SAFARI, now=D1)  # ikinci kişi, doğrudan
    s.commit()
    rows = s.query(PageView).filter_by(day="2026-10-24").all()
    hashes = {r.visitor_hash for r in rows}
check(len(rows) == 4 and len(hashes) == 2, f"4 görüntüleme, 2 benzersiz ziyaretçi ({len(rows)}, {len(hashes)})")

print("== B: ertesi gün farklı özet, eski tuz silinir")
with SessionLocal() as s:
    h1 = next(r.visitor_hash for r in s.query(PageView).filter_by(day="2026-10-24") if r.referrer == "linkedin.com")
    V.record_view(s, "landing", None, "203.0.113.7", CHROME, now=D2)
    s.commit()
    h2 = s.query(PageView).filter_by(day="2026-10-25").one().visitor_hash
    salts = [x.day for x in s.query(VisitSalt).all()]
    dump = " ".join(f"{r.visitor_hash} {r.referrer} {r.page}" for r in s.query(PageView))
check(h1 != h2, "aynı IP+UA ertesi gün farklı özet")
check(salts == ["2026-10-25"], f"dünün tuzu silindi ({salts})")
check("203.0.113" not in dump and "Mozilla" not in dump and "Chrome" not in dump, "ham IP ve User-Agent hiçbir alanda yok")
check({c.name for c in PageView.__table__.columns} == {"id", "day", "page", "visitor_hash", "referrer", "created_at"},
      "tabloda IP/UA/ülke kolonu yok")

print("== C: bot ve admin ayıklama")
bots = ["Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/130.0 Safari/537.36 Chrome-Lighthouse",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 HeadlessChrome/130.0 Safari/537.36",
        "Googlebot/2.1 (+http://www.google.com/bot.html)", "curl/8.4.0", "python-requests/2.32", "",
        "Mozilla/5.0 Playwright/1.48", "LinkedInBot/1.0", "facebookexternalhit/1.1"]
with SessionLocal() as s:
    counted = [V.record_view(s, "landing", None, "198.51.100.1", ua, now=D2) for ua in bots]
    admin = V.record_view(s, "app", None, "198.51.100.2", CHROME, is_admin=True, now=D2)
    bad_page = V.record_view(s, "admin", None, "198.51.100.3", CHROME, now=D2)
    s.commit()
check(not any(counted), f"botlar sayılmadı ({sum(counted)}/{len(bots)})")
check(not admin and not bad_page, "admin ziyareti ve geçersiz sayfa türü sayılmadı")
check(not V.is_bot(CHROME) and not V.is_bot(SAFARI), "gerçek tarayıcılar bot sayılmaz")

print("== D: kaynak alan adı")
check(V.referrer_domain("https://www.linkedin.com/feed/") == "linkedin.com", "www.linkedin.com → linkedin.com")
check(V.referrer_domain("https://newsradarapp.com/app") is None and V.referrer_domain("https://www.newsradarapp.com/") is None,
      "kendi sitemiz → doğrudan")
check(V.referrer_domain("android-app://com.slack") is None and V.referrer_domain("") is None and V.referrer_domain(None) is None,
      "http dışı / boş → doğrudan")
check(V.referrer_domain("https://news.ycombinator.com/item?id=1") == "news.ycombinator.com", "alt alan adı korunur")

print("== E: istatistik")
with SessionLocal() as s:
    st = V.stats(s, days=30, now=D2)
check(len(st["days"]) == 30 and st["days"][-1]["day"] == "2026-10-25" and st["days"][-2] == {"day": "2026-10-24", "visitors": 2, "views": 4},
      f"30 günlük seri, 24 Ekim: 2 ziyaretçi / 4 görüntüleme ({st['days'][-2]})")
check(st["top_referrers"] == [{"domain": "linkedin.com", "visitors": 1}], f"en çok gelen kaynaklar ({st['top_referrers']})")
check(st["landing_visitors"] == 3 and st["landing_to_app"] == 1 and st["conversion_rate"] == 0.333,
      f"landing → uygulama: 3 landing ziyaretçisinden 1'i ({st['conversion_rate']})")

print("== F: uçlar")
with TestClient(app) as c:
    r = c.post("/users/register", json={"username": "rootadmin", "password": "parola12345", "email": f"{uuid.uuid4().hex[:8]}@example.com"},
               headers={"X-Forwarded-For": "192.0.2.50"})
    atok = r.json()["token"]
    before = SessionLocal().query(PageView).count()
    r1 = c.post("/public/pv", json={"page": "landing", "referrer": "https://t.co/x"}, headers={"User-Agent": CHROME, "X-Forwarded-For": "192.0.2.10"})
    r2 = c.post("/public/pv", json={"page": "app"}, headers={"User-Agent": CHROME, "X-Forwarded-For": "192.0.2.11", "Authorization": f"Bearer {atok}"})
    r3 = c.post("/public/pv", json={"page": "app"}, headers={"User-Agent": CHROME, "X-Forwarded-For": "192.0.2.12", "Authorization": "Bearer bozuk.token.x"})
    after = SessionLocal().query(PageView).count()
    check(r1.status_code == r2.status_code == r3.status_code == 204, "POST /public/pv her durumda 204")
    check(after - before == 2, f"admin token'ıyla gelen sayılmadı, bozuk token sıradan ziyaretçi ({after - before})")
    anon = c.post("/session/bootstrap", headers={"X-Forwarded-For": "192.0.2.13"}).json()["token"]
    check(c.get("/admin/visits", headers={"Authorization": f"Bearer {anon}"}).status_code == 403, "admin dışı /admin/visits 403")
    g = c.get("/admin/visits", headers={"Authorization": f"Bearer {atok}"})
    check(g.status_code == 200 and len(g.json()["days"]) == 30 and "conversion_rate" in g.json(), "admin /admin/visits 200")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
