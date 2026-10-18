"""Finnhub sağlayıcısı — public ticker haberleri (/company-news).

Docs: https://finnhub.io/docs/api/company-news
Örnek: GET /company-news?symbol=TSLA&from=2024-01-01&to=2024-01-10&token=KEY
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..config import get_settings
from ..db.models import Entity
from ..messages import msg
from .base import FetchedArticle, NewsProvider, ProviderResult

_BASE = "https://finnhub.io/api/v1"


class FinnhubProvider(NewsProvider):
    name = "finnhub"
    entity_type = "ticker"

    def __init__(self) -> None:
        self._settings = get_settings()

    def is_available(self) -> bool:
        return self._settings.finnhub_available

    def fetch(self, entity: Entity, since: datetime) -> ProviderResult:
        if not self.is_available():
            return ProviderResult(
                provider=self.name,
                warning=msg("key_missing", key="FINNHUB_API_KEY"),
            )

        symbol = entity.query.upper().strip()
        params = {
            "symbol": symbol,
            "from": since.astimezone(timezone.utc).strftime("%Y-%m-%d"),
            "to": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "token": self._settings.finnhub_api_key,
        }
        try:
            resp = httpx.get(f"{_BASE}/company-news", params=params, timeout=20.0)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            return ProviderResult(
                provider=self.name,
                warning=msg("http_error", source="finnhub_news",
                            status=exc.response.status_code, symbol=symbol),
            )
        except (httpx.HTTPError, ValueError) as exc:
            return ProviderResult(
                provider=self.name,
                warning=msg("connection_error", source="finnhub_news", error=exc),
            )

        if not isinstance(data, list):
            return ProviderResult(
                provider=self.name,
                warning=msg("bad_response", source="finnhub_news", symbol=symbol),
            )

        articles: list[FetchedArticle] = []
        for item in data:
            url = (item.get("url") or "").strip()
            if not url:
                continue
            ts = item.get("datetime")  # unix saniye
            published = (
                datetime.fromtimestamp(ts, tz=timezone.utc)
                if isinstance(ts, (int, float)) and ts > 0
                else None
            )
            articles.append(
                FetchedArticle(
                    url=url,
                    title=(item.get("headline") or "").strip() or "(başlık yok)",
                    source=(item.get("source") or "Finnhub").strip(),
                    description=(item.get("summary") or "").strip(),
                    image_url=(item.get("image") or None),
                    published_at=published,
                )
            )
        return ProviderResult(provider=self.name, articles=articles)
