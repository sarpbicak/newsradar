"""Güvenlik yardımcıları: sır maskeleme, giriş hız sınırı, istemci IP.

- mask_url_secrets: log/hata mesajlarındaki apiKey/token/password gibi query
  parametrelerini ***'la maskeler (anahtar sızıntısını önler).
- LoginRateLimiter: IP başına başarısız giriş denemesini sınırlar (kaba kuvvet).
- get_client_ip: proxy (Render) arkasında gerçek IP (X-Forwarded-For).
"""

from __future__ import annotations

import logging
import re
import time

logger = logging.getLogger("newsradar.security")

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
    """İstemci IP'si — Render/proxy arkasında X-Forwarded-For'un İLK (en sol) adresi.

    RENDER: gerçek istemci IP'si XFF'in İLK adresidir (Render access log'unda da bunu
    gösterir). SON (en sağ) adresi almak Render'ın DEĞİŞEN iç proxy IP'sini verir → her
    istek 'yeni IP' sayılır ve hız sayacı hiç birikmez (canlıda yaşanan boşluk buydu).

    NOT (spoofing): teoride istemci kendi X-Forwarded-For'unu yollayıp ilk adresi
    değiştirebilir; ancak Render kenarı XFF'i kendi belirlediği istemci IP'siyle kurar.
    Çok katmanlı/güvenilmez proxy senaryosunda güvenilir-proxy derinliği ayarlanmalı.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[0]
    return request.client.host if request.client else "unknown"


class LoginRateLimiter:
    """IP başına başarısız giriş sınırı: `max_fails` / `window_s` aşılırsa `lock_s` kilit.

    KALICI (DB-tabanlı, login_rate tablosu): süreç yeniden başlasa da (Render free tier
    soğuk-başlangıç/redeploy) sayaç ve kilit korunur. Her metod kendi kısa transaction'ını
    açar (istek session'ından bağımsız → 401 rollback'i sayacı silmez). SQLite yazmayı
    serialize eder; küçük yarışlar en fazla ±1 sayar, kilit yine tetiklenir.
    """

    def __init__(self, max_fails: int = 5, window_s: int = 60, lock_s: int = 900) -> None:
        self.max_fails = max_fails
        self.window_s = window_s
        self.lock_s = lock_s

    def locked_seconds(self, ip: str) -> int:
        """IP kilitliyse kalan saniye, değilse 0."""
        from .db.database import session_scope
        from .db.models import LoginRate
        with session_scope() as s:
            row = s.get(LoginRate, ip)
            if row is None:
                return 0
            remaining = row.locked_until - time.time()
            return int(remaining) if remaining > 0 else 0

    def record_failure(self, ip: str) -> None:
        """Başarısız denemeyi kaydet (KALICI); eşik aşılırsa IP'yi kilitle."""
        import json
        from datetime import datetime, timezone
        from .db.database import session_scope
        from .db.models import LoginRate
        now = time.time()
        with session_scope() as s:
            row = s.get(LoginRate, ip)
            if row is None:
                row = LoginRate(ip=ip, attempts="[]", locked_until=0.0)
                s.add(row)
            try:
                prev = [t for t in json.loads(row.attempts or "[]") if now - t < self.window_s]
            except (ValueError, TypeError):
                prev = []
            prev.append(now)
            n = len(prev)
            row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            if n >= self.max_fails:
                row.locked_until = now + self.lock_s
                row.attempts = "[]"  # sıfırla; kilit süresi işliyor
                logger.warning(
                    "[rate-limit] IP=%s KİLİTLENDİ (%d/%d başarısız, %d dk)",
                    ip, n, self.max_fails, self.lock_s // 60,
                )
            else:
                row.attempts = json.dumps(prev)
                # HER başarısız denemede sayacı logla (canlıda birikimi görebilmek için).
                logger.warning("[rate-limit] IP=%s sayaç=%d/%d", ip, n, self.max_fails)

    def record_success(self, ip: str) -> None:
        """Başarılı giriş → o IP'nin sayaç/kilidini temizle."""
        from .db.database import session_scope
        from .db.models import LoginRate
        with session_scope() as s:
            row = s.get(LoginRate, ip)
            if row is not None:
                s.delete(row)

    def reset_all(self) -> None:
        """TEST/ADMIN: tüm hız-sınırı durumunu temizle."""
        from sqlalchemy import delete as _delete
        from .db.database import session_scope
        from .db.models import LoginRate
        with session_scope() as s:
            s.execute(_delete(LoginRate))


# Giriş uçları (genel şifre + kişisel giriş + kayıt) için ortak IP sınırlayıcı.
login_limiter = LoginRateLimiter()

# HESAP-BAZLI sınırlayıcı (XFF spoofing'e karşı savunma): saldırgan her istekte farklı
# sahte X-Forwarded-For göndererek IP sayacını atlayabilir (get_client_ip XFF'e güvenir,
# Render arkasında bunu tam doğrulayamayız). Bu yüzden /users/login'de HEDEF KULLANICI
# ADINA göre de sayaç tutulur ("user:<ad>" anahtarı) → tek hesaba dönük kaba kuvvet, IP
# ne olursa olsun kilitlenir. Eşik IP'den yüksek (kazara kendini kilitleme riskini azaltır),
# pencere uzun (yavaş/dağıtık denemeleri de yakalar). login_rate tablosunu paylaşır;
# anahtarlar IP'lerle çakışmaz. (Kabul edilen ödünleşme: bir saldırgan bir hesabı geçici
# kilitleyerek DoS yapabilir — hesap ele geçirmeye karşı bu tercih edilir.)
account_limiter = LoginRateLimiter(max_fails=10, window_s=900, lock_s=900)


def account_key(username: str) -> str:
    """Hesap-bazlı hız sayacı anahtarı (IP anahtarlarıyla çakışmayan ad-alanı)."""
    return f"user:{username.strip().lower()}"
