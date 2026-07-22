"""Sağlayıcı kayıt defteri: entity tipine göre doğru NewsProvider'ı seçer."""

from __future__ import annotations

from ..db.models import Entity
from .base import NewsProvider
from .finnhub import FinnhubProvider
from .newsapi import NewsApiProvider

# entity.type -> sağlayıcı örneği (tekil).
_PROVIDERS: dict[str, NewsProvider] = {
    "ticker": FinnhubProvider(),
    "keyword": NewsApiProvider(),
}


def get_provider_for(entity: Entity) -> NewsProvider | None:
    """Bir entity için sağlayıcı döner (tip eşleşmezse None)."""
    return _PROVIDERS.get(entity.type)


def provider_status() -> dict[str, bool]:
    """UI/uyarı için: her sağlayıcının anahtarı var mı? {'finnhub': bool, 'newsapi': bool}."""
    return {p.name: p.is_available() for p in _PROVIDERS.values()}
