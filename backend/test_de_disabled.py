"""Almanca bayrağı KAPALI (NEWSRADAR_ENABLE_DE varsayılanı) — sahte çıktı, gerçek API yok, izole DB.

Doğrular:
  (A) dil kodu: "de" kaydedilmez (en olur), Accept-Language de → en, açık diller tr/en
  (B) daha önce DE seçmiş kullanıcının kayıtlı tercihi en okunur (profil, e-posta, içerik dili)
  (C) public: diller tr/en; how-it-works ?lang=de → EN içerik
  (D) değerlendirmede DE çevirisi YAPILMAZ (yalnızca TR çevirisi); eksik DE tamamlanmaz
Çalıştır: python test_de_disabled.py
"""
import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_de_disabled.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.pop("NEWSRADAR_ENABLE_DE", None)
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="genelsifre", APP_SECRET="dd-secret-1234567890",
    ADMIN_USERNAME="rootadmin", NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_MAX_USERS="0", NEWSRADAR_TRUSTED_PROXY="render", NEWSRADAR_COOKIE_SECURE="off",
    NEWSRADAR_COOKIE_SAMESITE="lax", NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR="0",
    EMAIL_BACKEND="console", NEWSRADAR_PUBLIC_URL="https://newsradar.example",
    NEWSRADAR_DAILY_BUDGET_USD="0", NEWSRADAR_LLM_PROVIDER="anthropic",
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, update  # noqa: E402

from app.analysis.pipeline import analyze_all_async  # noqa: E402
from app.analysis.schemas import ENTITY_ANALYSIS_TOOL, TRANSLATION_TOOL  # noqa: E402
from app.api.main import app  # noqa: E402
from app.api.serializers import content_language  # noqa: E402
from app.db.database import SessionLocal, init_db, session_scope  # noqa: E402
from app.db.models import Article, Entity, EntityAnalysis, User  # noqa: E402
from app.languages import de_enabled, language_from_accept, normalize_language, ui_languages  # noqa: E402
from app.mailer import get_mailer  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


_ip = [0]


def xff():
    _ip[0] += 1
    return {"X-Forwarded-For": f"198.51.100.{_ip[0]}"}


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


print("== A: dil kodu ==")
check(not de_enabled() and ui_languages() == ("tr", "en"), "varsayılan: DE kapalı, açık diller tr/en")
check(normalize_language("de") == "en" and normalize_language("tr") == "tr", "de kaydedilmez → en")
check(language_from_accept("de-DE,de;q=0.9") == "en" and language_from_accept("tr-TR") == "tr",
      "Accept-Language de → en, tr → tr")

with TestClient(app) as c:
    c.post("/users/register", json={"username": "rootadmin", "password": "parola12345", "email": "r@example.com"},
           headers=xff())
    r = c.post("/users/register", json={"username": "lena", "password": "parola12345", "email": "l1@example.com"},
               headers=xff())
    tok = r.json()["token"]
    me = c.post("/users/me/language", json={"language": "de"}, headers=auth(tok)).json()
    check(me["language"] == "en", f"POST /users/me/language de → en ({me['language']})")
    r = c.post("/session/bootstrap", headers={**xff(), "Accept-Language": "de-DE,de;q=0.9"})
    check(r.json()["user"]["language"] == "en", "anonim oturum: de tarayıcı → en")

    print("== B: daha önce DE seçmiş kullanıcı ==")
    with SessionLocal() as s:
        s.execute(update(User).where(User.username == "lena").values(language="de"))
        s.commit()
    check(c.get("/users/me", headers=auth(tok)).json()["language"] == "en", "kayıtlı 'de' → profilde en")
    get_mailer().sent.clear()
    c.post("/users/me/email", json={"email": "lena@example.com"}, headers=auth(tok))
    sent = get_mailer().sent
    check(bool(sent) and sent[-1].subject == "NewsRadar: verify your email address" and 'lang="en"' in sent[-1].html,
          f"e-posta İngilizce ({sent[-1].subject if sent else '-'})")
    r = c.post("/users/login", json={"username": "lena", "password": "yanlis-sifre"}, headers=xff())
    check(r.json().get("code") == "login_invalid", "hata kodu (metin TR/EN arayüzde)")
    check(content_language(type("U", (), {"language": "de"})()) == "en"
          and content_language(type("U", (), {"language": "tr"})(), "de") == "en", "içerik dili: de → en")

    print("== C: public ==")
    check(c.get("/public/stats").json()["languages"] == ["tr", "en"], "public diller tr/en")
    check(c.get("/public/how-it-works", params={"lang": "de"}).status_code == 200, "how-it-works ?lang=de → 200 (EN)")

print("== D: DE çevirisi yapılmaz ==")
now = datetime.now(timezone.utc)


class Fake:
    model = "fake"

    def __init__(self):
        self.calls = []

    def call_tool(self, *, system, user, tool, max_tokens=4096):
        if tool["name"] == TRANSLATION_TOOL["name"]:
            self.calls.append("de" if "plain German" in user else "tr")
            src, _ = json.JSONDecoder().raw_decode(user.split("JSON:\n", 1)[1])
            return {k: ([f"TR {x}" for x in v] if isinstance(v, list) else (f"TR {v}" if v else "")) for k, v in src.items()}
        if tool["name"] == ENTITY_ANALYSIS_TOOL["name"]:
            self.calls.append("assess")
            return {"headline_verdict": "Verdict.", "summary": "Summary.", "risk_score": 40}
        return {"analyses": []}


init_db()
with session_scope() as s:
    e = Entity(name="Acme", type="keyword", query="Acme", active=True)
    s.add(e); s.flush()
    eid = e.id
    s.add(Article(entity_id=eid, url="http://a/1", url_hash="a1", title="Acme news", source="s", description="d",
                  provider="t", analyzed=True, analyzed_at=now - timedelta(hours=1), prefiltered=False,
                  sentiment=0.2, event_type="other", relevance=0.9))
f = Fake()
asyncio.run(analyze_all_async(f, entity_ids={eid}))
with session_scope() as s:
    row = s.scalars(select(EntityAnalysis).where(EntityAnalysis.entity_id == eid)).first()
    langs = sorted(row.texts or {})
check(f.calls == ["assess", "tr"] and langs == ["en", "tr"], f"yalnızca TR çevirisi ({f.calls}, {langs})")
f2 = Fake()
asyncio.run(analyze_all_async(f2, entity_ids={eid}))
check(f2.calls == [], f"eksik DE tamamlanmaz, çağrı yok ({f2.calls})")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
