"""Güvenlik yardımcıları: sır maskeleme, giriş hız sınırı, istemci IP.

- mask_url_secrets: log/hata mesajlarındaki apiKey/token/password gibi query
  parametrelerini ***'la maskeler (anahtar sızıntısını önler).
- LoginRateLimiter: IP başına başarısız giriş denemesini sınırlar (kaba kuvvet).
- get_client_ip: proxy (Render) arkasında gerçek IP (X-Forwarded-For).
"""

from __future__ import annotations

import re
import threading
import time

# Query parametresi olarak sır taşıyan anahtar adları (küçük harf karşılaştırılır).
_SECRET_PARAMS = ("apikey", "api_key", "key", "token", "password", "secret", "access_token")
_QS_SECRET_RE = re.compile(
    r"(?i)([?&](?:" + "|".join(_SECRET_PARAMS) + r")=)[^&\s]+"
)


def mask_url_secrets(text: str) -> str:
    """Bir metindeki (URL/hata) sır query parametrelerini ***'la maskeler."""
    if not text:
        return text
    return _QS_SECRET_RE.sub(r"\1***", str(text))


def get_client_ip(request) -> str:
    """İstemci IP'si — Render/proxy arkasında X-Forwarded-For'un İLK adresi."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class LoginRateLimiter:
    """IP başına başarısız giriş sınırı: `max_fails` / `window_s` aşılırsa `lock_s` kilit.

    Bellek-içi (tek instance; Render free tier tek süreç). Süreç yeniden başlarsa sıfırlanır
    — kaba kuvvete karşı yeterli; kalıcı kilit gerekmiyor. Thread-güvenli.
    """

    def __init__(self, max_fails: int = 5, window_s: int = 60, lock_s: int = 900) -> None:
        self.max_fails = max_fails
        self.window_s = window_s
        self.lock_s = lock_s
        self._lock = threading.Lock()
        self._fails: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}

    def locked_seconds(self, ip: str) -> int:
        """IP kilitliyse kalan saniye, değilse 0."""
        with self._lock:
            until = self._locked_until.get(ip, 0)
            remaining = until - time.time()
            return int(remaining) if remaining > 0 else 0

    def record_failure(self, ip: str) -> None:
        """Başarısız denemeyi kaydet; eşik aşılırsa IP'yi kilitle."""
        now = time.time()
        with self._lock:
            fails = [t for t in self._fails.get(ip, []) if now - t < self.window_s]
            fails.append(now)
            self._fails[ip] = fails
            if len(fails) >= self.max_fails:
                self._locked_until[ip] = now + self.lock_s
                self._fails[ip] = []  # sıfırla; kilit süresi işliyor

    def record_success(self, ip: str) -> None:
        with self._lock:
            self._fails.pop(ip, None)
            self._locked_until.pop(ip, None)


# Giriş uçları (genel şifre + kişisel giriş + kayıt) için ortak sınırlayıcı.
login_limiter = LoginRateLimiter()
