"""Öneri açıklaması arayüz dilinde (izole temp DB, sahte LLM; gerçek çağrı yok).

Doğrular:
  (A) istem: why_relevant makale analizinde EN üretilir, rationale TR kalır
  (B) biriktirme: EN kaynak why_texts'e yazılır; Türkçe sızan gerekçe kaynak sayılmaz; yeni
      gerekçe eski çevirileri ve eski kolonu geçersiz kılar; aynı gerekçe çeviriyi korur
  (C) çeviri: yalnızca gösterilebilir öneriler, yalnızca eksik dil (DE kapalıyken DE yok);
      başarısız dil yazılmaz; kota durdurur; tarama başına tavan; ikinci turda çağrı yok
  (D) GET /suggestions: EN arayüz → EN, TR arayüz → TR; çevirisi yoksa açıklama null;
      eski (Türkçe) kayıt TR'de görünür, EN'de null; ?lang yoksa kullanıcının dili
  (E) göç: eski tabloya why_texts eklenir, eski gerekçe silinmez
Çalıştır: python test_suggestion_language.py
"""
import os
import sqlite3
import sys
import tempfile
import uuid
from datetime import datetime, timezone

_db = os.path.join(tempfile.gettempdir(), "nr_test_suggestion_lang.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="testpass", APP_SECRET="test-secret-0123456789",
    ADMIN_USERNAME="theadmin", NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_DAILY_BUDGET_USD="0", NEWSRADAR_LLM_PROVIDER="anthropic", NEWSRADAR_ENABLE_DE="0",
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.analysis import pipeline  # noqa: E402
from app.analysis.claude_client import ClaudeError, ProviderQuotaError  # noqa: E402
from app.analysis.pipeline import _accumulate_suggestions, translate_suggestions  # noqa: E402
from app.analysis.prompts import SYSTEM_PROMPT, build_article_batch_prompt  # noqa: E402
from app.analysis.schemas import ARTICLE_ANALYSIS_TOOL, SUGGESTION_TRANSLATION_TOOL  # noqa: E402
from app.api.main import app  # noqa: E402
from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import Entity, Suggestion, User, UserWatchlist  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


EN = "Anthropic is growing quickly with its enterprise AI products."
TR = "Anthropic, kurumsal yapay zeka ürünleriyle hızla büyüyor."
OLD_TR = "Anthropic'in hızlı büyümesi, Alphabet'in yatırımını artırıyor."


class FakeLLM:
    """Sahte çeviri istemcisi: `replies` sırayla döner (istisna ise atılır), bitince TR."""

    def __init__(self, replies=None):
        self.replies = list(replies or [])
        self.calls = []

    def call_tool(self, system, user, tool, max_tokens):
        self.calls.append({"user": user, "tool": tool})
        reply = self.replies.pop(0) if self.replies else {"why_relevant": TR}
        if isinstance(reply, Exception):
            raise reply
        return reply


def co(name, why, ticker=None):
    return {"name": name, "ticker": ticker, "is_public": True, "why_relevant": why}


def row(name):
    with session_scope() as s:
        sug = s.scalar(select(Suggestion).where(Suggestion.name == name))
        return dict(sug.why_texts or {}), sug.why_relevant, sug.mention_count


def add_row(name, mentions=3, **kw):
    now = datetime.now(timezone.utc)
    with session_scope() as s:
        s.add(Suggestion(name=name, norm_key=f"n:{name.lower()}", mention_count=mentions,
                         source_entity_ids=kw.pop("sources", []), first_seen_at=now,
                         last_seen_at=now, **kw))


init_db()

print("== A: istem ==")
user_prompt = build_article_batch_prompt("X", "X", "keyword", [{"id": 1, "title": "t"}], "en")
why_schema = (ARTICLE_ANALYSIS_TOOL["input_schema"]["properties"]["analyses"]["items"]["properties"]
              ["co_mentioned_entities"]["items"]["properties"]["why_relevant"]["description"])
check("İNGİLİZCE" in why_schema and "TÜRKÇE" not in why_schema, "araç şeması: why_relevant İngilizce")
check("tek cümle İNGİLİZCE" in SYSTEM_PROMPT, "sistem istemi: why_relevant İngilizce")
check("`why_relevant` HER ZAMAN AKICI İNGİLİZCE" in user_prompt, "kullanıcı istemi: why_relevant istisnası")
check("(rationale," in user_prompt and "invalidation, why_relevant" not in user_prompt,
      "rationale Türkçe yönergede kaldı, why_relevant çıktı")

print("== B: biriktirme ==")
with session_scope() as s:
    _accumulate_suggestions(s, 1, "en", [co("Anthropic", EN)])
    _accumulate_suggestions(s, 1, "en", [co("Sizinti", OLD_TR)])
check(row("Anthropic")[:2] == ({"en": EN}, None), "yeni kayıt: EN kaynak why_texts'e yazıldı")
check(row("Sizinti")[:2] == ({}, None), "Türkçe gelen gerekçe kaynak sayılmadı")

with session_scope() as s:
    sug = s.scalar(select(Suggestion).where(Suggestion.name == "Anthropic"))
    sug.why_texts = {"en": EN, "tr": TR}
with session_scope() as s:
    _accumulate_suggestions(s, 1, "en", [co("Anthropic", EN)])
    _accumulate_suggestions(s, 2, "en", [co("Anthropic", None)])
    _accumulate_suggestions(s, 2, "en", [co("Anthropic", OLD_TR)])
texts, _, mentions = row("Anthropic")
check(texts == {"en": EN, "tr": TR} and mentions == 4,
      "aynı/boş/Türkçe gerekçe çeviriyi korur (çeviri maliyeti yok), anılma sayılır")
NEW = "Anthropic signed a new cloud deal."
with session_scope() as s:
    _accumulate_suggestions(s, 2, "en", [co("Anthropic", NEW)])
check(row("Anthropic")[0] == {"en": NEW}, "yeni gerekçe: eski çeviri silindi")

add_row("Eski", why_relevant=OLD_TR)
with session_scope() as s:
    _accumulate_suggestions(s, 1, "en", [co("Eski", EN)])
check(row("Eski")[:2] == ({"en": EN}, None), "eski kayıt yeniden anılınca EN kaynağa geçti, eski kolon temizlendi")
with session_scope() as s:
    for sug in s.scalars(select(Suggestion)).all():
        s.delete(sug)

print("== C: çeviri ==")
add_row("Hedef", why_texts={"en": EN})
add_row("Az", mentions=2, why_texts={"en": EN})
add_row("Kapali", why_texts={"en": EN}, dismissed=True)
add_row("Hazir", why_texts={"en": EN, "tr": TR})
add_row("KaynakYok", why_relevant=OLD_TR)
llm = FakeLLM()
check(translate_suggestions(llm) == 1 and len(llm.calls) == 1, "yalnızca gösterilebilir ve eksik öneri çevrildi")
check(llm.calls[0]["tool"] is SUGGESTION_TRANSLATION_TOOL and EN in llm.calls[0]["user"],
      "çağrı: öneri çeviri aracı, kaynak EN metin")
check("Türkçe" in llm.calls[0]["user"], "hedef dil Türkçe (DE kapalı → DE çağrısı yok)")
check(row("Hedef")[0] == {"en": EN, "tr": TR}, "çeviri kaydedildi")
check(row("Az")[0] == {"en": EN} and row("Kapali")[0] == {"en": EN}, "az anılan/kapatılan için çeviri yok")
check(row("KaynakYok")[:2] == ({}, OLD_TR), "EN kaynağı olmayan eski kayıt çevrilmez, gerekçesi durur")
llm2 = FakeLLM()
check(translate_suggestions(llm2) == 0 and not llm2.calls, "ikinci turda LLM çağrısı yok")

add_row("Bozuk", why_texts={"en": EN})
bad = FakeLLM([{"why_relevant": ""}, ClaudeError("sahte hata")])
check(translate_suggestions(bad) == 0 and len(bad.calls) == 2, "geçersiz çıktı bir kez yeniden istenir")
check(row("Bozuk")[0] == {"en": EN}, "çeviri başarısız → TR yazılmadı (yanlış dilde metin yok)")
leak = FakeLLM([{"why_relevant": "Anthropic however hızla büyüyor."}, {"why_relevant": TR}])
check(translate_suggestions(leak) == 1 and len(leak.calls) == 2 and row("Bozuk")[0]["tr"] == TR,
      "dil sızıntısı notla yeniden istendi; sonraki tur eksik dili tamamladı")

add_row("Kota1", mentions=9, why_texts={"en": EN})
add_row("Kota2", mentions=8, why_texts={"en": EN})
quota = FakeLLM([ProviderQuotaError("sahte kota")])
check(translate_suggestions(quota) == 0 and len(quota.calls) == 1, "kota hatası kalan çağrıları durdurur")
translate_suggestions(FakeLLM())

_limit, pipeline.SUGGESTION_TRANSLATIONS_PER_RUN = pipeline.SUGGESTION_TRANSLATIONS_PER_RUN, 2
for i in range(3):
    add_row(f"Tavan{i}", mentions=20 - i, why_texts={"en": EN})
capped = FakeLLM()
translate_suggestions(capped)
pipeline.SUGGESTION_TRANSLATIONS_PER_RUN = _limit
check(len(capped.calls) == 2 and "tr" in row("Tavan0")[0] and "tr" not in row("Tavan2")[0],
      "tarama başına tavan: en çok anılanlar önce, kalanı sonraki tura")

_real = pipeline._suggestions_to_translate
pipeline._suggestions_to_translate = lambda: [(_id, "Tavan2", "Baska kaynak metin.", ["tr"])]
with session_scope() as s:
    _id = s.scalar(select(Suggestion.id).where(Suggestion.name == "Tavan2"))
translate_suggestions(FakeLLM())
pipeline._suggestions_to_translate = _real
check("tr" not in row("Tavan2")[0], "gerekçe çeviri sırasında değiştiyse çeviri yazılmaz")
with session_scope() as s:
    for sug in s.scalars(select(Suggestion)).all():
        s.delete(sug)

print("== D: GET /suggestions ==")
client = TestClient(app)
guest = client.post("/auth/login", json={"password": "testpass"}).json()["token"]
r = client.post("/users/register", json={"username": f"u{uuid.uuid4().hex[:8]}", "password": "parola12345",
                                         "email": f"{uuid.uuid4().hex[:12]}@test.local"},
                headers={"Authorization": f"Bearer {guest}"})
assert r.status_code in (200, 201), r.text
headers = {"Authorization": f"Bearer {r.json()['token']}"}
me = client.get("/users/me", headers=headers).json()
with session_scope() as s:
    e = Entity(name="Alphabet", display_name="Alphabet", type="keyword", query="Alphabet", language="en")
    s.add(e)
    s.flush()
    s.add(UserWatchlist(user_id=me["id"], entity_id=e.id))
    sources = [e.id]
add_row("Anthropic", mentions=9, sources=sources, why_texts={"en": EN, "tr": TR})
add_row("Micron", mentions=8, sources=sources, why_texts={"en": EN})
add_row("Intel", mentions=7, sources=sources, why_relevant=OLD_TR)
add_row("Bos", mentions=6, sources=sources)


def whys(query=""):
    res = client.get(f"/suggestions{query}", headers=headers)
    assert res.status_code == 200, res.text
    return {x["name"]: x["why_relevant"] for x in res.json()}


en, tr = whys("?lang=en"), whys("?lang=tr")
check(en["Anthropic"] == EN, "EN arayüz: açıklama EN")
check(tr["Anthropic"] == TR, "TR arayüz: açıklama TR")
check(en["Micron"] == EN and tr["Micron"] is None, "çevirisi olmayan kayıt: TR'de açıklama yok, EN'e düşmez")
check(en["Intel"] is None and tr["Intel"] == OLD_TR, "eski kayıt (Türkçe): EN'de gizli, TR'de görünür")
check(en["Bos"] is None and tr["Bos"] is None, "gerekçesiz kayıt: iki dilde de açıklama yok")
check(whys("?lang=de")["Anthropic"] == EN, "DE kapalı: de → en")
with session_scope() as s:
    s.get(User, me["id"]).language = "en"
check(whys()["Anthropic"] == EN, "?lang yok: kullanıcının kayıtlı dili (en)")
with session_scope() as s:
    s.get(User, me["id"]).language = "tr"
check(whys()["Anthropic"] == TR, "?lang yok: kullanıcının kayıtlı dili (tr)")

print("== E: göç ==")
conn = sqlite3.connect(_db)
conn.execute("ALTER TABLE suggestions DROP COLUMN why_texts")
conn.commit()
conn.close()
init_db()
conn = sqlite3.connect(_db)
cols = {c[1] for c in conn.execute("PRAGMA table_info(suggestions)")}
kept = conn.execute("SELECT why_relevant FROM suggestions WHERE name='Intel'").fetchone()[0]
conn.close()
check("why_texts" in cols, "eski tabloya why_texts eklendi")
check(kept == OLD_TR, "eski gerekçe silinmedi")

print(f"\n{PASS} geçti, {FAIL} başarısız")
sys.exit(1 if FAIL else 0)
