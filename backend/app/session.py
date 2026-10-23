"""Anonim cihaz oturumu servisi.

Kullanıcı şifre girmeden kullanabilir: ilk ziyarette rastgele device_id üretilir,
HttpOnly cookie'ye yazılır, DB'de bir ANON kullanıcı satırı açılır. IP KİMLİK OLARAK
KULLANILMAZ (CGNAT/mobil sorunları + GDPR). device_id'nin DÜZ hali saklanmaz — yalnızca
sha256'sı (device_id_hash) tutulur.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db.models import User


def new_device_id() -> str:
    """Kriptografik rastgele, tahmin edilemez cihaz kimliği (≥32 byte)."""
    return secrets.token_urlsafe(32)


def hash_device_id(device_id: str) -> str:
    return hashlib.sha256(device_id.encode("utf-8")).hexdigest()


def find_user_by_device(db: Session, device_id: str) -> User | None:
    return db.scalar(
        select(User).where(User.device_id_hash == hash_device_id(device_id))
    )


def create_anonymous_user(db: Session, device_id: str, language: str = "tr") -> User:
    """Yeni anonim kullanıcı satırı: sentetik username ('anon:<hash8>', insan kaydedemez —
    kayıt regex'i ':' içermez), kullanılamaz rastgele şifre hash'i, is_anonymous=True.
    language: tarayıcı diline göre varsayılan (kullanıcı sonra modal'dan değiştirir)."""
    from .api.routes_auth import hash_password

    dh = hash_device_id(device_id)
    user = User(
        username=f"anon:{dh[:12]}",
        password_hash=hash_password(secrets.token_urlsafe(16)),  # login'de kullanılamaz
        is_anonymous=True,
        device_id_hash=dh,
        language=language if language in ("tr", "en") else "tr",
    )
    db.add(user)
    db.flush()
    return user


class AnonCreateLimiter:
    """Anonim oturum OLUŞTURMA hızını IP başına sınırlar (cookie silip sonsuz 'yeni
    kullanıcı' üretilmesin). BELLEK-İÇİ + EPHEMERAL — IP kalıcı SAKLANMAZ (GDPR).
    Süreç yeniden başlarsa sıfırlanır (anti-abuse için yeterli)."""

    def __init__(self, per_hour: int | None = None) -> None:
        # None → NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR (varsayılan 10; 0 = sınırsız). Her
        # kontrolde ayardan okunur: modül import edilirken değer dondurulmaz.
        self._per_hour = per_hour
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = {}

    @property
    def per_hour(self) -> int:
        if self._per_hour is not None:
            return self._per_hour
        from .config import get_settings
        return get_settings().anon_sessions_per_ip_hour

    def allow(self, ip: str) -> bool:
        if self.per_hour <= 0:
            return True
        now = time.time()
        with self._lock:
            hits = [t for t in self._hits.get(ip, []) if now - t < 3600]
            if len(hits) >= self.per_hour:
                self._hits[ip] = hits
                return False
            hits.append(now)
            self._hits[ip] = hits
            return True


anon_create_limiter = AnonCreateLimiter()
