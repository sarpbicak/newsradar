"""Anthropic Claude sarmalayıcısı.

İki kullanım:
- `call_tool(...)`: zorunlu tool-use ile yapılandırılmış JSON al (analiz hattı).
- `stream_chat(...)`: sohbet için token-token streaming (SSE ucu bunu kullanır).

Model: varsayılan `claude-sonnet-4-6` (config'ten). Sonnet 4.6 katı structured
outputs desteklemediği için yapılandırılmış çıktıyı tool_choice ile zorluyoruz.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import anthropic

from ..config import get_settings

logger = logging.getLogger("newsradar.claude")


class ClaudeError(RuntimeError):
    """Claude çağrısı başarısız (ağ, yetki, boş yanıt...)."""


class ModelNotFoundError(ClaudeError):
    """Model adı geçersiz/bulunamadı (404). Genelde yanlış NEWSRADAR_MODEL değeri."""


class MissingAPIKeyError(ClaudeError):
    """ANTHROPIC_API_KEY tanımlı değil."""


class ClaudeClient:
    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        if not settings.claude_available:
            raise MissingAPIKeyError(
                "ANTHROPIC_API_KEY tanımlı değil. .env dosyasına anahtarınızı ekleyin."
            )
        self.model = model or settings.anthropic_model
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def call_tool(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Zorunlu tool-use ile tek bir yapılandırılmış nesne döndürür.

        tool_choice ile modeli verilen aracı çağırmaya zorlar ve tool_use.input
        (doğrulanmış argümanlar) sözlüğünü döndürür.
        """
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.NotFoundError as exc:
            # 404 = model adı geçersiz/erişilemez. Bu, "Claude 0 döndürdü" sessiz
            # arızasının klasik sebebi — AÇIK mesaj ver ve logla, asla yut.
            msg = (f"Claude modeli '{self.model}' bulunamadı (404). NEWSRADAR_MODEL "
                   "değerini geçerli bir model adıyla güncelleyin.")
            logger.error(msg)
            raise ModelNotFoundError(msg) from exc
        except anthropic.APIStatusError as exc:
            msg = f"Claude API hatası ({exc.status_code}): {exc.message}"
            logger.error(msg)
            raise ClaudeError(msg) from exc
        except anthropic.APIConnectionError as exc:
            msg = f"Claude bağlantı hatası: {exc}"
            logger.error(msg)
            raise ClaudeError(msg) from exc

        # KRİTİK: yanıt max_tokens'ta kesildiyse tool_use bloğu bulunsa BİLE input
        # yarım/boş JSON olur → sessizce boş dict dönerdi. Bunu hata say (asla yutma).
        if getattr(resp, "stop_reason", None) == "max_tokens":
            msg = (f"Claude yanıtı max_tokens'ta kesildi (model={self.model}, "
                   f"max_tokens={max_tokens}). Batch'i küçültün (NEWSRADAR_BATCH_SIZE) "
                   "ya da NEWSRADAR_MAX_OUTPUT_TOKENS'ı artırın.")
            logger.error(msg)
            raise ClaudeError(msg)

        for block in resp.content:
            if block.type == "tool_use" and block.name == tool["name"]:
                # input zaten sözlük olarak parse edilmiş halde gelir.
                return dict(block.input)
        # tool_use bloğu yok: model beklenen aracı çağırmadı (boş/uyumsuz yanıt).
        # stop_reason'ı da logla — teşhis için (ör. 'max_tokens', 'end_turn').
        stop = getattr(resp, "stop_reason", "?")
        msg = (f"Claude beklenen tool_use bloğunu döndürmedi (model={self.model}, "
               f"stop_reason={stop}). Model/anahtar/yanıt sorunu olabilir.")
        logger.error(msg)
        raise ClaudeError(msg)

    def stream_chat(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        """Sohbet yanıtını token-token yield eder (SSE için).

        Hata durumunda ClaudeError fırlatır; çağıran bunu SSE 'error' olayına çevirir.
        """
        try:
            with self._client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except anthropic.APIStatusError as exc:
            raise ClaudeError(f"Claude API hatası ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ClaudeError(f"Claude bağlantı hatası: {exc}") from exc


def available() -> bool:
    """ANTHROPIC_API_KEY var mı?"""
    return get_settings().claude_available
