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

        # Paylaşılan tek şifre (iki kişilik erişim kapısı). Boşsa giriş devre dışı
        # ve korumalı uçlar 503 döner — yani parola ayarlanmadan kimse giremez.
        self.app_password: str = os.getenv("APP_PASSWORD", "").strip()

        # NOT: Var olmayan bir model adı (ör. eski claude-sonnet-4-6) API'de sessiz
        # boş/404 yanıta yol açıp analizi durdurur. Geçerli, güncel bir model kullanın.
        self.model: str = _env("NEWSRADAR_MODEL", "claude-sonnet-4-5")
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
        self.batch_size: int = int(_env("NEWSRADAR_BATCH_SIZE", "25"))
        self.max_articles_per_entity: int = int(
            _env("NEWSRADAR_MAX_ARTICLES_PER_ENTITY", "25")
        )
        self.analysis_concurrency: int = int(_env("NEWSRADAR_ANALYSIS_CONCURRENCY", "5"))

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
    def claude_available(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Uygulama boyunca tek Settings örneği döner."""
    return Settings()
