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
from .base import PriceProvider, PriceQuote, PriceResult

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
                warning="FINNHUB_API_KEY tanımlı değil — fiyat atlandı.",
            )

        symbol = entity.query.upper().strip()
        params = {"symbol": symbol, "token": self._settings.finnhub_api_key}
        try:
            resp = httpx.get(f"{_BASE}/quote", params=params, timeout=15.0)
            resp.raise_for_status()
            d = resp.json()
        except httpx.HTTPStatusError as exc:
            return PriceResult(
                provider=self.name,
                warning=f"Finnhub fiyat hatası ({exc.response.status_code}) — {symbol} atlandı.",
            )
        except (httpx.HTTPError, ValueError) as exc:
            return PriceResult(
                provider=self.name,
                warning=f"Finnhub fiyat bağlantı/çözümleme hatası: {exc}",
            )

        current = d.get("c")
        # c=0/None → geçersiz sembol ya da ABD dışı (ücretsiz katmanda kapsam yok).
        if not current:
            return PriceResult(
                provider=self.name,
                warning=f"{symbol} için fiyat verisi yok (ABD dışı borsa olabilir).",
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
