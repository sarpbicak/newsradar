"""ORM modelleri: Entity (izleme listesi), Article (haber + analizi), EntityAnalysis (özet).

Şema notları:
- Bir haber (URL) birden çok entity'ye ilgili olabilir; bu yüzden dedupe anahtarı
  (entity_id, url_hash) çiftidir — aynı URL farklı entity'lerde ayrı satır olur.
- Makale-başı Claude analizi Article üzerindeki alanlara yazılır (sentiment, event_type...).
- Entity-başı toplu Claude analizi ayrı EntityAnalysis satırlarında tutulur (geçmiş için).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# İzin verilen değerler (uygulama seviyesinde doğrulama; SQLite enum zorlamaz).
ENTITY_TYPES = ("ticker", "keyword")
EVENT_TYPES = (
    "earnings", "product", "regulation", "lawsuit", "partnership",
    "funding", "macro", "leadership", "other",
)
RISK_FLAGS = (
    "regulatory", "competition", "financial", "legal",
    "product", "supply_chain", "macro", "reputation",
)
IMPACT_HORIZONS = ("short", "medium", "long")
STANCES = ("bullish", "neutral", "bearish")
CONVICTIONS = ("low", "medium", "high")
SENTIMENT_TRENDS = ("improving", "stable", "deteriorating")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def url_hash(url: str) -> str:
    """Bir URL'nin dedupe anahtarı (sha256 hex)."""
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


class Base(DeclarativeBase):
    pass


class Entity(Base):
    """İzleme listesindeki bir varlık: public ticker ya da özel şirket/keyword."""

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # ticker | keyword
    # ticker için sembol (TSLA); keyword için arama sorgusu ("Anthropic").
    query: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    articles: Mapped[list["Article"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    analyses: Mapped[list["EntityAnalysis"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan",
        order_by="EntityAnalysis.created_at.desc()",
    )

    __table_args__ = (UniqueConstraint("type", "query", name="uq_entity_type_query"),)


class Article(Base):
    """Bir haber makalesi + (varsa) makale-başı Claude analizi."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Ham haber alanları (sağlayıcıdan)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    provider: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    # Ön-filtre: entity adı/ticker'ı başlık+açıklamada hiç geçmiyorsa Claude'a
    # gönderilmeden elenir ve burada işaretlenir (tekrar değerlendirilmez, ayrıca
    # url_hash korunduğu için tekrar çekilmez de). Panoda gösterilmez.
    prefiltered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Makale-başı analiz (Claude doldurur; analiz edilene kadar analyzed=False)
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)      # -1..1
    event_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    risk_flags: Mapped[list | None] = mapped_column(JSON, nullable=True)       # list[str]
    impact_horizon: Mapped[str | None] = mapped_column(String(10), nullable=True)
    relevance: Mapped[float | None] = mapped_column(Float, nullable=True)      # 0..1
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)         # TR, tek cümle

    entity: Mapped["Entity"] = relationship(back_populates="articles")

    # Aynı URL aynı entity'de tekrar edilmesin (dedupe).
    __table_args__ = (
        UniqueConstraint("entity_id", "url_hash", name="uq_article_entity_url"),
    )


class EntityAnalysis(Base):
    """Bir entity için toplu (aggregate) Claude analizi — zaman içinde birden çok satır."""

    __tablename__ = "entity_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)           # 0..100
    sentiment_trend: Mapped[str] = mapped_column(String(20), nullable=False)
    top_drivers: Mapped[list] = mapped_column(JSON, nullable=False)            # list[str], TR
    summary: Mapped[str] = mapped_column(Text, nullable=False)                 # TR
    stance: Mapped[str] = mapped_column(String(10), nullable=False)           # bullish/neutral/bearish
    conviction: Mapped[str] = mapped_column(String(10), nullable=False)       # low/medium/high
    what_to_verify: Mapped[list] = mapped_column(JSON, nullable=False)        # list[str], TR
    invalidation: Mapped[str] = mapped_column(Text, nullable=False)           # TR, tek cümle
    articles_considered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    entity: Mapped["Entity"] = relationship(back_populates="analyses")
