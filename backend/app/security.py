"""Güvenlik yardımcıları: sır maskeleme, giriş hız sınırı, istemci IP.

- mask_secrets: log/hata mesajlarındaki apiKey/token/password gibi query parametrelerini
  ve çıplak sağlayıcı anahtarlarını (sk-ant-*, sk-or-v1-*, nvapi-*) ***'la maskeler.
- install_log_masking: tüm log kayıtlarını mask_secrets'ten geçiren filtre (kök handler'lara).
- LoginRateLimiter: IP başına başarısız giriş denemesini sınırlar (kaba kuvvet).
- get_client_ip: proxy (Render) arkasında gerçek IP (X-Forwarded-For).
- prune_ip_records: kötüye kullanım önleme kayıtlarındaki IP'leri N gün sonra siler.
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


# Çıplak sağlayıcı anahtarları. Anthropic anahtarının TÜRÜ ne olursa olsun (sk-ant-api03-…,
# sk-ant-usr-…, sk-ant-admin01-…) sk-ant- ile başlayan her anahtar maskelenir; tür öneki
# teşhis için görünür kalır. Tür segmenti olmayan sk-ant-… için yedek desen.
_PROVIDER_KEY_RE = re.compile(
    r"\b(sk-ant-[a-z]+[0-9]*-|sk-or-v1-|nvapi-)[A-Za-z0-9_-]{8,}"
    r"|\b(sk-ant-)[A-Za-z0-9_-]{16,}"
)


def _mask_key(m: re.Match) -> str:
    return f"{m.group(1) or m.group(2)}***"


def mask_secrets(text: str) -> str:
    """Bir metindeki sır query parametrelerini ve çıplak sağlayıcı anahtarlarını maskeler."""
    if not text:
        return text
    text = _QS_SECRET_RE.sub(r"\1***", str(text))
    return _PROVIDER_KEY_RE.sub(_mask_key, text)


mask_url_secrets = mask_secrets  # geriye uyum adı


class SecretMaskingFilter(logging.Filter):
    """Log kaydının biçimlenmiş mesajını mask_secrets'ten geçirir (args dahil)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 — bozuk format: kaydı olduğu gibi bırak
            return True
        masked = mask_secrets(msg)
        if masked != msg:
            record.msg, record.args = masked, None
        return True


def install_log_masking() -> None:
    """Kök logger'ın handler'larına maskeleme filtresi ekler (idempotent).

    Logger düzeyindeki filtreler alt logger'lardan yayılan kayıtlara uygulanmaz; handler
    düzeyindeki filtreler hepsine uygulanır. logging.basicConfig'ten SONRA çağrılmalı.
    httpx/httpx2 (Anthropic SDK 1.x) URL loglamasını da WARNING'e çeker."""
    for name in ("httpx", "httpcore", "httpx2", "httpcore2", "openai", "anthropic"):
        logging.getLogger(name).setLevel(logging.WARNING)
    for h in logging.getLogger().handlers:
        if not any(isinstance(f, SecretMaskingFilter) for f in h.filters):
            h.addFilter(SecretMaskingFilter())


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


# Başarısız giriş/kayıt olaylarında detail.ip tutulur (admin panelinde kötüye kullanım
# incelemesi için) — saklama süresi sonunda yalnızca 'ip' alanı silinir, olay kalır.
_IP_EVENT_TYPES = ("login_failed", "register_failed")


def prune_ip_records(days: int | None = None) -> dict:
    """GİZLİLİK: `days` günden eski IP kayıtlarını siler. {'login_rate': n, 'events': m}.

    - login_rate: son güncellemesi eski VE kilidi bitmiş satırlar (IP ve 'user:' anahtarları).
      Başarılı giriş satırı zaten anında siler; bu, yalnızca başarısız deneme kalan IP'ler için.
    - usage_events (login_failed / register_failed): detail.ip alanı çıkarılır, olay korunur.
    Bellek-içi sınırlayıcılar (anonim oturum, geri bildirim) diske yazmaz; 1 saatlik pencere.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete as _delete, select as _select

    from .config import get_settings
    from .db.database import session_scope
    from .db.models import LoginRate, UsageEvent

    days = days if days is not None else get_settings().ip_retention_days
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=days)
    with session_scope() as s:
        res = s.execute(
            _delete(LoginRate).where(LoginRate.updated_at < cutoff,
                                     LoginRate.locked_until < time.time())
        )
        n_rate = res.rowcount or 0
        n_events = 0
        for ev in s.scalars(
            _select(UsageEvent).where(UsageEvent.event_type.in_(_IP_EVENT_TYPES),
                                      UsageEvent.created_at < cutoff)
        ):
            if isinstance(ev.detail, dict) and "ip" in ev.detail:
                ev.detail = {k: v for k, v in ev.detail.items() if k != "ip"}  # yeni dict → değişiklik algılanır
                n_events += 1
    if n_rate or n_events:
        logger.info("[gizlilik] %d günden eski IP kayıtları silindi: login_rate=%d, olay=%d",
                    days, n_rate, n_events)
    return {"login_rate": n_rate, "events": n_events}
