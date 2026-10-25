"""Sağlayıcı kayıt defteri: entity'ye göre haber / fiyat / analist kaynağını seçer.

Haber: ABD hissesi → Finnhub company-news; anahtar kelime ve ABD dışı hisse → GDELT
(NEWSRADAR_NEWSAPI_ENABLED=on ise anahtar kelime NewsAPI). Fiyat ve analist: pazar başına
yuva — ABD için mevcut kaynaklar (Finnhub fiyat/tavsiye, FMP hedef); diğer pazarlarda yuva BOŞ
(ücretli kaynak eklenmedi) → bu şirketlerde "veri yok". Yeni kaynak = INTL_* yuvasına bir
PriceProvider/AnalystProvider (pazar kodu → sağlayıcı).
"""

from __future__ import annotations

from ..config import get_settings
from ..db.models import Entity
from ..markets import market_of
from .base import AnalystProvider, NewsProvider, PriceProvider
from .finnhub import FinnhubProvider
from .finnhub_analyst import FinnhubAnalystProvider
from .finnhub_price import FinnhubPriceProvider
from .fmp_analyst import FMPAnalystProvider
from .gdelt import GdeltProvider
from .newsapi import NewsApiProvider

_FINNHUB_NEWS = FinnhubProvider()
_GDELT = GdeltProvider()
_NEWSAPI = NewsApiProvider()

_PRICE_PROVIDER: PriceProvider = FinnhubPriceProvider()
# Tavsiye (al/tut/sat): Finnhub. Hedef fiyat: FMP (Finnhub'da premium). analyst.py birleştirir.
_ANALYST_PROVIDER: AnalystProvider = FinnhubAnalystProvider()
_TARGET_PROVIDER: AnalystProvider = FMPAnalystProvider()

# ABD dışı pazarlar için BOŞ yuvalar: {pazar kodu ("DE", "IS", "T") ya da "*": sağlayıcı}.
# Ücretli bir dünya geneli kaynak seçilirse buraya eklenir; yoksa fiyat/analist "veri yok".
INTL_PRICE_PROVIDERS: dict[str, PriceProvider] = {}
INTL_ANALYST_PROVIDERS: dict[str, AnalystProvider] = {}


def get_provider_for(entity: Entity) -> NewsProvider | None:
    """Bir entity için haber sağlayıcı (tip eşleşmezse None)."""
    if entity.type == "ticker":
        return _FINNHUB_NEWS if market_of(entity.query).is_us else _GDELT
    if entity.type == "keyword":
        return _NEWSAPI if get_settings().newsapi_enabled else _GDELT
    return None


def _intl(slots: dict, entity: Entity):
    code = market_of(entity.query).code
    return slots.get(code) or slots.get("*")


def price_provider_for(entity: Entity) -> PriceProvider | None:
    """Hissenin pazarına göre fiyat sağlayıcısı; ABD dışında yuva boşsa None ("veri yok")."""
    if entity.type != "ticker":
        return None
    return _PRICE_PROVIDER if market_of(entity.query).is_us else _intl(INTL_PRICE_PROVIDERS, entity)


def analyst_supported(entity: Entity) -> bool:
    """Analist verisi (tavsiye + hedef) bu pazarda var mı? ABD dışında yuva boşsa hayır."""
    if entity.type != "ticker":
        return False
    return market_of(entity.query).is_us or _intl(INTL_ANALYST_PROVIDERS, entity) is not None


def get_price_provider() -> PriceProvider:
    """ABD fiyat sağlayıcısı (Finnhub)."""
    return _PRICE_PROVIDER


def get_analyst_provider() -> AnalystProvider:
    """Analist TAVSİYE (al/tut/sat) sağlayıcısı (Finnhub; ABD)."""
    return _ANALYST_PROVIDER


def get_target_provider() -> AnalystProvider:
    """Analist HEDEF FİYAT sağlayıcısı (FMP; ABD)."""
    return _TARGET_PROVIDER


def provider_status() -> dict[str, bool]:
    """UI/uyarı için: sağlayıcıların anahtarı var mı? NewsAPI yalnızca açıkken listelenir."""
    status = {_FINNHUB_NEWS.name: _FINNHUB_NEWS.is_available(), _GDELT.name: True}
    if get_settings().newsapi_enabled:
        status[_NEWSAPI.name] = _NEWSAPI.is_available()
    status[_TARGET_PROVIDER.name] = _TARGET_PROVIDER.is_available()
    return status
