"""API istek/yanıt modelleri (Pydantic)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ..db.models import ENTITY_LANGUAGES, ENTITY_TYPES


# --------------------------- İstek modelleri --------------------------- #
class EntityCreate(BaseModel):
    name: str = Field(max_length=200)
    type: str = Field(max_length=20)
    query: str = Field(max_length=200)
    language: str = "en"

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        if v not in ENTITY_TYPES:
            raise ValueError(f"type '{v}' geçersiz; {ENTITY_TYPES} olmalı.")
        return v

    @field_validator("language")
    @classmethod
    def _valid_language(cls, v: str) -> str:
        v = (v or "en").strip().lower()
        if v not in ENTITY_LANGUAGES:
            raise ValueError(f"language '{v}' geçersiz; {ENTITY_LANGUAGES} olmalı.")
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
    messages: list[dict] = Field(max_length=50)  # aşırı uzun konuşma reddedilsin


# --------------------------- Kullanıcı hesapları --------------------------- #
class RegisterIn(BaseModel):
    username: str = Field(max_length=100)   # detay doğrulama route'ta (regex 3–30)
    password: str = Field(max_length=200)


class UserLoginIn(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


class UserOut(BaseModel):
    """Mevcut kullanıcı bilgisi (/users/me + kayıt/giriş yanıtı)."""

    id: int
    username: str
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None = None


class UserTokenOut(BaseModel):
    """Kayıt/giriş sonrası: kişisel token + kullanıcı."""

    token: str
    user: UserOut


# ------------------------------- Admin paneli ------------------------------ #
class AdminUserRow(BaseModel):
    """Admin kullanıcı listesi satırı: özet sayaçlar + son aktiflik."""

    id: int
    username: str
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None
    login_count: int
    refresh_count: int
    total_events: int
    last_active_at: datetime | None


class AdminEventOut(BaseModel):
    event_type: str
    detail: dict | None
    created_at: datetime


class AdminUserDetail(BaseModel):
    """Tek kullanıcının detaylı kullanımı."""

    user: UserOut
    event_counts: dict[str, int]           # {event_type: adet}
    top_entities: list[dict]               # [{name, count}] — en çok view alan
    recent_events: list[AdminEventOut]     # son eylemler (zaman çizelgesi)


class AdminStatsOut(BaseModel):
    """Genel istatistikler."""

    total_users: int
    active_today: int                      # bugün en az 1 eylem yapan kullanıcı
    refreshes_today: int
    top_entities: list[dict]               # [{name, count}] — en popüler (view)


# --------------------------- Yanıt modelleri --------------------------- #
class AnalysisOut(BaseModel):
    headline_verdict: str | None = None
    ai_take: str | None = None
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


class AnalystOut(BaseModel):
    """Analist verisi (GERÇEK — tavsiye Finnhub, hedef fiyat FMP; NewsRadar ÜRETMEZ)."""

    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int
    total: int
    period: str | None
    # Hedef fiyatlar — GERÇEK analist konsensüsü (FMP). Kaynak yoksa None (tahmin YOK).
    target_mean: float | None = None
    target_high: float | None = None
    target_low: float | None = None
    target_median: float | None = None
    target_consensus: float | None = None
    # Güncel fiyata göre hedef farkı (%). Frontend renk/etiket için.
    current_price: float | None = None
    upside_percent: float | None = None
    fetched_at: datetime


class EntityCardOut(BaseModel):
    """Overview kartı: entity + son değerlendirme + değişim + sayaçlar."""

    id: int
    name: str
    type: str
    query: str
    language: str = "en"
    active: bool
    article_count: int
    analyzed_count: int
    avg_sentiment: float | None
    top_flags: list[str]
    last_updated: datetime | None
    analysis: AnalysisOut | None
    # Kart hiyerarşisi için türetilmiş "3 saniyelik" alanlar (analiz varsa dolu).
    horizon: str | None = None            # çoğunluk vade: short | medium | long
    evidence_strength: str | None = None  # strong | medium | weak
    evidence_count: int = 0               # hükmün dayandığı analiz edilmiş haber sayısı
    previous_analysis: PreviousAnalysisOut | None = None
    delta: DeltaOut | None = None
    # Fiyat (yalnızca ticker entity'lerde dolu; keyword'de None).
    price: float | None = None
    change_percent: float | None = None
    price_updated_at: datetime | None = None
    # Analist konsensüsü (yalnızca ticker + veri varsa; yoksa None).
    analyst: AnalystOut | None = None


class ArticleOut(BaseModel):
    id: int
    url: str
    title: str
    source: str
    source_count: int = 1   # aynı haber kaç kaynakta çıktı (dedup); >1 = önem sinyali
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
    why_relevant: str | None    # önerilen şirketin neden gündemde olduğu (eski kayıtlarda None)
    source_entity_names: list[str]
    last_seen_at: datetime
    # Eklenince ne olacağı (kullanıcıya önceden göstermek için).
    add_as_type: str            # "ticker" | "keyword"
    add_as_language: str | None  # keyword ise dil, ticker ise None


class RiskPointOut(BaseModel):
    """Risk skoru zaman serisinde tek nokta (grafik için)."""

    created_at: datetime
    risk_score: int
    stance: str


class PricePointOut(BaseModel):
    """Fiyat zaman serisinde tek nokta (grafik için)."""

    fetched_at: datetime
    price: float


class ArticleStatusOut(BaseModel):
    """Bir entity'nin makale durum sayacı (detay sayfasında teşhis için).

    'takıldı mı?' bir bakışta görünsün: çekilen ama analiz edilmeyen (bekleyen)
    yığını burada belli olur — üç tur teşhis dönmeye gerek kalmadan.
    """

    total: int       # entity'ye ait tüm makaleler
    analyzed: int    # analiz edilmiş (analyzed=True)
    prefiltered: int  # ön-filtrede elenmiş (Claude'a hiç gitmedi)
    pending: int     # bekleyen (analyzed=False, prefiltered=False) — bir sonraki yenilemede işlenir


class DashboardOut(BaseModel):
    entity: EntityCardOut
    articles: list[ArticleOut]
    article_status: ArticleStatusOut
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
    infos: list[str] = []


class RefreshAck(BaseModel):
    """/refresh anında döner: tarama arka planda başladı mı."""

    started: bool          # bu çağrı yeni bir tarama başlattı mı
    is_running: bool       # şu an bir tarama çalışıyor mu
    message: str


class SymbolResultOut(BaseModel):
    """Sembol arama sonucu (ticker eklerken otomatik tamamlama)."""

    symbol: str
    description: str
    type: str
    market: str              # "US" ya da yabancı borsa son eki (IS, DE, L...)
    us_supported: bool       # Finnhub kapsıyor mu (ABD borsası)
    exchange_name: str       # insan-okur borsa adı ("ABD", "Borsa İstanbul"...)
    suggested_language: str  # keyword'e yönlendirilirse önerilen dil (IS→tr...)


class NewsApiQuotaOut(BaseModel):
    """NewsAPI kota durumu (rolling 24s)."""

    used: int
    limit: int
    remaining: int
    exhausted: bool
    warn: bool
    reset_in_hours: float


class ProviderStatusOut(BaseModel):
    providers: dict[str, bool]
    claude: bool
    scheduler_enabled: bool
    newsapi_quota: NewsApiQuotaOut | None = None
    # Yenileme süreci durumu (polling için).
    is_running: bool = False
    progress_done: int = 0
    progress_total: int = 0
    last_completed_at: datetime | None = None
    last_summary: RefreshSummaryOut | None = None
