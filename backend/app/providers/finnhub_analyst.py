"""Finnhub analist sağlayıcısı — al/tut/sat konsensüsü (/stock/recommendation).

Docs: https://finnhub.io/docs/api/recommendation-trends
Örnek: GET /stock/recommendation?symbol=AAPL&token=KEY
Yanıt: [{symbol, period, strongBuy, buy, hold, sell, strongSell}, ...] (en yeni önce)

Not: /stock/price-target (hedef fiyat) ücretsiz katmanda KAPALI (403 premium) —
bu yüzden hedef alanları None döner. recommendation ücretsiz katmanda erişilebilir.
"""

from __future__ import annotations

import httpx

from ..config import get_settings
from ..db.models import Entity
from .base import AnalystProvider, AnalystRating, AnalystResult

_BASE = "https://finnhub.io/api/v1"


class FinnhubAnalystProvider(AnalystProvider):
    name = "finnhub-analyst"

    def __init__(self) -> None:
        self._settings = get_settings()

    def is_available(self) -> bool:
        return self._settings.finnhub_available

    def fetch(self, entity: Entity) -> AnalystResult:
        if not self.is_available():
            return AnalystResult(
                provider=self.name,
                warning="FINNHUB_API_KEY tanımlı değil — analist verisi atlandı.",
            )

        symbol = entity.query.upper().strip()
        params = {"symbol": symbol, "token": self._settings.finnhub_api_key}
        try:
            resp = httpx.get(f"{_BASE}/stock/recommendation", params=params, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            return AnalystResult(
                provider=self.name,
                warning=f"Finnhub analist hatası ({exc.response.status_code}) — {symbol} atlandı.",
            )
        except (httpx.HTTPError, ValueError) as exc:
            return AnalystResult(
                provider=self.name,
                warning=f"Finnhub analist bağlantı/çözümleme hatası: {exc}",
            )

        if not isinstance(data, list) or not data:
            return AnalystResult(
                provider=self.name,
                warning=f"{symbol} için analist verisi yok (ABD dışı borsa olabilir).",
            )

        latest = data[0]  # en yeni dönem
        return AnalystResult(
            provider=self.name,
            rating=AnalystRating(
                strong_buy=int(latest.get("strongBuy") or 0),
                buy=int(latest.get("buy") or 0),
                hold=int(latest.get("hold") or 0),
                sell=int(latest.get("sell") or 0),
                strong_sell=int(latest.get("strongSell") or 0),
                period=latest.get("period"),
                # Hedef fiyatlar premium → None (ileride price-target açılırsa eklenir).
            ),
        )
