"""Finnhub fiyat sağlayıcısı — anlık kotasyon (/quote).

Docs: https://finnhub.io/docs/api/quote
Örnek: GET /quote?symbol=AAPL&token=KEY
Yanıt: {c: güncel, d: değişim, dp: değişim %, h: gün yüksek, l: gün düşük, pc: önceki kapanış}
Not: Ücretsiz katman yalnızca ABD hisseleri; geçersiz/ABD-dışı sembolde c=0 döner.
"""

from __future__ import annotations

import httpx

from ..config import get_settings
from ..db.models import Entity
from ..messages import msg
from .base import PERMANENT_HTTP, PriceProvider, PriceQuote, PriceResult

_BASE = "https://finnhub.io/api/v1"


class FinnhubPriceProvider(PriceProvider):
    name = "finnhub-price"

    def __init__(self) -> None:
        self._settings = get_settings()

    def is_available(self) -> bool:
        return self._settings.finnhub_available

    def quote(self, entity: Entity) -> PriceResult:
        if not self.is_available():
            return PriceResult(
                provider=self.name,
                warning=msg("key_missing", key="FINNHUB_API_KEY"),
            )

        symbol = entity.query.upper().strip()
        params = {"symbol": symbol, "token": self._settings.finnhub_api_key}
        try:
            resp = httpx.get(f"{_BASE}/quote", params=params, timeout=15.0)
            resp.raise_for_status()
            d = resp.json()
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            return PriceResult(
                provider=self.name,
                warning=msg("http_error", source="finnhub_price", status=code, symbol=symbol),
                expected=code in PERMANENT_HTTP,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return PriceResult(
                provider=self.name,
                warning=msg("connection_error", source="finnhub_price", error=exc),
            )

        current = d.get("c")
        # c=0/None → geçersiz sembol ya da ABD dışı (ücretsiz katmanda kapsam yok).
        if not current:
            return PriceResult(
                provider=self.name,
                warning=msg("no_data", source="finnhub_price", symbol=symbol),
                expected=True,  # ABD dışı borsa / kapsam dışı sembol — kalıcı
            )

        return PriceResult(
            provider=self.name,
            quote=PriceQuote(
                price=float(current),
                change_percent=_num(d.get("dp")),
                previous_close=_num(d.get("pc")),
                day_high=_num(d.get("h")),
                day_low=_num(d.get("l")),
            ),
        )


def _num(v: object) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None
