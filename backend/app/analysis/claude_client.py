"""Anthropic Claude sarmalayıcısı.

İki kullanım:
- `call_tool(...)`: tool-use ile yapılandırılmış JSON al (analiz hattı).
- `stream_chat(...)`: sohbet için token-token streaming (SSE ucu bunu kullanır).

Model kullanım amacına göre config'ten gelir (purpose: article | assessment | chat →
NEWSRADAR_ARTICLE_MODEL / NEWSRADAR_ASSESSMENT_MODEL / NEWSRADAR_CHAT_MODEL). Model başına
sınırlar/davranış farkları: model_specs.py.

Sessiz-hata korumaları (OpenAI-uyumlu yol ile AYNI sözleşme):
- stop_reason == "max_tokens" → TruncationError (tool_use bloğu olsa bile).
- Bakiye/kredi/kalıcı yetki-kota (401 geçersiz anahtar, 402, kredi yetersiz, 403, kalıcı
  429) → ProviderQuotaError.
- Geçici hatalar (529 overloaded, 5xx, geçici 429, bağlantı) → üstel geri çekilmeyle en
  fazla MAX_RETRIES yeniden deneme. SDK'nın kendi yeniden denemesi kapalı (max_retries=0)
  ki kalıcı 429 boşuna tekrarlanmasın.
- tool_use yok / input boş → ClaudeError.

Prompt caching: tools + SYSTEM_PROMPT her çağrıda aynı → system bloğuna cache_control
(5 dk ephemeral) konur. Render sırası tools → system → messages olduğundan bu tek
breakpoint tool şemasını da kapsar. Değişken kısım (sohbet bağlamı, makale listesi)
breakpoint'ten SONRA gelir. Minimum önbelleklenebilir önek Haiku/Sonnet 5.5'te 512 token;
cache_creation_input_tokens / cache_read_input_tokens kullanım kaydına ayrı yazılır.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

import anthropic

from ..config import get_settings
from .model_specs import spec_for
from .prompts import SYSTEM_PROMPT

logger = logging.getLogger("newsradar.claude")

T = TypeVar("T")

MAX_RETRIES = 2            # geçici hatada en fazla 2 yeniden deneme (toplam 3 deneme)
_BACKOFF_BASE_S = 1.0      # 1s, 2s (+ jitter); retry-after başlığı varsa o kullanılır
_BACKOFF_CAP_S = 30.0
_CHAT_EFFORT = "low"       # sohbet: kısa, hızlı yanıt (thinking gecikmesini azaltır)

# Kalıcı kota/bakiye/harcama sınırı mesaj işaretleri (429/400 gövdesinde).
_QUOTA_MARKERS = ("credit balance", "billing", "spend limit", "usage limit", "quota")


class ClaudeError(RuntimeError):
    """Claude çağrısı başarısız (ağ, yetki, boş yanıt...)."""


class ModelNotFoundError(ClaudeError):
    """Model adı geçersiz/bulunamadı (404). Genelde yanlış NEWSRADAR_*_MODEL değeri."""


class MissingAPIKeyError(ClaudeError):
    """ANTHROPIC_API_KEY tanımlı değil."""


class ProviderQuotaError(ClaudeError):
    """Sağlayıcının KALICI kota/bakiye hatası (ör. Anthropic 402 billing, 'credit balance
    is too low', kalıcı 403/429; OpenRouter 403 'Key limit exceeded'). Yeniden denemek
    anlamsız — aynı hata döner ve token/uyarı biriktirir. Pipeline bunu alınca o yenilemenin
    TÜM kalan LLM çağrılarını durdurur ve TEK bir uyarı verir (89 aynı uyarı yerine).
    status_code teşhis/sağlık paneli için taşınır."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TruncationError(ClaudeError):
    """Yanıt max_tokens'ta kesildi (yarım/bozuk JSON). Batch bölünüp yeniden denenebilir.

    ClaudeError'ın ALT tipi: pipeline yalnızca BUNU bölerek yeniden dener; diğer
    ClaudeError'lar (rate limit, bağlantı, API) bölünmez (uyar + devam)."""


# ------------------------------ Hata sınıflama ------------------------------ #
def _error_type(exc: anthropic.APIStatusError) -> str:
    """API gövdesindeki error.type ('overloaded_error', 'billing_error', ...)."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("type") or "")
    return ""


def classify_error(exc: Exception) -> str:
    """'quota' | 'not_found' | 'transient' | 'fatal'.

    Akış ortasındaki (SSE) hatalar HTTP 200 ile gelir; bu yüzden status yanında gövdedeki
    error.type da okunur (ör. overloaded_error → geçici)."""
    if isinstance(exc, anthropic.APIConnectionError):  # zaman aşımı dahil
        return "transient"
    if not isinstance(exc, anthropic.APIStatusError):
        return "fatal"
    status = exc.status_code
    etype = _error_type(exc)
    msg = str(getattr(exc, "message", "") or exc).lower()
    if status == 404 or etype == "not_found_error":
        return "not_found"
    if status == 401 or etype == "authentication_error":
        return "quota"  # geçersiz/iptal anahtar: kalıcı — her çağrı aynı 401'i alır
    if status == 402 or etype == "billing_error":
        return "quota"
    if status == 403 or etype == "permission_error":
        return "quota"
    if any(m in msg for m in _QUOTA_MARKERS) and status in (400, 429):
        return "quota"  # 'credit balance is too low' (400) / harcama sınırı (429)
    if status == 429 or etype == "rate_limit_error":
        return "transient"
    if status == 529 or etype in ("overloaded_error", "api_error") or status >= 500:
        return "transient"
    return "fatal"


def system_blocks(system: str) -> list[dict[str, Any]]:
    """System prompt'u cache breakpoint'li bloklara böler.

    SYSTEM_PROMPT ile başlıyorsa (sohbet: SYSTEM_PROMPT + dil yönergesi + bağlam) yalnızca
    sabit SYSTEM_PROMPT önbelleğe alınır, gerisi ayrı (önbelleksiz) blok olur — böylece her
    entity/dil için ortak önek tekrar kullanılır. Aksi halde tüm metin tek önbellekli blok."""
    cache = {"type": "ephemeral"}
    if system.startswith(SYSTEM_PROMPT) and len(system) > len(SYSTEM_PROMPT):
        rest = system[len(SYSTEM_PROMPT):].lstrip("\n")
        blocks = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": cache}]
        if rest:
            blocks.append({"type": "text", "text": rest})
        return blocks
    return [{"type": "text", "text": system, "cache_control": cache}]


def _retry_delay(exc: Exception, attempt: int) -> float:
    """retry-after başlığı (varsa) ya da üstel geri çekilme + jitter."""
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None)
    if headers is not None:
        try:
            ra = float(headers.get("retry-after", ""))
            if ra > 0:
                return min(ra, _BACKOFF_CAP_S)
        except (TypeError, ValueError):
            pass
    return min(_BACKOFF_BASE_S * (2 ** attempt) + random.uniform(0, 0.5), _BACKOFF_CAP_S)


class ClaudeClient:
    def __init__(self, model: str | None = None, purpose: str = "article") -> None:
        settings = get_settings()
        if not settings.claude_available:
            raise MissingAPIKeyError(
                "ANTHROPIC_API_KEY tanımlı değil. .env dosyasına anahtarınızı ekleyin."
            )
        self.purpose = purpose
        self.model = model or settings.model_for(purpose)
        self.spec = spec_for(self.model)
        # max_retries=0: yeniden denemeyi biz yönetiyoruz (kalıcı 429'u ayırt etmek için).
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=0)
        # Token/çağrı sayaçları (thread-güvenli; pipeline eşzamanlı çağırır).
        self._usage_lock = threading.Lock()
        self.total_prompt_tokens = 0       # input + cache write + cache read
        self.total_completion_tokens = 0
        self.call_count = 0
        self.total_cost_usd = 0.0
        self.last_usage: dict | None = None

    # ------------------------------ yardımcılar ------------------------------ #
    def _clamp_max_tokens(self, max_tokens: int) -> int:
        cap = self.spec.max_output_tokens
        if max_tokens > cap:
            logger.info("max_tokens %d → %d (model=%s çıktı sınırı)", max_tokens, cap, self.model)
            return cap
        return max_tokens

    def _raise_mapped(self, exc: Exception, kind: str) -> None:
        status = getattr(exc, "status_code", None)
        detail = getattr(exc, "message", None) or str(exc)
        if kind == "not_found":
            # 404 = model adı geçersiz/erişilemez. "Claude 0 döndürdü" sessiz arızasının
            # klasik sebebi — AÇIK mesaj ver ve logla, asla yut.
            msg = (f"Claude modeli '{self.model}' bulunamadı (404). NEWSRADAR_"
                   f"{self.purpose.upper()}_MODEL değerini geçerli bir model adıyla güncelleyin.")
            logger.error(msg)
            raise ModelNotFoundError(msg) from exc
        if kind == "quota":
            if status == 401:
                msg = f"Claude kimlik doğrulama hatası (401) — ANTHROPIC_API_KEY geçersiz: {detail}"
            else:
                msg = f"Sağlayıcı kota/bakiye hatası ({status}): {detail}"
            logger.error(msg)
            raise ProviderQuotaError(msg, status) from exc
        if isinstance(exc, anthropic.APIConnectionError):
            msg = f"Claude bağlantı hatası: {exc}"
        else:
            msg = f"Claude API hatası ({status}): {detail}"
        logger.error(msg)
        raise ClaudeError(msg) from exc

    def _with_retries(self, fn: Callable[[], T]) -> T:
        """fn'i çalıştırır; geçici hatada üstel geri çekilmeyle en fazla MAX_RETRIES kez
        yeniden dener. Kalıcı hatalar (kota/404/400) anında eşlenmiş hataya çevrilir."""
        for attempt in range(MAX_RETRIES + 1):
            try:
                return fn()
            except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
                kind = classify_error(exc)
                if kind == "transient" and attempt < MAX_RETRIES:
                    delay = _retry_delay(exc, attempt)
                    logger.warning("Claude geçici hata (%s) — %.1fs sonra yeniden deneme %d/%d",
                                   getattr(exc, "status_code", type(exc).__name__),
                                   delay, attempt + 1, MAX_RETRIES)
                    time.sleep(delay)
                    continue
                self._raise_mapped(exc, kind)
        raise AssertionError("unreachable")  # pragma: no cover

    def _note_usage(self, resp: Any) -> None:
        u = getattr(resp, "usage", None)
        if u is None:
            return
        inp = getattr(u, "input_tokens", 0) or 0
        cw = getattr(u, "cache_creation_input_tokens", 0) or 0
        cr = getattr(u, "cache_read_input_tokens", 0) or 0
        out = getattr(u, "output_tokens", 0) or 0
        # Çağrı başına kalıcı kayıt (model, token kalemleri, USD) — günlük bütçe buradan.
        from ..budget import record_llm_call
        cost = record_llm_call(self.model, self.purpose, inp, out, cw, cr)
        self.last_usage = {"input_tokens": inp, "cache_creation_input_tokens": cw,
                           "cache_read_input_tokens": cr, "output_tokens": out,
                           "cost_usd": cost}
        with self._usage_lock:
            self.total_prompt_tokens += inp + cw + cr
            self.total_completion_tokens += out
            self.call_count += 1
            self.total_cost_usd += cost

    # ------------------------------ tool çağrısı ------------------------------ #
    def call_tool(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Tool-use ile tek bir yapılandırılmış nesne döndürür (tool_use.input sözlüğü).

        Zorunlu tool_choice destekleyen modelde {"type": "tool"}; desteklemeyende (Sonnet
        5.5) auto + açık talimat. Her iki yolda tool_use yoksa/boşsa hata fırlatılır.
        Akış (stream) kullanılır: büyük max_tokens (kesilme kurtarmasında 2×) akışsız
        istekte SDK zaman aşımı korumasına takılır.
        """
        name = tool["name"]
        max_tokens = self._clamp_max_tokens(max_tokens)
        user_content = user
        kwargs: dict[str, Any] = {}
        if self.spec.forced_tool_choice:
            kwargs["tool_choice"] = {"type": "tool", "name": name}
        else:
            kwargs["tool_choice"] = {"type": "auto"}
            user_content = (f"{user}\n\nYanıtını YALNIZCA `{name}` aracını çağırarak ver; "
                            "araç dışında metin yazma.")
        if self.spec.tool_effort:
            kwargs["output_config"] = {"effort": self.spec.tool_effort}

        def _do():
            with self._client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                system=system_blocks(system),
                tools=[tool],
                messages=[{"role": "user", "content": user_content}],
                **kwargs,
            ) as stream:
                return stream.get_final_message()

        resp = self._with_retries(_do)
        self._note_usage(resp)
        stop = getattr(resp, "stop_reason", None)

        # KRİTİK: yanıt max_tokens'ta kesildiyse tool_use bloğu bulunsa BİLE input
        # yarım/boş JSON olur → sessizce boş dict dönerdi. Bunu hata say (asla yutma).
        if stop == "max_tokens":
            msg = (f"Claude yanıtı max_tokens'ta kesildi (model={self.model}, "
                   f"max_tokens={max_tokens}). Batch'i küçültün (NEWSRADAR_BATCH_SIZE) "
                   "ya da NEWSRADAR_MAX_OUTPUT_TOKENS'ı artırın.")
            logger.error(msg)
            raise TruncationError(msg)
        if stop == "refusal":
            details = getattr(resp, "stop_details", None)
            cat = getattr(details, "category", None) if details else None
            msg = f"Claude isteği reddetti (model={self.model}, kategori={cat})."
            logger.error(msg)
            raise ClaudeError(msg)

        for block in resp.content:
            if block.type == "tool_use" and block.name == name:
                data = block.input
                if not isinstance(data, dict) or not data:
                    msg = (f"Claude tool_use input'u boş/geçersiz (model={self.model}, "
                           f"stop_reason={stop}).")
                    logger.error(msg)
                    raise ClaudeError(msg)
                return dict(data)
        # tool_use bloğu yok: model beklenen aracı çağırmadı (boş/uyumsuz yanıt).
        msg = (f"Claude beklenen tool_use bloğunu döndürmedi (model={self.model}, "
               f"stop_reason={stop}). Model/anahtar/yanıt sorunu olabilir.")
        logger.error(msg)
        raise ClaudeError(msg)

    def count_prompt_tokens(self, *, system: str, user: str, tool: dict[str, Any]) -> int:
        """call_tool ile aynı prompt'un girdi token sayısı (count_tokens ucu, ücretsiz).
        100k fiyat bariyeri kontrolü için. tool_choice gönderilmez (sayıyı etkilemez)."""
        def _do():
            return self._client.messages.count_tokens(
                model=self.model,
                system=system_blocks(system),
                tools=[tool],
                messages=[{"role": "user", "content": user}],
            )
        return int(self._with_retries(_do).input_tokens)

    # --------------------------------- sohbet --------------------------------- #
    def stream_chat(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        """Sohbet yanıtını token-token yield eder (SSE için).

        Geçici hatada yeniden deneme YALNIZCA henüz metin gönderilmediyse yapılır (aksi
        halde kullanıcı aynı metni iki kez görür). Hata → ClaudeError (çağıran SSE 'error'
        olayına çevirir); kota → ProviderQuotaError (ClaudeError alt tipi).
        """
        max_tokens = self._clamp_max_tokens(max_tokens)
        for attempt in range(MAX_RETRIES + 1):
            yielded = False
            try:
                with self._client.messages.stream(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_blocks(system),
                    messages=messages,
                    output_config={"effort": _CHAT_EFFORT},
                ) as stream:
                    for text in stream.text_stream:
                        yielded = True
                        yield text
                    self._note_usage(stream.get_final_message())
                return
            except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
                kind = classify_error(exc)
                if kind == "transient" and not yielded and attempt < MAX_RETRIES:
                    time.sleep(_retry_delay(exc, attempt))
                    continue
                self._raise_mapped(exc, kind)


def available() -> bool:
    """ANTHROPIC_API_KEY var mı?"""
    return get_settings().claude_available
