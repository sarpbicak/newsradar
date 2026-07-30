"""LLM sağlayıcı soyutlaması — GERİ DÖNÜLEBİLİR.

Analiz motoru env ile seçilir: NEWSRADAR_LLM_PROVIDER = nvidia (varsayılan) | anthropic.
Claude kodu (claude_client.ClaudeClient) SİLİNMEZ; AnthropicProvider onu sarar. Bir
sorun çıkarsa NEWSRADAR_LLM_PROVIDER=anthropic ile tek değişkenle geri dönülür.

Her iki sağlayıcı da aynı sözleşmeyi sunar:
  call_tool(system, user, tool, max_tokens) -> dict   (zorunlu tool-use → JSON)
  stream_chat(system, messages, max_tokens) -> Iterator[str]

Hata tipi ortak: ClaudeError (pipeline zaten onu yakalıyor). Kesilme/boş yanıt/parse
hatası ASLA sessiz geçilmez — hata fırlatılır.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from ..config import get_settings
from .claude_client import ClaudeClient, ClaudeError, MissingAPIKeyError

logger = logging.getLogger("newsradar.llm")

_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
_TEMPERATURE = 0.3  # yapılandırılmış çıktı için düşük (tutarlılık)


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


# --------------------------- NVIDIA (yeni) --------------------------- #
class NvidiaProvider(LLMProvider):
    """NVIDIA'da barındırılan Llama (OpenAI-uyumlu API). Ücretsiz endpoint."""

    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        if not settings.nvidia_api_key:
            raise MissingAPIKeyError(
                "NVIDIA_API_KEY tanımlı değil. .env dosyasına anahtarınızı ekleyin."
            )
        from openai import OpenAI  # tembel import — anthropic yolunda gerekmez

        self._client = OpenAI(base_url=_NVIDIA_BASE_URL, api_key=settings.nvidia_api_key)
        self.model = model or settings.llm_model

    def _raise_for_openai(self, exc: Exception) -> None:
        """OpenAI istisnalarını anlaşılır ClaudeError'a çevirir (429 = rate limit)."""
        import openai

        if isinstance(exc, openai.RateLimitError):
            raise ClaudeError("NVIDIA rate limit (429) — kısa süre bekleyin.") from exc
        if isinstance(exc, openai.APIStatusError):
            raise ClaudeError(f"NVIDIA API hatası ({exc.status_code}): {exc.message}") from exc
        if isinstance(exc, openai.APIConnectionError):
            raise ClaudeError(f"NVIDIA bağlantı hatası: {exc}") from exc
        raise ClaudeError(f"NVIDIA beklenmeyen hata: {exc}") from exc

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
            logger.error("NVIDIA call_tool hatası: %s", exc)
            self._raise_for_openai(exc)

        choice = resp.choices[0]

        # KRİTİK: yanıt max_tokens'ta kesildiyse tool argümanları yarım/bozuk JSON olur →
        # sessizce boş sayılırdı. Hata fırlat (asla yutma).
        if choice.finish_reason == "length":
            msg = (f"NVIDIA yanıtı max_tokens'ta kesildi (model={self.model}, "
                   f"max_tokens={max_tokens}). Batch'i küçültün (NEWSRADAR_BATCH_SIZE) "
                   "ya da NEWSRADAR_MAX_OUTPUT_TOKENS'ı artırın.")
            logger.error(msg)
            raise ClaudeError(msg)

        tool_calls = getattr(choice.message, "tool_calls", None)
        if not tool_calls:
            msg = (f"NVIDIA beklenen tool_call'ı döndürmedi (model={self.model}, "
                   f"finish_reason={choice.finish_reason}). Model/yanıt sorunu olabilir.")
            logger.error(msg)
            raise ClaudeError(msg)

        raw_args = tool_calls[0].function.arguments  # JSON string
        try:
            data = json.loads(raw_args)
        except (json.JSONDecodeError, TypeError) as exc:
            msg = f"NVIDIA tool argümanları JSON parse edilemedi: {exc}"
            logger.error("%s | ham: %s", msg, str(raw_args)[:200])
            raise ClaudeError(msg) from exc
        if not isinstance(data, dict):
            raise ClaudeError("NVIDIA tool argümanları beklenen nesne (dict) değil.")
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


# ------------------------------- Fabrika ------------------------------- #
def get_llm_provider(model: str | None = None) -> LLMProvider:
    """Env'e göre sağlayıcı döner. Varsayılan: nvidia. Geri dönüş: anthropic."""
    provider = get_settings().llm_provider
    if provider == "anthropic":
        return AnthropicProvider(model)
    return NvidiaProvider(model)  # varsayılan


def provider_name() -> str:
    return get_settings().llm_provider
