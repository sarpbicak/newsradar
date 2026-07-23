"""Sağlayıcı kayıt defteri: entity tipine göre doğru NewsProvider'ı seçer."""

from __future__ import annotations

from ..db.models import Entity
from .base import AnalystProvider, NewsProvider, PriceProvider
from .finnhub import FinnhubProvider
from .finnhub_analyst import FinnhubAnalystProvider
from .finnhub_price import FinnhubPriceProvider
from .newsapi import NewsApiProvider

# entity.type -> haber sağlayıcı örneği (tekil).
_PROVIDERS: dict[str, NewsProvider] = {
    "ticker": FinnhubProvider(),
    "keyword": NewsApiProvider(),
}

# Fiyat + analist sağlayıcılar (yalnızca ticker entity'ler için; tekil).
_PRICE_PROVIDER: PriceProvider = FinnhubPriceProvider()
_ANALYST_PROVIDER: AnalystProvider = FinnhubAnalystProvider()


def get_provider_for(entity: Entity) -> NewsProvider | None:
    """Bir entity için haber sağlayıcı döner (tip eşleşmezse None)."""
    return _PROVIDERS.get(entity.type)


def get_price_provider() -> PriceProvider:
    """Fiyat sağlayıcısını döner (ticker entity'ler için)."""
    return _PRICE_PROVIDER


def get_analyst_provider() -> AnalystProvider:
    """Analist verisi sağlayıcısını döner (ticker entity'ler için)."""
    return _ANALYST_PROVIDER


def provider_status() -> dict[str, bool]:
    """UI/uyarı için: her sağlayıcının anahtarı var mı? {'finnhub': bool, 'newsapi': bool}."""
    return {p.name: p.is_available() for p in _PROVIDERS.values()}
