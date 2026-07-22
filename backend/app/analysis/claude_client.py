"""Anthropic Claude sarmalayıcısı.

İki kullanım:
- `call_tool(...)`: zorunlu tool-use ile yapılandırılmış JSON al (analiz hattı).
- `stream_chat(...)`: sohbet için token-token streaming (SSE ucu bunu kullanır).

Model: varsayılan `claude-sonnet-4-6` (config'ten). Sonnet 4.6 katı structured
outputs desteklemediği için yapılandırılmış çıktıyı tool_choice ile zorluyoruz.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import anthropic

from ..config import get_settings


class ClaudeError(RuntimeError):
    """Claude çağrısı başarısız (ağ, yetki, boş yanıt...)."""


class MissingAPIKeyError(ClaudeError):
    """ANTHROPIC_API_KEY tanımlı değil."""


class ClaudeClient:
    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        if not settings.claude_available:
            raise MissingAPIKeyError(
                "ANTHROPIC_API_KEY tanımlı değil. .env dosyasına anahtarınızı ekleyin."
            )
        self.model = model or settings.model
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
        except anthropic.APIStatusError as exc:
            raise ClaudeError(f"Claude API hatası ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ClaudeError(f"Claude bağlantı hatası: {exc}") from exc

        for block in resp.content:
            if block.type == "tool_use" and block.name == tool["name"]:
                # input zaten sözlük olarak parse edilmiş halde gelir.
                return dict(block.input)
        raise ClaudeError("Claude beklenen tool_use bloğunu döndürmedi.")

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
