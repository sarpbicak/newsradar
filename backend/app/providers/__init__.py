"""Haber sağlayıcıları: soyut NewsProvider arayüzü + Finnhub/NewsAPI implementasyonları."""

from .base import FetchedArticle, NewsProvider, ProviderResult
from .registry import get_provider_for, provider_status

__all__ = [
    "FetchedArticle",
    "NewsProvider",
    "ProviderResult",
    "get_provider_for",
    "provider_status",
]
