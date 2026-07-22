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
