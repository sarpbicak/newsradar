"""API istek/yanıt modelleri (Pydantic)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from ..db.models import ENTITY_TYPES


# --------------------------- İstek modelleri --------------------------- #
class EntityCreate(BaseModel):
    name: str
    type: str
    query: str

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        if v not in ENTITY_TYPES:
            raise ValueError(f"type '{v}' geçersiz; {ENTITY_TYPES} olmalı.")
        return v

    @field_validator("name", "query")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("boş olamaz")
        return v


class ChatRequest(BaseModel):
    entity_id: int
    messages: list[dict]  # [{role: 'user'|'assistant', content: str}, ...]


# --------------------------- Yanıt modelleri --------------------------- #
class AnalysisOut(BaseModel):
    risk_score: int
    sentiment_trend: str
    top_drivers: list[str]
    summary: str
    stance: str
    conviction: str
    what_to_verify: list[str]
    invalidation: str
    articles_considered: int
    created_at: datetime


class PreviousAnalysisOut(BaseModel):
    """Bir önceki değerlendirme snapshot'ı (değişim karşılaştırması için)."""

    risk_score: int
    stance: str
    sentiment_trend: str
    avg_sentiment: float | None
    created_at: datetime


class DeltaOut(BaseModel):
    """Son iki değerlendirme arasındaki değişim. Yeterli geçmiş yoksa None döner."""

    risk_delta: int                    # + = risk arttı (kötü), - = azaldı (iyi)
    stance_changed: bool
    previous_stance: str | None        # yalnızca değiştiyse dolu
    sentiment_delta: float | None      # snapshot avg_sentiment farkı (yoksa None)


class EntityCardOut(BaseModel):
    """Overview kartı: entity + son değerlendirme + değişim + sayaçlar."""

    id: int
    name: str
    type: str
    query: str
    active: bool
    article_count: int
    analyzed_count: int
    avg_sentiment: float | None
    top_flags: list[str]
    last_updated: datetime | None
    analysis: AnalysisOut | None
    previous_analysis: PreviousAnalysisOut | None = None
    delta: DeltaOut | None = None
    # Fiyat (yalnızca ticker entity'lerde dolu; keyword'de None).
    price: float | None = None
    change_percent: float | None = None
    price_updated_at: datetime | None = None


class ArticleOut(BaseModel):
    id: int
    url: str
    title: str
    source: str
    published_at: datetime | None
    provider: str
    analyzed: bool
    sentiment: float | None
    event_type: str | None
    risk_flags: list[str] | None
    impact_horizon: str | None
    relevance: float | None
    rationale: str | None


class SuggestionOut(BaseModel):
    """Öneri kartı: co-mentioned şirket + neden gündemde + hangi entity'lerden."""

    id: int
    name: str
    ticker: str | None
    is_public: bool | None
    mention_count: int
    sample_rationale: str | None
    source_entity_names: list[str]
    last_seen_at: datetime


class RiskPointOut(BaseModel):
    """Risk skoru zaman serisinde tek nokta (grafik için)."""

    created_at: datetime
    risk_score: int
    stance: str


class PricePointOut(BaseModel):
    """Fiyat zaman serisinde tek nokta (grafik için)."""

    fetched_at: datetime
    price: float


class DashboardOut(BaseModel):
    entity: EntityCardOut
    articles: list[ArticleOut]
    risk_history: list[RiskPointOut] = []
    price_history: list[PricePointOut] = []


class RefreshSummaryOut(BaseModel):
    """Son tamamlanan yenilemenin özeti (/status içinde)."""

    fetched_new: int
    prefiltered: int
    analyzed: int
    discarded: int
    entity_assessments: int
    warnings: list[str]


class RefreshAck(BaseModel):
    """/refresh anında döner: tarama arka planda başladı mı."""

    started: bool          # bu çağrı yeni bir tarama başlattı mı
    is_running: bool       # şu an bir tarama çalışıyor mu
    message: str


class ProviderStatusOut(BaseModel):
    providers: dict[str, bool]
    claude: bool
    scheduler_enabled: bool
    # Yenileme süreci durumu (polling için).
    is_running: bool = False
    progress_done: int = 0
    progress_total: int = 0
    last_completed_at: datetime | None = None
    last_summary: RefreshSummaryOut | None = None
