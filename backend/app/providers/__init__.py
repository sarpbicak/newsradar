"""Haber sağlayıcıları: soyut NewsProvider arayüzü + Finnhub/NewsAPI implementasyonları."""

from .base import (
    AnalystProvider,
    AnalystRating,
    AnalystResult,
    FetchedArticle,
    NewsProvider,
    PriceProvider,
    PriceQuote,
    PriceResult,
    ProviderResult,
)
from .registry import (
    get_analyst_provider,
    get_price_provider,
    get_provider_for,
    get_target_provider,
    provider_status,
)

__all__ = [
    "AnalystProvider",
    "AnalystRating",
    "AnalystResult",
    "FetchedArticle",
    "NewsProvider",
    "PriceProvider",
    "PriceQuote",
    "PriceResult",
    "ProviderResult",
    "get_analyst_provider",
    "get_price_provider",
    "get_provider_for",
    "get_target_provider",
    "provider_status",
]
