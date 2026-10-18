"""NewsAPI sağlayıcısı — startup/keyword haberleri (/v2/everything).

Docs: https://newsapi.org/docs/endpoints/everything
Örnek: GET /v2/everything?q="Anthropic"&from=...&sortBy=publishedAt&apiKey=KEY
Not: Ücretsiz katman ~24s gecikmeli ve `from` en fazla ~1 ay geriye gidebilir — v1 için kabul.
"""

from __future__ import annotations

import logging

from datetime import datetime, timezone

import httpx

from ..config import get_settings
from ..db.models import Entity
from ..messages import msg
from .base import FetchedArticle, NewsProvider, ProviderResult

_BASE = "https://newsapi.org/v2"
_PAGE_SIZE = 50


class NewsApiProvider(NewsProvider):
    name = "newsapi"
    entity_type = "keyword"

    def __init__(self) -> None:
        self._settings = get_settings()

    def is_available(self) -> bool:
        return self._settings.newsapi_available

    def fetch(self, entity: Entity, since: datetime) -> ProviderResult:
        if not self.is_available():
            return ProviderResult(
                provider=self.name,
                warning=msg("key_missing", key="NEWSAPI_KEY"),
            )

        query = entity.query.strip()
        # Entity'nin dili NewsAPI `language` parametresine geçer (varsayılan en).
        language = (getattr(entity, "language", None) or "en").strip().lower()
        params = {
            "q": query,
            "from": since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "sortBy": "publishedAt",
            "language": language,
            "pageSize": _PAGE_SIZE,
            "apiKey": self._settings.newsapi_key,
        }
        try:
            resp = httpx.get(f"{_BASE}/everything", params=params, timeout=20.0)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            # NewsAPI hata gövdesinde açıklayıcı mesaj döndürür.
            detail = ""
            try:
                detail = exc.response.json().get("message", "")
            except Exception:
                pass
            logging.getLogger("newsradar.providers").warning(
                "NewsAPI %s ('%s'): %s", exc.response.status_code, query, detail)
            return ProviderResult(
                provider=self.name,
                warning=msg("http_error", source="newsapi", status=exc.response.status_code,
                            symbol=query),
            )
        except (httpx.HTTPError, ValueError) as exc:
            return ProviderResult(
                provider=self.name,
                warning=msg("connection_error", source="newsapi", error=exc),
            )

        if data.get("status") != "ok":
            return ProviderResult(
                provider=self.name,
                warning=msg("newsapi_status", status=data.get("status"),
                            message=data.get("message", "")),
            )

        articles: list[FetchedArticle] = []
        for item in data.get("articles", []):
            url = (item.get("url") or "").strip()
            if not url:
                continue
            published = _parse_iso(item.get("publishedAt"))
            src = (item.get("source") or {}).get("name") or "NewsAPI"
            articles.append(
                FetchedArticle(
                    url=url,
                    title=(item.get("title") or "").strip() or "(başlık yok)",
                    source=str(src).strip(),
                    description=(item.get("description") or "").strip(),
                    image_url=(item.get("urlToImage") or None),
                    published_at=published,
                )
            )
        return ProviderResult(provider=self.name, articles=articles)


def _parse_iso(value: str | None) -> datetime | None:
    """NewsAPI ISO-8601 (Z sonlu) tarihini timezone-aware datetime'a çevirir."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
