"""Soyut haber sağlayıcı arayüzü.

Kaynakları sonradan takas edebilmek için tüm çekme mantığı NewsProvider arkasına
gizlenir. Yeni bir kaynak eklemek = yeni bir NewsProvider alt sınıfı + registry'ye kaydı.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from ..db.models import Entity


@dataclass
class FetchedArticle:
    """Bir sağlayıcıdan gelen ham haber (henüz DB'ye yazılmamış, analiz edilmemiş)."""

    url: str
    title: str
    source: str = ""
    description: str = ""
    image_url: str | None = None
    published_at: datetime | None = None


@dataclass
class ProviderResult:
    """Bir çekme işleminin sonucu: makaleler + (varsa) kullanıcıya gösterilecek uyarı."""

    provider: str
    articles: list[FetchedArticle] = field(default_factory=list)
    warning: str | None = None  # örn. "anahtar yok" ya da "API hatası"


class NewsProvider(ABC):
    """Bir haber kaynağının sözleşmesi."""

    #: İnsan-okur ad (loglar/UI için) ve DB'ye yazılan `provider` etiketi.
    name: str = "base"

    #: Bu sağlayıcının hangi entity tipini beslediği ("ticker" | "keyword").
    entity_type: str = ""

    @abstractmethod
    def is_available(self) -> bool:
        """Gerekli API anahtarı var mı? Yoksa registry bu sağlayıcıyı atlar."""
        raise NotImplementedError

    @abstractmethod
    def fetch(self, entity: Entity, since: datetime) -> ProviderResult:
        """`since` zamanından bu yana `entity` ile ilgili haberleri çeker.

        Ağ/anahtar hatalarını yakalayıp ProviderResult.warning ile döndürmeli —
        istisna fırlatmamalı ki hat tek bir kaynak hatasında çökmesin.
        """
        raise NotImplementedError


# --------------------------------------------------------------------------- #
#  Fiyat sağlayıcı arayüzü (ayrı sözleşme; ileride başka sağlayıcı eklenebilir)
#  ÖNEMLİ: Fiyat verisi TAHMİN için değil — haberin fiyata yansıyıp yansımadığını
#  görmek içindir. Hedef fiyat/teknik sinyal üretilmez.
# --------------------------------------------------------------------------- #
@dataclass
class PriceQuote:
    """Bir varlığın anlık fiyat görüntüsü (snapshot)."""

    price: float
    change_percent: float | None = None   # günlük %
    previous_close: float | None = None
    day_high: float | None = None
    day_low: float | None = None


@dataclass
class PriceResult:
    """Fiyat çekme sonucu: quote (varsa) + kullanıcıya gösterilecek uyarı (varsa)."""

    provider: str
    quote: PriceQuote | None = None
    warning: str | None = None


class PriceProvider(ABC):
    """Bir fiyat kaynağının sözleşmesi. Yalnızca `type=ticker` entity'ler için kullanılır."""

    name: str = "base-price"

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def quote(self, entity: Entity) -> PriceResult:
        """Entity için anlık fiyat döner. Hata/anahtar yoksa warning ile döner, çökmez."""
        raise NotImplementedError
