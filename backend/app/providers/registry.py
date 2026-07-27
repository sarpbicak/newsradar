"""Sağlayıcı kayıt defteri: entity tipine göre doğru NewsProvider'ı seçer."""

from __future__ import annotations

from ..db.models import Entity
from .base import AnalystProvider, NewsProvider, PriceProvider
from .finnhub import FinnhubProvider
from .finnhub_analyst import FinnhubAnalystProvider
from .finnhub_price import FinnhubPriceProvider
from .fmp_analyst import FMPAnalystProvider
from .newsapi import NewsApiProvider

# entity.type -> haber sağlayıcı örneği (tekil).
_PROVIDERS: dict[str, NewsProvider] = {
    "ticker": FinnhubProvider(),
    "keyword": NewsApiProvider(),
}

# Fiyat + analist sağlayıcılar (yalnızca ticker entity'ler için; tekil).
_PRICE_PROVIDER: PriceProvider = FinnhubPriceProvider()
# Tavsiye (al/tut/sat): Finnhub. Hedef fiyat: FMP (Finnhub'da premium). İki kaynak
# ayrı; analyst.py ikisini tek snapshot'ta birleştirir.
_ANALYST_PROVIDER: AnalystProvider = FinnhubAnalystProvider()
_TARGET_PROVIDER: AnalystProvider = FMPAnalystProvider()


def get_provider_for(entity: Entity) -> NewsProvider | None:
    """Bir entity için haber sağlayıcı döner (tip eşleşmezse None)."""
    return _PROVIDERS.get(entity.type)


def get_price_provider() -> PriceProvider:
    """Fiyat sağlayıcısını döner (ticker entity'ler için)."""
    return _PRICE_PROVIDER


def get_analyst_provider() -> AnalystProvider:
    """Analist TAVSİYE (al/tut/sat) sağlayıcısını döner (Finnhub; ticker için)."""
    return _ANALYST_PROVIDER


def get_target_provider() -> AnalystProvider:
    """Analist HEDEF FİYAT sağlayıcısını döner (FMP; ticker için)."""
    return _TARGET_PROVIDER


def provider_status() -> dict[str, bool]:
    """UI/uyarı için: her sağlayıcının anahtarı var mı? {'finnhub', 'newsapi', 'fmp-target'}."""
    status = {p.name: p.is_available() for p in _PROVIDERS.values()}
    status[_TARGET_PROVIDER.name] = _TARGET_PROVIDER.is_available()
    return status
