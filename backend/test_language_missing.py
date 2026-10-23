"""Dil karışması — kullanıcının dilinde analiz yoksa başka dile DÜŞÜLMEZ (izole temp DB).

Doğrular:
  (A) GET /entities: TR kullanıcı, yalnızca EN analizi olan entity'de İngilizce metin GÖRMEZ;
      analysis=None + analysis_missing_language=True. TR analizi olanda normal kart.
  (B) ?lang=tr|en: arayüzün o anki dili kayıtlı dili ezer (dashboard dahil); geçersiz → kayıtlı dil
  (C) POST /users/me/language yanıttan ÖNCE commit eder (get_db commit'i yanıttan sonra
      çalışıyordu → hemen ardından gelen GET eski dilde kart alıyordu)
  (D) atlama kuralı: yeni veri YOKKEN bile o dilde hiç analiz yoksa o dil değerlendirilir;
      diğer (güncel) dil atlanır
Çalıştır: python test_language_missing.py
"""
import asyncio
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_lang_missing.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="testpass", APP_SECRET="test-secret-0123456789",
    ADMIN_USERNAME="theadmin", NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_DAILY_BUDGET_USD="0", NEWSRADAR_LLM_PROVIDER="anthropic",
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.analysis.pipeline import analyze_all_async  # noqa: E402
from app.analysis.schemas import ENTITY_ANALYSIS_TOOL  # noqa: E402
from app.api.main import app  # noqa: E402
from app.api.routes_users import LanguageIn, set_language  # noqa: E402
from app.db.database import SessionLocal, init_db, session_scope  # noqa: E402
from app.db.models import Article, Entity, EntityAnalysis, User, UserWatchlist  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


def now():
    return datetime.now(timezone.utc)


def mk(entity_id, language, verdict, at=None):
    return EntityAnalysis(
        entity_id=entity_id, language=language, headline_verdict=verdict, ai_take="t.",
        risk_score=40, sentiment_trend="stable", top_drivers=["d."], summary="s.",
        stance="neutral", conviction="medium", what_to_verify=["v."], invalidation="i.",
        articles_considered=3, created_at=at or now(),
    )


init_db()
client = TestClient(app)


def auth_headers(username, password="pw12345678"):
    gtok = client.post("/auth/login", json={"password": "testpass"}).json()["token"]
    r = client.post("/users/register", json={"username": username, "password": password},
                    headers={"Authorization": f"Bearer {gtok}"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


h = auth_headers("ayse")
client.post("/users/me/language", json={"language": "tr"}, headers=h)
with session_scope() as s:
    uid = s.scalar(select(User.id).where(User.username == "ayse"))
    only_en = Entity(name="Advanced Micro Devices", display_name="AMD", type="ticker", query="AMD")
    both = Entity(name="Tesla", type="ticker", query="TSLA")
    s.add_all([only_en, both]); s.flush()
    s.add(mk(only_en.id, "en", "AMD news is upbeat on MI400."))
    s.add(mk(both.id, "tr", "Tesla teslimatları beklentiyi aştı."))
    s.add(mk(both.id, "en", "Tesla deliveries beat estimates."))
    s.add_all([UserWatchlist(user_id=uid, entity_id=only_en.id),
               UserWatchlist(user_id=uid, entity_id=both.id)])
    amd_id, tsla_id = only_en.id, both.id

print("== A: TR kullanıcı, yalnızca EN analizi olan entity ==")
cards = {c["query"]: c for c in client.get("/entities", headers=h).json()}
amd, tsla = cards["AMD"], cards["TSLA"]
check(amd["analysis"] is None and amd["analysis_language"] is None,
      "AMD: İngilizce analiz Türkçe arayüze DÖNMEDİ (analysis=None)")
check(amd["analysis_missing_language"] is True, "AMD: analysis_missing_language=True")
check(tsla["analysis"]["headline_verdict"].startswith("Tesla teslimatları")
      and tsla["analysis_language"] == "tr" and tsla["analysis_missing_language"] is False,
      "Tesla: TR analiz gösterildi, bayrak False")
d = client.get(f"/entities/{amd_id}/dashboard", headers=h).json()
check(d["entity"]["analysis"] is None and d["entity"]["analysis_missing_language"] is True,
      "detay (dashboard) da başka dile düşmüyor")

print("== B: ?lang= arayüz dili kayıtlı dili ezer ==")
cards_en = {c["query"]: c for c in client.get("/entities?lang=en", headers=h).json()}
check(cards_en["AMD"]["analysis"]["headline_verdict"].startswith("AMD news")
      and cards_en["AMD"]["analysis_language"] == "en", "?lang=en → EN analiz (kayıtlı dil tr olsa da)")
cards_bad = {c["query"]: c for c in client.get("/entities?lang=xx", headers=h).json()}
check(cards_bad["AMD"]["analysis"] is None, "geçersiz ?lang → kayıtlı dil (tr)")
d_en = client.get(f"/entities/{tsla_id}/dashboard?lang=en", headers=h).json()
check(d_en["entity"]["analysis_language"] == "en" and len(d_en["risk_history"]) == 1,
      "dashboard ?lang=en → EN kart + EN risk geçmişi")

print("== C: /users/me/language yanıttan önce commit eder ==")
db = SessionLocal()
try:
    user = db.get(User, uid)
    set_language(LanguageIn(language="en"), user=user, db=db)
    # get_db'nin yanıttan SONRA çalışan commit'i hiç çalışmasa bile değişiklik görünmeli.
    other = SessionLocal()
    try:
        seen = other.get(User, uid).language
    finally:
        other.close()
finally:
    db.close()
check(seen == "en", f"ayrı oturum yeni dili hemen görüyor ({seen})")
client.post("/users/me/language", json={"language": "tr"}, headers=h)

print("== D: atlama kuralı eksik dili hesaba katar ==")
cap_msgs = []


class Cap(logging.Handler):
    def emit(self, r):
        cap_msgs.append(r.getMessage())


lg = logging.getLogger("newsradar.analysis")
lg.addHandler(Cap()); lg.setLevel(logging.INFO)


class FakeClient:
    model = "fake"

    def __init__(self):
        self.langs = []

    def call_tool(self, *, system, user, tool, max_tokens=4096):
        if tool["name"] == ENTITY_ANALYSIS_TOOL["name"]:
            en = "CRITICAL RULES" in user
            self.langs.append("en" if en else "tr")
            return ({"headline_verdict": "Verdict.", "summary": "Summary.", "risk_score": 40}
                    if en else {"headline_verdict": "Hüküm.", "summary": "Özet.", "risk_score": 40})
        return {"analyses": []}


with session_scope() as s:
    e = Entity(name="Anthropic", type="keyword", query="Anthropic", active=True)
    s.add(e); s.flush()
    kid = e.id
    s.add(Article(entity_id=kid, url="http://a/1", url_hash="k1", title="Anthropic news",
                  source="s", description="d", provider="t", analyzed=True,
                  analyzed_at=now() - timedelta(hours=3), prefiltered=False,
                  sentiment=0.2, event_type="other", relevance=0.9))
    # TR güncel (makaleden SONRA) → yeni veri yok; EN hiç yok.
    s.add(mk(kid, "tr", "Anthropic hükmü.", at=now() - timedelta(hours=1)))
fc = FakeClient()
totals = asyncio.run(analyze_all_async(fc, entity_ids={kid}))
check(fc.langs == ["en"], f"yeni veri yokken yalnızca eksik EN değerlendirildi ({fc.langs})")
check(totals.assessments_skipped == 1, f"güncel TR atlandı (atlanan={totals.assessments_skipped})")
check(any("[Anthropic] değerlendirme yapılacak (en): bu dilde değerlendirme yok" in m for m in cap_msgs),
      "log: eksik dil sebebi yazıldı")
fc2 = FakeClient()
asyncio.run(analyze_all_async(fc2, entity_ids={kid}))
check(fc2.langs == [], f"iki dil de varken yeni veri yok → atlandı ({fc2.langs})")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
