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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# İzin verilen değerler (uygulama seviyesinde doğrulama; SQLite enum zorlamaz).
ENTITY_TYPES = ("ticker", "keyword")
# Haber arama dili (NewsAPI `language` parametresi). Varsayılan İngilizce.
ENTITY_LANGUAGES = ("en", "tr", "de", "fr")

# Ön-filtre kural sürümü. Kurallar değişince ARTIR → eski sürümle prefiltered
# işaretlenen makaleler açılışta yeniden değerlendirmeye açılır (reconcile_prefilter).
# v2: keyword'lerde ön-filtre gevşetildi + Türkçe-güvenli eşleşme.
# v3: eski sürümlerde (ör. AMD) yanlış/eski prefiltered kalıp drain olmayan makaleleri
#     kurtarmak için sürüm artırıldı — deploy'da hepsi yeniden değerlendirmeye açılır.
# v4: ticker ön-filtresi kaldırıldı — Finnhub company-news zaten entity-filtreli, başlık
#     eşleşmesi "Lisa Su unveils Helios" gibi AMD haberlerini yanlış eliyordu. Takılı
#     prefiltered makaleler açılışta açılır ve bu sefer analize girer.
PREFILTER_VERSION = 4
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
    # Haber arama dili (özellikle keyword/NewsAPI için). Varsayılan 'en'.
    language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
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


class UserWatchlist(Base):
    """Kişisel izleme listesi (kullanıcı ↔ entity, many-to-many).

    MİMARİ: entity'ler ORTAK havuzda (bir kez analiz edilir); "kim neyi takip
    ediyor" bu tabloda kişiseldir. Bir kullanıcının listesi = buradaki kendi
    satırları. Bir entity en az bir satırda geçiyorsa aktiftir (analiz edilir);
    hiçbirinde geçmiyorsa pasif olur (silinmez — havuzda kalır, veri hazır durur).
    """

    __tablename__ = "user_watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "entity_id", name="uq_user_watchlist"),
    )


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
    # Bu makaleyi eleyen ön-filtre kuralının sürümü (0 = sürümsüz/eski). Güncel
    # sürümün altındaysa reconcile ile yeniden değerlendirmeye açılır.
    prefilter_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Aynı haberin kaç kaynakta çıktığı (dedup ile birleşen kopya sayısı). 1 = tekil.
    # Çok kaynakta çıkması ÖNEM sinyalidir (sentiment tekrarı değil — kopyalar elenir).
    source_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

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


class ApiCall(Base):
    """Sağlayıcı API çağrısı kaydı — kota takibi için (rolling 24 saat).

    Özellikle NewsAPI ücretsiz katmanı (günde ~100 istek) sınırını aşmamak için
    her gerçek çağrı burada zaman damgasıyla saklanır; son 24 saat sayılır.
    """

    __tablename__ = "api_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    called_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class LoginRate(Base):
    """IP başına giriş hız-sınırı durumu (KALICI — süreç yeniden başlasa da korunur).

    In-memory sayaç Render free tier'da soğuk-başlangıçta sıfırlanıyordu → kilit
    kayboluyordu. DB'de tutulur: attempts = pencere içindeki başarısız zaman damgaları
    (JSON), locked_until = kilidin bittiği epoch saniyesi.
    """

    __tablename__ = "login_rate"

    ip: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # JSON list[float]
    locked_until: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class LlmUsage(Base):
    """LLM token kullanımı (maliyet takibi + günlük bütçe tavanı). Her yenileme sonunda
    o taramanın toplam token deltası bir satır olarak yazılır; günlük toplam buradan sayılır.
    """

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class LlmHealthEvent(Base):
    """LLM sağlık olayı — her yenileme sonunda bir satır: sağlayıcı çağrıları başarılı
    mıydı yoksa kalıcı kota/hata mı aldı. Admin paneli 'sistem sağlığı' göstergesi bunu
    okur (son çağrı başarılı mı, son 24 saatteki kota hataları) — sorun kullanıcıdan önce
    görülsün. kind: 'ok' | 'quota' | 'error'.
    """

    __tablename__ = "llm_health_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class Feedback(Base):
    """Kullanıcı geri bildirimi (herkese açık — anon da yazabilir). Yalnızca admin okur.

    user_id nullable: anonim (token'sız) gönderim ya da gönderen kullanıcı silinince NULL
    olur (geri bildirim korunur, kimlik düşer). IP SAKLANMAZ (spam sınırı ephemeral,
    GDPR); yalnızca user_agent tutulur (mobil/masaüstü ayrımı için).
    """

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )


class Suggestion(Base):
    """Öneri: analiz edilen haberlerde geçen ama izleme listesinde OLMAYAN şirketler.

    Co-mentioned varlıklardan biriktirilir. `norm_key` ile tekilleştirilir:
    ticker varsa 't:TICKER', yoksa 'n:isim' (lowercase). Filtreleme (izleme
    listesinde olanları/dismissed/az anılanları eleme) LİSTELEME anında yapılır.
    """

    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_public: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Ülke/borsa ipucu (Claude biliyorsa; add sırasında ABD-listeli mi kararı için).
    country: Mapped[str | None] = mapped_column(String(60), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Bu öneri hangi entity'nin haberinden geldiyse onun dili (add'de keyword dili).
    source_language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
    # Tekilleştirme anahtarı (ticker'a ya da isme göre normalize).
    norm_key: Mapped[str] = mapped_column(String(220), nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Hangi entity'lerin haberlerinde geçti (id listesi).
    source_entity_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # ÖNERİLEN şirketin neden gündemde olduğu (şirket-özel, tek cümle). Eski
    # kayıtlarda NULL → kartta hiç gösterilmez.
    why_relevant: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("norm_key", name="uq_suggestion_norm"),)


class SuggestionDismissal(Base):
    """Bir kullanıcının bir öneriyi kapatması (KİŞİSEL — başkasını etkilemez).

    Öneri tablosu ortak (co-mention havuzu) ama "kapatma" kişiseldir: A kullanıcısı
    bir öneriyi kapatınca yalnızca A'da gizlenir; B hâlâ görebilir (izolasyon).
    """

    __tablename__ = "suggestion_dismissals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suggestion_id: Mapped[int] = mapped_column(
        ForeignKey("suggestions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dismissed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "suggestion_id", name="uq_suggestion_dismissal"),
    )


class PriceSnapshot(Base):
    """Bir ticker entity'nin anlık fiyat görüntüsü (her yenilemede append-only).

    Fiyat TAHMİN için değil; haberin fiyata yansıyıp yansımadığını görmek için.
    """

    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price: Mapped[float] = mapped_column(Float, nullable=False)
    change_percent: Mapped[float | None] = mapped_column(Float, nullable=True)  # günlük %
    previous_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    day_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    day_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AnalystSnapshot(Base):
    """Bir ticker entity için analist konsensüsü (her yenilemede append-only).

    GERÇEK analist verisi (Finnhub) — NewsRadar/Claude üretmez, sadece saklar/aktarır.
    Hedef fiyat alanları ücretsiz katmanda None (price-target premium).
    """

    __tablename__ = "analyst_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Hedef fiyatlar — GERÇEK analist verisi (FMP price-target-consensus). Kaynak
    # yoksa None (asla tahminle doldurulmaz). Finnhub premium olduğu için FMP kullanılır.
    target_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_median: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_consensus: Mapped[float | None] = mapped_column(Float, nullable=True)  # FMP consensus
    # Al/tut/sat dağılımı.
    strong_buy: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    buy: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sell: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    strong_sell: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# İzin verilen kullanım eylemi tipleri (usage_events.event_type).
USAGE_EVENT_TYPES = (
    "login", "login_failed", "register_failed", "refresh", "view_entity",
    "add_entity", "remove_entity", "chat", "add_suggestion", "dismiss_suggestion",
    "delete_user", "password_reset", "feedback_sent",
)


class User(Base):
    """Kişisel hesap (Katman 2). Veri ORTAK — kullanıcı yalnızca 'kim yaptı' ayrımı için.

    Şifre bcrypt ile hash'lenir (düz metin ASLA saklanmaz). username büyük/küçük
    harf duyarsız benzersizdir (functional unique index).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)  # bcrypt
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Son aktiflik: HER kimlik-doğrulanmış istekte (get_current_user) tazelenir —
    # login gibi belirli eylemler değil, sadece siteyi gezmek de sayılır (throttle'lı).
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # "NewsRadar ne yapar?" açıklama kutusu kapatıldı mı (kullanıcı tercihi; kalıcı).
    guide_dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # İlk giriş tutorial'ı tamamlandı/kapatıldı mı (bir daha gösterilmez; kalıcı).
    tutorial_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # ANONİM CİHAZ OTURUMU: şifresiz kullanım. Anon kullanıcı da normal bir satır;
    # username sentetiktir ("anon:<hash>", insan kaydedemez — regex ':' içermez).
    # Hesaba yükseltince is_anonymous=False + gerçek username/şifre yazılır.
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # device_id cookie'sinin sha256'sı (düz device_id ASLA saklanmaz). Cihazdan kullanıcı bulunur.
    device_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Arayüz dili: "tr" | "en". İlk girişte sorulur, kullanıcıya kaydedilir, her girişte
    # hatırlanır. Analiz metinleri de bu dile göre gösterilir (EntityAnalysis.language).
    language: Mapped[str] = mapped_column(String(5), default="tr", nullable=False)

    # Büyük/küçük harf duyarsız benzersizlik (SQLite functional unique index).
    __table_args__ = (
        Index("uq_users_username_ci", func.lower(username), unique=True),
    )


class UsageEvent(Base):
    """Bir kullanıcının anlamlı bir eylemi (login/refresh/view/...). Kullanım takibi.

    detail: eyleme özgü serbest JSON (ör. {'entity_id': 8, 'name': 'AMD'}).
    """

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )


class EntityAnalysis(Base):
    """Bir entity için toplu (aggregate) Claude analizi — zaman içinde birden çok satır."""

    __tablename__ = "entity_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    # Bu değerlendirmenin dili ("tr" | "en"). Aynı taramada her iki dilde birer satır
    # üretilir; kullanıcı diline göre ilgili satır gösterilir. Eski kayıtlar "tr".
    language: Mapped[str] = mapped_column(String(5), default="tr", nullable=False, index=True)

    # Finans bilmeyen için tek cümlelik düz hüküm (kartın başında). Eski
    # kayıtlarda None → kart özete/yöne düşer.
    headline_verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "AI ne düşünüyor?" — 3-5 cümlelik bütünsel yorum (detay sayfası). Sağlayıcıdan
    # bağımsız ad (ai_take). Eski kayıtlarda None → bölüm gösterilmez.
    ai_take: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)           # 0..100
    sentiment_trend: Mapped[str] = mapped_column(String(20), nullable=False)
    top_drivers: Mapped[list] = mapped_column(JSON, nullable=False)            # list[str], TR
    summary: Mapped[str] = mapped_column(Text, nullable=False)                 # TR
    stance: Mapped[str] = mapped_column(String(10), nullable=False)           # bullish/neutral/bearish
    conviction: Mapped[str] = mapped_column(String(10), nullable=False)       # low/medium/high
    what_to_verify: Mapped[list] = mapped_column(JSON, nullable=False)        # list[str], TR
    invalidation: Mapped[str] = mapped_column(Text, nullable=False)           # TR, tek cümle
    articles_considered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Bu snapshot anındaki ortalama duygu (-1..1) — değişim (delta) hesabı için saklanır.
    avg_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)

    entity: Mapped["Entity"] = relationship(back_populates="analyses")
