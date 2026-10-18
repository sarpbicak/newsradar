"""Ortam tabanlı yapılandırma. Tüm anahtarlar `.env`'den okunur, koda gömülmez."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# backend/ kökündeki .env dosyasını yükle.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    """Ortam değişkenini okur, satır-içi `#` yorumunu ve boşlukları temizler.

    python-dotenv tırnaksız değerlerdeki satır-içi yorumları ayıklamaz;
    `MODEL=claude-... # not` gibi bir satır tüm yorumla birlikte değere sızar.
    Bu yüzden config değerlerini burada `#` öncesinden kesip kırpıyoruz.
    """
    return os.getenv(name, default).split("#")[0].strip()


class Settings:
    """Uygulama ayarları (tek örnek, `get_settings()` ile alınır)."""

    def __init__(self) -> None:
        self.anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "").strip()
        self.newsapi_key: str = os.getenv("NEWSAPI_KEY", "").strip()
        # FMP (Financial Modeling Prep) — GERÇEK analist hedef fiyatı (Finnhub'da premium).
        # Yoksa hedef fiyat gösterilmez (tavsiye/haber etkilenmez).
        self.fmp_api_key: str = os.getenv("FMP_API_KEY", "").strip()

        # Paylaşılan tek şifre (Katman 1 — genel kapı). Boşsa giriş devre dışı ve
        # korumalı uçlar 503 döner — yani parola ayarlanmadan kimse giremez.
        self.app_password: str = os.getenv("APP_PASSWORD", "").strip()
        # Katman 2 — kişisel hesaplar. Bu kullanıcı adıyla kayıt olan admin olur.
        # Boşsa: İLK kayıt olan kullanıcı otomatik admin olur.
        self.admin_username: str = os.getenv("ADMIN_USERNAME", "").strip()
        # Oturum token'ı HMAC imza sırrı. Ayrı APP_SECRET önerilir; yoksa APP_PASSWORD'a
        # düşer (kodda SABİT varsayılan YOK — ikisi de boşsa token üretilemez).
        self.app_secret: str = os.getenv("APP_SECRET", "").strip() or self.app_password
        # Token geçerlilik süresi (gün). Süresi geçmiş token 401 döner.
        self.token_ttl_days: int = int(_env("NEWSRADAR_TOKEN_TTL_DAYS", "30"))
        # ANONİM CİHAZ OTURUMU cookie'si (HttpOnly). Frontend+backend Render'da farklı
        # subdomain (cross-origin) → cookie'nin fetch'te gitmesi için SameSite=None+Secure
        # gerekir (aynı-origin'de "lax" yeter). Yerelde (http) Secure kapatılabilir.
        self.session_cookie_name: str = _env("NEWSRADAR_SESSION_COOKIE", "nr_device")
        self.cookie_samesite: str = _env("NEWSRADAR_COOKIE_SAMESITE", "none").lower()
        self.cookie_secure: bool = _env("NEWSRADAR_COOKIE_SECURE", "on").lower() == "on"
        self.session_cookie_days: int = int(_env("NEWSRADAR_SESSION_COOKIE_DAYS", "365"))
        # Kayıt sınırı: en fazla bu kadar hesap (anonim dahil). 0 = sınırsız.
        # Herkese açık: yüksek ama sonlu (kötüye kullanım + maliyet tavanı).
        self.max_users: int = int(_env("NEWSRADAR_MAX_USERS", "500"))
        # KADEMELİ kişi-başı kotalar (admin muaf; 0 = sınırsız).
        # Anonim (cihaz oturumu) < kayıtlı (hesap oluşturmuş) < admin.
        self.max_entities_anon: int = int(_env("NEWSRADAR_MAX_ENTITIES_ANON", "3"))
        self.max_entities_registered: int = int(_env("NEWSRADAR_MAX_ENTITIES_REGISTERED", "10"))
        self.max_refresh_anon: int = int(_env("NEWSRADAR_MAX_REFRESH_ANON", "1"))
        self.max_refresh_registered: int = int(_env("NEWSRADAR_MAX_REFRESH_REGISTERED", "3"))
        # SİSTEM GENELİ maliyet güvencesi (asıl koruma):
        # daily_budget_usd: UTC gününde toplam LLM harcama tavanı (USD; 0 = sınırsız).
        #   Maliyet çağrı başına model fiyat tablosundan hesaplanır (analysis/model_specs.py).
        #   Dolunca yeni analiz durur (tarama ortasında da), kullanıcıya mesaj gösterilir.
        # daily_entity_add_cap: sistem geneli günlük yeni entity ekleme sınırı (biri 500
        #   şirket ekleyip bütçeyi yakmasın; 0 = sınırsız).
        self.daily_budget_usd: float = float(_env("NEWSRADAR_DAILY_BUDGET_USD", "1.50"))
        self.daily_entity_add_cap: int = int(_env("NEWSRADAR_DAILY_ENTITY_ADD_CAP", "300"))
        # Anonim oturum oluşturma: IP başına saatlik sınır (cookie silip sonsuz "yeni
        # kullanıcı" üretilmesin).
        self.anon_sessions_per_ip_hour: int = int(_env("NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR", "10"))
        # Geri bildirim: IP başına saatlik sınır (spam koruması; 0 = sınırsız).
        self.feedback_per_ip_hour: int = int(_env("NEWSRADAR_FEEDBACK_PER_IP_HOUR", "5"))

        # LLM seçimi (GERİ DÖNÜLEBİLİR): anthropic (varsayılan) → Claude; başka her değer
        # (openrouter/nvidia/…) → OpenAI-uyumlu endpoint. Geri dönüş:
        # NEWSRADAR_LLM_PROVIDER=openrouter (+ NEWSRADAR_LLM_* ayarları aşağıda).
        self.llm_provider: str = _env("NEWSRADAR_LLM_PROVIDER", "anthropic").lower()
        # Claude modelleri — KULLANIM AMACINA göre üç ayrı ayar (yalnızca provider=anthropic).
        # Geçerli adlar + fiyat/sınırlar: app/analysis/model_specs.py. Geçersiz ad 404 →
        # ModelNotFoundError; `python -m app.cli llm-check` her birini doğrular.
        #   article    : makale-batch analizi (hacimli sınıflandırma/çıkarım)
        #   assessment : entity değerlendirmesi (kullanıcının okuduğu TR+EN metin)
        #   chat       : sohbet (SSE)
        self.article_model: str = _env("NEWSRADAR_ARTICLE_MODEL", "claude-haiku-5-5")
        self.assessment_model: str = _env("NEWSRADAR_ASSESSMENT_MODEL", "claude-haiku-5-5")
        self.chat_model: str = _env("NEWSRADAR_CHAT_MODEL", "claude-haiku-5-5")
        # OpenAI-uyumlu endpoint ayarları. Varsayılan: OpenRouter.
        self.llm_base_url: str = _env("NEWSRADAR_LLM_BASE_URL", "https://openrouter.ai/api/v1")
        self.llm_model: str = _env("NEWSRADAR_LLM_MODEL", "meta-llama/llama-3.3-70b-instruct")
        # OpenAI-uyumlu endpoint anahtarı (OpenRouter/NVIDIA/… — hangisini kullanıyorsan).
        self.llm_api_key: str = os.getenv("NEWSRADAR_LLM_API_KEY", "").strip()
        self.lookback_hours: int = int(_env("NEWSRADAR_LOOKBACK_HOURS", "48"))
        self.scheduler_enabled: bool = _env("NEWSRADAR_SCHEDULER", "on").lower() == "on"
        # Otomatik yenileme aralığı (saat). Saatlik çok agresif; varsayılan 6.
        self.scheduler_hours: int = max(1, int(_env("NEWSRADAR_SCHEDULER_HOURS", "6")))
        # NewsAPI ücretsiz katman günlük istek sınırı (rolling 24s).
        self.newsapi_daily_limit: int = int(_env("NEWSAPI_DAILY_LIMIT", "100"))

        # Analiz performans/maliyet ayarları (hepsi env'den; kod değişikliği gerekmez).
        # batch_size: tek Claude çağrısında kaç makale analiz edilir.
        # max_articles_per_entity: tek yenilemede entity başına tavan (en yeniler öncelikli).
        # analysis_concurrency: aynı anda kaç Claude çağrısı (semaphore; rate limit için).
        # batch_size: tek Claude çağrısında kaç makale. DİKKAT: büyüyen çıktı şeması
        # (co_mentioned_entities + why_relevant) makale başına ~300 token → 25 makale
        # 4096 max_tokens'a sığmaz, yanıt kesilir. Güvenli varsayılan 10.
        self.batch_size: int = int(_env("NEWSRADAR_BATCH_SIZE", "10"))
        # Entity başına analiz edilecek makale tavanı. Geniş kanıt tabanı için yüksek
        # varsayılan; 0 = SINIRSIZ (birikmiş tüm bekleyen makaleler analiz edilir).
        # DİKKAT: yalnızca analyzed=False makaleler işlenir → tekrar analiz olmaz.
        self.max_articles_per_entity: int = int(
            _env("NEWSRADAR_MAX_ARTICLES_PER_ENTITY", "200")
        )
        self.analysis_concurrency: int = int(_env("NEWSRADAR_ANALYSIS_CONCURRENCY", "5"))
        # Makale-batch Claude çağrısı için üretim (output) token tavanı. Batch büyük
        # ya da şema genişse artırın; yanıt kesilirse (stop_reason=max_tokens) hata verir.
        # Türkçe çıktı İngilizceden ~%50 fazla token yer; kesilmeyi önlemek için yüksek
        # tavan (model bağlamı geniş, çıktı tavanı maliyeti artırmaz — yalnızca kesilmeyi önler).
        self.max_output_tokens: int = int(_env("NEWSRADAR_MAX_OUTPUT_TOKENS", "16384"))

        # Deploy: frontend'in domain'i (CORS). Virgülle birden fazla verilebilir.
        # Boşsa yalnızca yerel Vite (localhost:5173) izinli. "*" = tümüne izin.
        self.frontend_url: str = _env("FRONTEND_URL", "")
        # Deploy: açılışta varsayılan izleme listesini otomatik ekle (idempotent).
        # Kalıcı olmayan diskte (Render bedava katman) DB boş başlamasın diye faydalı.
        self.seed_on_start: bool = _env("NEWSRADAR_SEED_ON_START", "off").lower() == "on"

        db = _env("NEWSRADAR_DB", "newsradar.db")
        db_path = Path(db)
        if not db_path.is_absolute():
            db_path = _BACKEND_ROOT / db_path
        self.db_path: Path = db_path
        self.database_url: str = f"sqlite:///{self.db_path}"

    @property
    def cors_origins(self) -> list[str]:
        """CORS izinli origin listesi: yerel dev + FRONTEND_URL (varsa)."""
        dev = ["http://localhost:5173", "http://127.0.0.1:5173"]
        if not self.frontend_url:
            return dev
        extra = [o.strip().rstrip("/") for o in self.frontend_url.split(",") if o.strip()]
        if "*" in extra:
            return ["*"]  # esnek kaçış: tüm origin'lere izin
        return dev + extra

    # --- Sağlayıcı erişilebilirliği (anahtar var mı?) ---
    @property
    def finnhub_available(self) -> bool:
        return bool(self.finnhub_api_key)

    @property
    def newsapi_available(self) -> bool:
        return bool(self.newsapi_key)

    @property
    def fmp_available(self) -> bool:
        return bool(self.fmp_api_key)

    @property
    def claude_available(self) -> bool:
        return bool(self.anthropic_api_key)

    def model_for(self, purpose: str) -> str:
        """Kullanım amacına göre Claude model adı ('article' | 'assessment' | 'chat')."""
        return {
            "article": self.article_model,
            "assessment": self.assessment_model,
            "chat": self.chat_model,
        }[purpose]

    @property
    def llm_available(self) -> bool:
        """AKTİF analiz motorunun anahtarı var mı (sağlayıcıya göre)."""
        if self.llm_provider == "anthropic":
            return self.claude_available
        return bool(self.llm_api_key)

    # --- Kademeli kota yardımcıları (0 = sınırsız) ---
    def entity_limit_for(self, user) -> int:
        """Kullanıcının izleme listesi üst sınırı (admin=sınırsız, anon<kayıtlı)."""
        if getattr(user, "is_admin", False):
            return 0
        if getattr(user, "is_anonymous", False):
            return self.max_entities_anon
        return self.max_entities_registered

    def refresh_limit_for(self, user) -> int:
        """Kullanıcının 24 saatlik elle yenileme hakkı (admin=sınırsız)."""
        if getattr(user, "is_admin", False):
            return 0
        if getattr(user, "is_anonymous", False):
            return self.max_refresh_anon
        return self.max_refresh_registered


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Uygulama boyunca tek Settings örneği döner."""
    return Settings()
