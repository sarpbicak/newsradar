"""ClaudeClient sessiz-hata korumaları — sahte SDK akışı (gerçek API yok).

Doğrular:
  (A) stop_reason=max_tokens → TruncationError (tool_use bloğu olsa bile)
  (B) 402 / 400 'credit balance' / 403 / kalıcı 429 → ProviderQuotaError, yeniden deneme YOK
  (C) 529 / 500 / geçici 429 / bağlantı → en fazla 2 yeniden deneme, sonra ClaudeError
  (D) geçici hata sonra başarı → sonuç döner
  (E) tool_use yok / input boş → ClaudeError; refusal → ClaudeError
  (F) zorunlu tool_choice yalnızca destekleyen modelde; max_tokens model sınırına kırpılır
  (G) 404 → ModelNotFoundError
  (H) system bloğuna cache_control; sohbette yalnızca sabit önek önbellekli
Çalıştır: python test_claude_client.py
"""
import os
import tempfile
from types import SimpleNamespace

_db = os.path.join(tempfile.gettempdir(), "nr_test_claude_client.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="x", APP_SECRET="y", NEWSRADAR_SCHEDULER="off",
    NEWSRADAR_SEED_ON_START="off", NEWSRADAR_LLM_PROVIDER="anthropic",
    ANTHROPIC_API_KEY="sk-ant-test",
)

import anthropic  # noqa: E402
import httpx2  # noqa: E402

from app.analysis import claude_client as cc  # noqa: E402
from app.analysis.claude_client import (  # noqa: E402
    ClaudeClient, ClaudeError, ModelNotFoundError, ProviderQuotaError, TruncationError,
)

from app.db.database import init_db, session_scope  # noqa: E402
from app.db.models import LlmUsage  # noqa: E402

init_db()
cc.time.sleep = lambda s: None  # testte bekleme yok

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


def status_err(code, etype, message="err"):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx2.Response(code, request=req)
    body = {"type": "error", "error": {"type": etype, "message": message}}
    return anthropic.APIStatusError(message, response=resp, body=body)


def message(stop="tool_use", content=None):
    usage = SimpleNamespace(input_tokens=100, output_tokens=50,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0)
    if content is None:
        content = [SimpleNamespace(type="tool_use", name="t", input={"a": 1})]
    return SimpleNamespace(stop_reason=stop, content=content, usage=usage, stop_details=None)


class FakeStream:
    def __init__(self, outcome):
        self.outcome = outcome
    def __enter__(self):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self
    def __exit__(self, *a):
        return False
    def get_final_message(self):
        return self.outcome


class FakeMessages:
    """outcomes: sırayla döndürülecek mesaj ya da fırlatılacak istisna listesi."""
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
    def stream(self, **kw):
        self.calls.append(kw)
        return FakeStream(self.outcomes.pop(0))


def client_with(outcomes, model="claude-haiku-5-5"):
    c = ClaudeClient(model=model)
    fm = FakeMessages(outcomes)
    c._client = SimpleNamespace(messages=fm)
    return c, fm


TOOL = {"name": "t", "description": "d", "input_schema": {"type": "object"}}


def call(c, mt=1000):
    return c.call_tool(system="s", user="u", tool=TOOL, max_tokens=mt)


def expect(exc_type, fn):
    try:
        fn()
    except exc_type as e:
        return e
    except Exception as e:  # noqa: BLE001
        return f"yanlış istisna: {type(e).__name__}: {e}"
    return "istisna yok"


print("== A: max_tokens → TruncationError ==")
c, fm = client_with([message(stop="max_tokens")])
r = expect(TruncationError, lambda: call(c))
check(isinstance(r, TruncationError), f"tool_use olsa bile TruncationError ({r})")

print("== B: kalıcı kota/bakiye → ProviderQuotaError, yeniden deneme yok ==")
for code, etype, msg in [
    (401, "authentication_error", "invalid x-api-key"),
    (402, "billing_error", "billing"),
    (400, "invalid_request_error", "Your credit balance is too low to access the Anthropic API."),
    (403, "permission_error", "forbidden"),
    (429, "rate_limit_error", "You have reached your specified API usage limits."),
]:
    c, fm = client_with([status_err(code, etype, msg)] * 3)
    r = expect(ProviderQuotaError, lambda: call(c))
    check(isinstance(r, ProviderQuotaError) and len(fm.calls) == 1,
          f"{code} {etype} → ProviderQuotaError, tek çağrı ({len(fm.calls)})")

print("== C: geçici hata → 2 yeniden deneme, sonra ClaudeError ==")
conn_err = anthropic.APIConnectionError(
    request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
for name, e in [("529", status_err(529, "overloaded_error")),
                ("500", status_err(500, "api_error")),
                ("429 geçici", status_err(429, "rate_limit_error", "rate limited")),
                ("SSE overloaded (200)", status_err(200, "overloaded_error")),
                ("bağlantı", conn_err)]:
    c, fm = client_with([e] * 5)
    r = expect(ClaudeError, lambda: call(c))
    check(isinstance(r, ClaudeError) and not isinstance(r, ProviderQuotaError)
          and len(fm.calls) == 3, f"{name}: 3 deneme sonra ClaudeError ({len(fm.calls)})")

print("== D: geçici hata sonra başarı ==")
c, fm = client_with([status_err(529, "overloaded_error"), message()])
check(call(c) == {"a": 1} and len(fm.calls) == 2, "529 → yeniden deneme → sonuç")
check(c.call_count == 1 and c.total_prompt_tokens == 100, "kullanım yalnızca başarılı çağrıda sayıldı")
with session_scope() as s:
    row = s.query(LlmUsage).order_by(LlmUsage.id.desc()).first()
    check(row is not None and row.model == "claude-haiku-5-5" and row.purpose == "article"
          and row.prompt_tokens == 100 and row.completion_tokens == 50
          and abs(row.cost_usd - (100 * 0.10 + 50 * 0.50) / 1e6) < 1e-12,
          "llm_usage satırı: model, amaç, token kalemleri, USD")

print("== E: tool_use yok / boş input / refusal ==")
c, _ = client_with([message(stop="end_turn", content=[SimpleNamespace(type="text", text="hi")])])
check(isinstance(expect(ClaudeError, lambda: call(c)), ClaudeError), "tool_use yok → ClaudeError")
c, _ = client_with([message(content=[SimpleNamespace(type="tool_use", name="t", input={})])])
check(isinstance(expect(ClaudeError, lambda: call(c)), ClaudeError), "boş input → ClaudeError")
c, _ = client_with([message(stop="refusal", content=[])])
r = expect(ClaudeError, lambda: call(c))
check(isinstance(r, ClaudeError) and not isinstance(r, TruncationError), "refusal → ClaudeError")

print("== F: tool_choice + max_tokens kırpma ==")
c, fm = client_with([message()], model="claude-haiku-5-5")
call(c, mt=500_000)
kw = fm.calls[0]
check(kw["tool_choice"] == {"type": "tool", "name": "t"}, "Haiku 5.5: zorunlu tool_choice")
check(kw["max_tokens"] == 128_000, f"max_tokens 500k → model sınırı 128k ({kw['max_tokens']})")
c, fm = client_with([message()], model="claude-sonnet-5-5")
call(c)
kw = fm.calls[0]
check(kw["tool_choice"] == {"type": "auto"}, "Sonnet 5.5: tool_choice=auto (zorunlu 400 verir)")
check("`t` aracını" in kw["messages"][0]["content"], "Sonnet 5.5: araç talimatı user'a eklendi")
check("temperature" not in kw, "temperature gönderilmiyor (5.5 modelleri 400 verir)")
check(kw["tools"][0].get("strict") is True, "Sonnet 5.5: tool strict=true")
c, fm = client_with([message()], model="claude-haiku-5-5")
call(c)
check("strict" not in fm.calls[0]["tools"][0] and "strict" not in TOOL,
      "Haiku 5.5: strict KAPALI (işaretleme sızıntısı gözlendi)")
c, fm = client_with([message()], model="bilinmeyen-model")
call(c)
check("strict" not in fm.calls[0]["tools"][0], "tabloda olmayan model: strict YOK (temkinli)")

print("== H: prompt caching ==")
from app.analysis.prompts import SYSTEM_PROMPT  # noqa: E402
c, fm = client_with([message()])
c.call_tool(system=SYSTEM_PROMPT, user="u", tool=TOOL, max_tokens=100)
sysb = fm.calls[0]["system"]
check(len(sysb) == 1 and sysb[0]["cache_control"] == {"type": "ephemeral"},
      "tool çağrısı: system bloğunda cache_control (tools+system önbellekte)")
chat_sys = f"{SYSTEM_PROMPT}\n\nDİL: tr\n\nBAĞLAM: x"
blocks = cc.system_blocks(chat_sys)
check(len(blocks) == 2 and blocks[0]["text"] == SYSTEM_PROMPT and "cache_control" in blocks[0]
      and "cache_control" not in blocks[1] and blocks[1]["text"].startswith("DİL"),
      "sohbet: yalnızca sabit SYSTEM_PROMPT önbellekli, bağlam ayrı blok")

print("== G: 404 → ModelNotFoundError ==")
c, fm = client_with([status_err(404, "not_found_error", "model: x")])
check(isinstance(expect(ModelNotFoundError, lambda: call(c)), ModelNotFoundError) and len(fm.calls) == 1,
      "404 → ModelNotFoundError, tek çağrı")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
