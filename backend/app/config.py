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

        self.model: str = _env("NEWSRADAR_MODEL", "claude-sonnet-4-6")
        self.lookback_hours: int = int(_env("NEWSRADAR_LOOKBACK_HOURS", "48"))
        self.scheduler_enabled: bool = _env("NEWSRADAR_SCHEDULER", "on").lower() == "on"

        db = _env("NEWSRADAR_DB", "newsradar.db")
        db_path = Path(db)
        if not db_path.is_absolute():
            db_path = _BACKEND_ROOT / db_path
        self.db_path: Path = db_path
        self.database_url: str = f"sqlite:///{self.db_path}"

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
