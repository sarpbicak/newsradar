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


# Kalıcı HTTP durumları: anahtar geçersiz (401) ya da uç ücretsiz katmanın dışında
# (402/403). Tekrar denemek aynı sonucu verir → ProviderResult.expected=True.
PERMANENT_HTTP = frozenset({401, 402, 403})


@dataclass
class ProviderResult:
    """Bir çekme işleminin sonucu: makaleler + (varsa) kullanıcıya gösterilecek uyarı."""

    provider: str
    articles: list[FetchedArticle] = field(default_factory=list)
    # Kullanıcıya gösterilecek uyarı: app.messages.msg(...) sözlüğü (kod + parametre).
    warning: dict | None = None
    # Kalıcı ve BEKLENEN durum (ücretsiz katman 401/402/403, sembol kapsam dışı): kullanıcıya
    # uyarı olarak gösterilmez, yalnızca loglanır ve 24 saat tekrar denenmez (provider_skip).
    expected: bool = False


class NewsProvider(ABC):
    """Bir haber kaynağının sözleşmesi."""

    #: İnsan-okur ad (loglar/UI için) ve DB'ye yazılan `provider` etiketi.
    name: str = "base"

    #: Bu sağlayıcının hangi entity tipini beslediği ("ticker" | "keyword").
    entity_type: str = ""

    #: Sağlayıcı haberleri ZATEN entity'ye göre filtreliyor mu? (Finnhub
    #: company-news = ticker'a göre, NewsAPI = arama terimine göre → True.)
    #: True ise ön-filtre atlanır (ikinci bir başlık-eşleşme kapısı gereksiz ve
    #: yanlış eler); alaka güvencesi Claude'un relevance<0.3 elemesindedir.
    entity_filtered: bool = True

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
    warning: dict | None = None  # app.messages.msg(...)
    expected: bool = False       # kalıcı/beklenen (bkz. ProviderResult.expected)


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


# --------------------------------------------------------------------------- #
#  Analist verisi sağlayıcı arayüzü (al/tut/sat + hedef fiyat)
#  ÖNEMLİ: Bu GERÇEK analist konsensüsüdür — NewsRadar/Claude ÜRETMEZ, sadece aktarır.
#  (Finnhub ücretsiz katmanda price-target kapalı → hedef alanları şimdilik None.)
# --------------------------------------------------------------------------- #
@dataclass
class AnalystRating:
    """Bir varlık için analist konsensüsü (en güncel dönem)."""

    strong_buy: int = 0
    buy: int = 0
    hold: int = 0
    sell: int = 0
    strong_sell: int = 0
    period: str | None = None
    # Hedef fiyatlar — GERÇEK analist verisi. Finnhub ücretsiz katmanda YOK (premium);
    # FMP (Financial Modeling Prep) ücretsiz katmanı price-target-consensus ile sağlar.
    # Kaynak ne olursa olsun bunlar GERÇEK analist rakamlarıdır — Claude ÜRETMEZ.
    target_high: float | None = None
    target_low: float | None = None
    target_mean: float | None = None      # ortalama/konsensüs hedef
    target_median: float | None = None
    target_consensus: float | None = None  # FMP'nin açık "consensus" değeri (≈ mean)


@dataclass
class AnalystResult:
    provider: str
    rating: AnalystRating | None = None
    warning: dict | None = None  # app.messages.msg(...)
    expected: bool = False       # kalıcı/beklenen (bkz. ProviderResult.expected)


class AnalystProvider(ABC):
    """Bir analist-verisi kaynağının sözleşmesi. Yalnızca `type=ticker` için."""

    name: str = "base-analyst"

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, entity: Entity) -> AnalystResult:
        """Analist konsensüsü döner. Hata/anahtar yoksa warning ile döner, çökmez."""
        raise NotImplementedError
