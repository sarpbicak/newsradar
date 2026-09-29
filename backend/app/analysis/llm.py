"""LLM sağlayıcı soyutlaması — GERİ DÖNÜLEBİLİR + OpenAI-uyumlu HERHANGİ bir endpoint.

Analiz motoru env ile seçilir: NEWSRADAR_LLM_PROVIDER = anthropic → Claude; başka her
değer (openrouter/nvidia/…) → OpenAICompatProvider. OpenAI-uyumlu sağlayıcı üç env'den
okur: NEWSRADAR_LLM_BASE_URL, NEWSRADAR_LLM_API_KEY, NEWSRADAR_LLM_MODEL. Böylece
OpenRouter, NVIDIA, Together, yerel vLLM… hepsi tek kodla çalışır.

Claude kodu (claude_client.ClaudeClient) SİLİNMEZ; AnthropicProvider onu sarar. Bir
sorun çıkarsa NEWSRADAR_LLM_PROVIDER=anthropic ile tek değişkenle geri dönülür.

Sözleşme:
  call_tool(system, user, tool, max_tokens) -> dict   (zorunlu tool-use → JSON)
  stream_chat(system, messages, max_tokens) -> Iterator[str]

Hata tipi ortak: ClaudeError (pipeline zaten onu yakalıyor). Kesilme/boş yanıt/parse
hatası ASLA sessiz geçilmez — hata fırlatılır.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

from ..config import get_settings
from .claude_client import (
    ClaudeClient,
    ClaudeError,
    MissingAPIKeyError,
    ProviderQuotaError,
    TruncationError,
)

logger = logging.getLogger("newsradar.llm")

_TEMPERATURE = 0.3  # yapılandırılmış çıktı için düşük (tutarlılık)
# Kesilme (max_tokens) sinyali sağlayıcıya göre değişir: finish_reason ya da
# native_finish_reason bunlardan biriyse yanıt yarım kalmıştır.
_TRUNCATION_MARKERS = {"length", "max_tokens", "maxtokens", "max_output_tokens", "token_limit"}


def _is_truncation(finish_reason, native_finish_reason) -> bool:
    vals = {str(finish_reason).lower(), str(native_finish_reason).lower()}
    return bool(vals & _TRUNCATION_MARKERS)


class LLMProvider:
    """Sağlayıcı sözleşmesi."""

    model: str

    def call_tool(self, *, system: str, user: str, tool: dict, max_tokens: int = 4096) -> dict:
        raise NotImplementedError

    def stream_chat(self, *, system: str, messages: list[dict], max_tokens: int = 4096) -> Iterator[str]:
        raise NotImplementedError


# --------------------------- Anthropic (mevcut) --------------------------- #
class AnthropicProvider(LLMProvider):
    """Mevcut ClaudeClient'ı sarar — davranış birebir korunur."""

    def __init__(self, model: str | None = None) -> None:
        self._client = ClaudeClient(model=model)
        self.model = self._client.model

    def call_tool(self, *, system: str, user: str, tool: dict, max_tokens: int = 4096) -> dict:
        return self._client.call_tool(system=system, user=user, tool=tool, max_tokens=max_tokens)

    def stream_chat(self, *, system: str, messages: list[dict], max_tokens: int = 4096) -> Iterator[str]:
        return self._client.stream_chat(system=system, messages=messages, max_tokens=max_tokens)


# ------------------------ Anthropic → OpenAI tool ------------------------ #
def to_openai_tool(anthropic_tool: dict) -> dict:
    """Anthropic tool şemasını OpenAI 'function' formatına sarar (JSON Schema gövdesi aynı)."""
    return {
        "type": "function",
        "function": {
            "name": anthropic_tool["name"],
            "description": anthropic_tool.get("description", ""),
            "parameters": anthropic_tool["input_schema"],
        },
    }


# ----------------- OpenAI-uyumlu genel sağlayıcı (OpenRouter/NVIDIA/…) ----------------- #
class OpenAICompatProvider(LLMProvider):
    """OpenAI-uyumlu HERHANGİ bir endpoint (OpenRouter, NVIDIA, Together, vLLM…).

    base_url / api_key / model doğrudan verilir ya da env'den (config) okunur.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        settings = get_settings()
        base_url = base_url or settings.llm_base_url
        api_key = api_key or settings.llm_api_key
        if not api_key:
            raise MissingAPIKeyError(
                "NEWSRADAR_LLM_API_KEY tanımlı değil (OpenAI-uyumlu endpoint için gerekli). "
                ".env dosyasına ekleyin."
            )
        from openai import OpenAI  # tembel import — anthropic yolunda gerekmez

        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model or settings.llm_model
        self.base_url = base_url
        self.last_usage: dict | None = None  # son çağrının token kullanımı
        # Toplam token/çağrı sayacı (maliyet/ölçüm; thread-güvenli).
        import threading
        self._usage_lock = threading.Lock()
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.call_count = 0

    def _raise_for_openai(self, exc: Exception) -> None:
        """OpenAI istisnalarını anlaşılır ClaudeError'a çevirir (429 = rate limit).

        402/403 = KALICI kota/bakiye hatası (OpenRouter 'Key limit exceeded' / 'Insufficient
        balance') → ProviderQuotaError; pipeline bunu alınca taramayı durdurur (yeniden
        denemez). Böylece tek hata 89 kez tekrarlanmaz."""
        import openai

        if isinstance(exc, openai.APIStatusError) and exc.status_code in (402, 403):
            raise ProviderQuotaError(
                f"Sağlayıcı kota/bakiye hatası ({exc.status_code}): {exc.message}",
                exc.status_code,
            ) from exc
        if isinstance(exc, openai.RateLimitError):
            raise ClaudeError("LLM rate limit (429) — kısa süre bekleyin.") from exc
        if isinstance(exc, openai.APIStatusError):
            raise ClaudeError(f"LLM API hatası ({exc.status_code}): {exc.message}") from exc
        if isinstance(exc, openai.APIConnectionError):
            raise ClaudeError(f"LLM bağlantı hatası: {exc}") from exc
        raise ClaudeError(f"LLM beklenmeyen hata: {exc}") from exc

    def call_tool(self, *, system: str, user: str, tool: dict, max_tokens: int = 4096) -> dict:
        """Zorunlu tool-use ile yapılandırılmış JSON döndürür.

        OpenAI'da tool argümanları JSON *string*'tir (Anthropic'te dict'ti) → parse edilir.
        Kesilme/boş/parse hatası ASLA sessiz geçilmez.
        """
        import openai

        oai_tool = to_openai_tool(tool)
        name = tool["name"]
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=_TEMPERATURE,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                tools=[oai_tool],
                tool_choice={"type": "function", "function": {"name": name}},
            )
        except openai.OpenAIError as exc:
            logger.error("LLM call_tool hatası: %s", exc)
            self._raise_for_openai(exc)

        # Token kullanımını sakla + biriktir (maliyet/ölçüm).
        u = getattr(resp, "usage", None)
        if u is not None:
            pt = getattr(u, "prompt_tokens", 0) or 0
            ct = getattr(u, "completion_tokens", 0) or 0
            self.last_usage = {"prompt_tokens": pt, "completion_tokens": ct,
                               "total_tokens": getattr(u, "total_tokens", pt + ct)}
            with self._usage_lock:
                self.total_prompt_tokens += pt
                self.total_completion_tokens += ct
                self.call_count += 1

        choice = resp.choices[0]
        # OpenRouter bazı sağlayıcılarda kesilmeyi finish_reason yerine
        # native_finish_reason'da bildirir; ikisini de kontrol et.
        fr = getattr(choice, "finish_reason", None)
        nfr = getattr(choice, "native_finish_reason", None)
        truncated = _is_truncation(fr, nfr)

        trunc_msg = (
            f"LLM yanıtı max_tokens'ta kesildi (model={self.model}, max_tokens={max_tokens}, "
            f"finish_reason={fr}/{nfr}). Batch'i küçültün (NEWSRADAR_BATCH_SIZE) ya da "
            "NEWSRADAR_MAX_OUTPUT_TOKENS'ı artırın."
        )

        # KRİTİK: yanıt kesildiyse tool argümanları yarım/bozuk JSON olur → hata (asla yutma).
        if truncated:
            logger.error(trunc_msg)
            raise TruncationError(trunc_msg)

        tool_calls = getattr(choice.message, "tool_calls", None)
        if not tool_calls:
            msg = (f"LLM beklenen tool_call'ı döndürmedi (model={self.model}, "
                   f"finish_reason={fr}/{nfr}). Model/yanıt sorunu olabilir.")
            logger.error(msg)
            raise ClaudeError(msg)

        raw_args = tool_calls[0].function.arguments  # JSON string
        try:
            data = json.loads(raw_args)
        except (json.JSONDecodeError, TypeError) as exc:
            # Parse hatası büyük olasılıkla KESİLME'dir (yarım JSON) — bunu böyle bildir ki
            # otomatik yeniden-dene (batch bölme) tetiklensin.
            logger.error("LLM JSON parse hatası (muhtemelen kesildi): %s | ham son 80: %s",
                         exc, str(raw_args)[-80:])
            raise TruncationError(trunc_msg) from exc
        if not isinstance(data, dict):
            raise ClaudeError("LLM tool argümanları beklenen nesne (dict) değil.")
        return data

    def stream_chat(self, *, system: str, messages: list[dict], max_tokens: int = 4096) -> Iterator[str]:
        import openai

        try:
            stream = self._client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=_TEMPERATURE,
                messages=[{"role": "system", "content": system}, *messages],
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
        except openai.OpenAIError as exc:
            self._raise_for_openai(exc)


# Geriye uyum adı (eski kod/testler NvidiaProvider'ı çağırabilir).
NvidiaProvider = OpenAICompatProvider


# ------------------------------- Fabrika ------------------------------- #
def get_llm_provider(model: str | None = None) -> LLMProvider:
    """Env'e göre sağlayıcı döner. anthropic → Claude; başka her değer → OpenAI-uyumlu
    endpoint (NEWSRADAR_LLM_BASE_URL/API_KEY/MODEL). Varsayılan: OpenAI-uyumlu."""
    provider = get_settings().llm_provider
    if provider == "anthropic":
        return AnthropicProvider(model)
    return OpenAICompatProvider(model=model)  # varsayılan (openrouter/nvidia/…)


def provider_name() -> str:
    return get_settings().llm_provider
