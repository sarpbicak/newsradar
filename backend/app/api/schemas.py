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


class FeedbackIn(BaseModel):
    """Geri bildirim gönderimi (herkese açık). message zorunlu, contact opsiyonel."""

    message: str = Field(min_length=1, max_length=2000)
    contact: str | None = Field(default=None, max_length=200)

    @field_validator("message")
    @classmethod
    def _non_empty_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("boş olamaz")
        return v

    @field_validator("contact")
    @classmethod
    def _clean_contact(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return v or None


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
    is_anonymous: bool = False   # anon cihaz oturumu mu (frontend "Misafir" gösterir)
    created_at: datetime
    last_login_at: datetime | None = None
    guide_dismissed: bool = False   # "NewsRadar ne yapar?" kutusu kapatıldı mı
    tutorial_done: bool = False     # ilk giriş tutorial'ı tamamlandı mı
    language: str = "tr"            # arayüz dili (tr/en)


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


class PasswordResetOut(BaseModel):
    """Admin şifre sıfırlama sonucu — geçici şifre YALNIZCA burada döner (bir kez)."""

    username: str
    temp_password: str


class AdminUserDetail(BaseModel):
    """Tek kullanıcının detaylı kullanımı."""

    user: UserOut
    event_counts: dict[str, int]           # {event_type: adet}
    top_entities: list[dict]               # [{name, count}] — en çok view alan
    recent_events: list[AdminEventOut]     # son eylemler (zaman çizelgesi)
    watchlist: list[dict]                  # [{name, type, query}] — kullanıcının takip ettikleri
    watchlist_size: int                    # izleme listesi boyutu


class FeedbackAck(BaseModel):
    """Geri bildirim gönderim onayı."""

    ok: bool = True


class AdminFeedbackOut(BaseModel):
    """Admin gelen kutusu satırı — mesaj + gönderen + cihaz + okundu."""

    id: int
    message: str
    contact: str | None = None
    username: str | None = None       # gönderen kullanıcı adı; anonim/silinmişse None
    is_anonymous: bool = False        # gönderen anon cihaz oturumu muydu
    device: str = "bilinmiyor"        # "mobil" | "masaüstü" | "bilinmiyor" (user_agent'tan)
    user_agent: str | None = None
    is_read: bool = False
    created_at: datetime


class AdminHealthOut(BaseModel):
    """LLM sistem sağlığı özeti (admin paneli)."""

    last_kind: str | None = None           # 'ok' | 'quota' | 'error' | None (hiç olay yok)
    last_at: datetime | None = None        # son sağlık olayının zamanı
    last_status_code: int | None = None    # son kota hatasının HTTP kodu (402/403)
    last_ok_at: datetime | None = None     # en son başarılı LLM çağrısı
    quota_errors_24h: int = 0              # son 24 saatteki kota hatası sayısı
    errors_24h: int = 0                    # son 24 saatteki diğer LLM hataları


class AdminStatsOut(BaseModel):
    """Genel istatistikler."""

    total_users: int
    max_users: int                         # kayıt sınırı (0 = sınırsız); panelde N/limit göster
    active_today: int                      # bugün en az 1 eylem yapan kullanıcı
    refreshes_today: int
    top_entities: list[dict]               # [{name, count}] — en popüler (view)
    most_followed: list[dict]              # [{name, type, followers}] — en çok watchlist'te
    total_entities: int                    # havuzdaki benzersiz (takip edilen) entity sayısı
    # Maliyet takibi (çağrı başına model fiyat tablosundan USD) + günlük USD bütçe durumu.
    tokens_today: int = 0
    tokens_week: int = 0
    tokens_month: int = 0
    cost_today_usd: float = 0.0
    cost_week_usd: float = 0.0
    cost_month_usd: float = 0.0
    daily_budget_usd: float = 0.0          # 0 = sınırsız
    budget_exceeded: bool = False
    # Önbellek isabet oranı (cache_read / tüm girdi), son 7 gün; veri yoksa None.
    cache_hit_rate_7d: float | None = None
    # Son 30 gün model kırılımı: [{model, calls, input_tokens, output_tokens,
    #   cache_creation_tokens, cache_read_tokens, cost_usd, cache_hit_rate}]
    model_breakdown: list[dict] = []
    unread_feedback: int = 0               # okunmamış geri bildirim sayısı
    # Sistem sağlığı (LLM): son çağrı sonucu + son 24s kota/hata sayısı. Sorunu
    # kullanıcıdan önce admin görsün (ör. OpenRouter kota/bakiye limiti).
    health: AdminHealthOut | None = None


# --------------------------- Yanıt modelleri --------------------------- #
class AnalysisOut(BaseModel):
    headline_verdict: str | None = None
    ai_take: str | None = None
    risk_score: int
    sentiment_trend: str
    top_drivers: list[str]
    driver_directions: list[str | None] | None = None  # top_drivers ile aynı sıra: up/down/null
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
    display_name: str | None = None        # kısa görünen ad (AMD); arayüz `display_name or name`
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
    analysis_language: str | None = None   # gösterilen değerlendirmenin dili; artık HEP istenen
                                           # dil (başka dile düşülmez) ya da analiz yoksa None
    # İstenen dilde analiz YOK ama başka dilde VAR → analysis=None + bu bayrak True. Arayüz
    # "Bu dilde henüz analiz yok, bir sonraki yenilemede gelecek" gösterir. Hiç analiz yoksa
    # (yeni entity) False kalır — o durum "henüz analiz yok" boş halidir.
    analysis_missing_language: bool = False
    # Analiz yoksa neden: "pending" (analiz bekleyen haber var → yenileme işe yarar) ·
    # "few_news" (pencerede analiz edilecek haber yok → yeni haber çıkınca güncellenir).
    no_analysis_reason: str | None = None
    news_window_days: int = 2                # haber penceresi (lookback) gün olarak
    # Kart hiyerarşisi için türetilmiş "3 saniyelik" alanlar (analiz varsa dolu).
    horizon: str | None = None            # çoğunluk vade: short | medium | long
    evidence_strength: str | None = None  # strong | medium | weak
    evidence_count: int = 0               # hükmün dayandığı analiz edilmiş haber sayısı
    previous_analysis: PreviousAnalysisOut | None = None
    delta: DeltaOut | None = None
    # Kademeli düzen: öncelik skoru + neden + katman (1 = "bugün önemli", 2 = liste).
    # tier list_entities'te global sıralamayla atanır (skor ≥ 2 olan en yüksek 3 → tier 1).
    priority_score: int = 0
    priority_reason: str | None = None      # "yön değişti" | "sert hareket" | "ayrışma" | "risk sıçraması"
    tier: int = 2
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
    pending: int     # bekleyen (analyzed=False, prefiltered=False, expired=False) — sonraki yenilemede işlenir
    expired: int = 0  # lookback dışına düştüğü için analiz edilmeyecek (LLM'e gönderilmez)


class AnalystPeriodOut(BaseModel):
    """Bir tavsiye dönemindeki (Finnhub, aylık) al/tut/sat dağılımı — dönemin son snapshot'ı."""

    period: str
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int


class DashboardOut(BaseModel):
    entity: EntityCardOut
    articles: list[ArticleOut]
    article_status: ArticleStatusOut
    risk_history: list[RiskPointOut] = []
    price_history: list[PricePointOut] = []
    analyst_history: list[AnalystPeriodOut] = []  # eski → yeni, en fazla 6 dönem


class MessageOut(BaseModel):
    """Kullanıcıya giden uyarı/bilgi: kod + parametre (app/messages.py). Frontend
    `msg.<code>` anahtarıyla kullanıcının dilinde metne çevirir."""

    code: str
    entity: str | None = None
    params: dict = {}


class RefreshSummaryOut(BaseModel):
    """Son tamamlanan yenilemenin özeti (/status içinde). Sayaçların anlamı:
    refresh.RefreshSummary'deki açıklamaya bakın."""

    fetched_new: int            # bu taramada YENİ eklenen makale
    prefiltered: int            # LLM'e gitmeden elenen (kopya / ön-filtre)
    analyzed: int               # LLM sonrası TUTULAN
    discarded: int              # LLM sonrası ilgisiz bulunup elenen
    llm_articles: int = 0       # bu taramada LLM'e gidip yanıtı alınan (kuyruktan gelenler dahil)
    queued: int = 0             # hâlâ analiz bekleyen (sonraki yenilemede)
    expired: int = 0            # lookback dışına düştüğü için LLM'den çıkarılan
    entity_assessments: int
    assessments_skipped: int = 0
    warnings: list[MessageOut]
    infos: list[MessageOut] = []
    quota_error: bool = False  # sağlayıcı kota/bakiye limiti → analiz durdu (kullanıcı banner'ı)


class RefreshAck(BaseModel):
    """/refresh anında döner: iş çalışıyor mu, sırada mı (yenileme kuyruğu)."""

    accepted: bool         # çağrıdan sonra bu kullanıcının bir işi çalışıyor YA DA sırada mı
    started: bool          # BU çağrının işi şu an çalışıyor mu (sıra boştu, hemen başladı)
    queued: bool = False   # kullanıcının işi sırada mı bekliyor
    queue_position: int | None = None  # sıradaysa 1 tabanlı konum (bekleyenler arasında)
    is_running: bool       # BU KULLANICININ işi şu an çalışıyor mu
    # None: yeni iş kabul edildi (çalışıyor ya da sırada) · "empty" (liste boş, kabul yok) ·
    # "running" (kendi işi zaten çalışıyor, izlemesi yeter) · "queued" (kendi işi zaten
    # sırada) · "queue_full" (sıra dolu, kabul yok) · "budget" (günlük bütçe dolu, kabul yok).
    reason: str | None = None
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
    current_entity: str | None = None  # şu an analiz edilen şirket adı (UI: "Tesla analiz ediliyor…")
    # Adım bazlı ilerleme: step = prices | fetch | filter | analyze | assess; frontend
    # kullanıcının dilinde metne çevirir. progress_fraction: entity dilimlerinin ortalaması.
    step: str | None = None
    step_entity: str | None = None
    step_count: int | None = None
    progress_fraction: float = 0.0
    skipped_entity: str | None = None  # "X atlandı, yeni veri yok" (~3 sn)
    # KİŞİSEL son sonuç: last_completed_at yalnızca veri gerçekten tazelendiyse (done|merged);
    # last_summary yalnızca done'da. last_result_*: her durum için (done|merged|failed|
    # budget|canceled), Türkçe kısa mesaj ve bitiş anı.
    last_completed_at: datetime | None = None
    last_summary: RefreshSummaryOut | None = None
    last_result_status: str | None = None
    last_result_message: str | None = None
    last_result_at: datetime | None = None
    # Yenileme kuyruğu (kişisel): sırada mı, kaçıncı (1 tabanlı), sırada kaç kullanıcı işi var.
    queued: bool = False
    queue_position: int | None = None
    queue_length: int = 0
    # Kişisel elle yenileme kotası (rolling 24s). refresh_limit=0 → sınırsız.
    refresh_limit: int = 0
    refresh_used: int = 0
    refresh_is_admin: bool = False
    # Ayarlardaki günlük haklar (NEWSRADAR_MAX_REFRESH_ANON / _REGISTERED) — arayüz açıklaması için.
    refresh_limit_anon: int = 0
    refresh_limit_registered: int = 0
    # Hak dolduysa bir hakkın geri geleceği an (UTC); dolmadıysa None.
    refresh_resets_at: datetime | None = None
    # Sistem-geneli günlük USD bütçesi (maliyet güvencesi).
    budget_exceeded: bool = False          # dolduysa yeni analiz durur
    cost_today_usd: float = 0.0
    daily_budget_usd: float = 0.0          # 0 = sınırsız
    # Kişisel entity kotası (kademeli; kartta "N/limit" göstermek için).
    entity_limit: int = 0
    entity_used: int = 0


class HowHeadlineOut(BaseModel):
    """'Nasıl çalışır?' — gerçek bir haber başlığı + AI etiketi."""

    title: str
    source: str | None = None
    label: str                      # positive | negative | neutral | irrelevant
    published_at: datetime | None = None


class PublicStatsOut(BaseModel):
    """Landing sayfasındaki gerçek rakamlar (yalnızca toplamlar)."""

    articles_analyzed: int        # AI'ın analiz ettiği haber (DB'deki analyzed=True)
    assessments: int              # üretilen AI değerlendirmesi (entity_analyses satırı, tüm diller)
    news_sources: int             # haberlerdeki farklı kaynak (boş kaynak sayılmaz)
    languages: list[str]          # arayüz + AI değerlendirmesi dilleri


class HowItWorksOut(BaseModel):
    """'Nasıl çalışır?' anlatımının gerçek örnek verisi (uydurma yok)."""

    available: bool = False         # uygun örnek (güncel analizli seed şirket) yoksa False
    entity: EntityCardOut | None = None
    headlines: list[HowHeadlineOut] = []
    articles_week: int = 0          # son 7 günde toplanan (elenenler dahil)
    providers: list[str] = []       # gerçek kaynak adları (Finnhub, NewsAPI…)
