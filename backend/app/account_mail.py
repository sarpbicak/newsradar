"""E-posta doğrulama ve şifre sıfırlama: tek kullanımlık token'lar + hız sınırı + gönderim.

- Token: `secrets.token_urlsafe(32)`; DB'de yalnızca sha256'sı (email_tokens.token_hash).
  verify 24 saat, reset 1 saat geçerli; kullanılınca used_at dolar (tekrar kullanılamaz).
- Hız sınırı: rate_events tablosu; anahtar HMAC(APP_SECRET, ip/e-posta) — ham IP ya da adres
  saklanmaz. 1 günden eski olaylar temizlenir.
- Bağlantı kökü yapılandırmadan (Settings.public_url); isteğin Host başlığı kullanılmaz.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .languages import user_language
from .config import get_settings
from .db.models import EmailToken, RateEvent, User
from .email_templates import message
from .mailer import send_email

VERIFY_TTL = timedelta(hours=24)
RESET_TTL = timedelta(hours=1)
RESEND_COOLDOWN_S = 60          # "Tekrar gönder" bekleme süresi
VERIFY_PER_DAY = 10             # kullanıcı başına günlük doğrulama postası
FORGOT_PER_IP_HOUR = 5          # şifre sıfırlama isteği: IP başına saatlik
FORGOT_PER_EMAIL_HOUR = 3       # ve adres başına saatlik (aşılırsa SESSİZCE gönderilmez)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def create_token(db: Session, user: User, purpose: str, email: str | None = None) -> str:
    """Yeni tek kullanımlık token (düz hali döner, yalnızca özeti saklanır)."""
    raw = secrets.token_urlsafe(32)
    ttl = VERIFY_TTL if purpose == "verify" else RESET_TTL
    db.add(EmailToken(user_id=user.id, purpose=purpose, token_hash=_hash(raw), email=email,
                      created_at=_now(), expires_at=_now() + ttl))
    db.flush()
    return raw


def consume_token(db: Session, raw: str, purpose: str) -> EmailToken | None:
    """Geçerli (doğru amaç, süresi dolmamış, kullanılmamış) token'ı kullanılmış işaretler ve
    döner; değilse None. Aynı token ikinci kez None döner."""
    if not raw or len(raw) > 200:
        return None
    tok = db.scalar(select(EmailToken).where(EmailToken.token_hash == _hash(raw),
                                             EmailToken.purpose == purpose))
    if tok is None or tok.used_at is not None or _aware(tok.expires_at) <= _now():
        return None
    tok.used_at = _now()
    db.flush()
    return tok


def invalidate_tokens(db: Session, user_id: int, purpose: str) -> None:
    db.execute(update(EmailToken).where(EmailToken.user_id == user_id, EmailToken.purpose == purpose,
                                        EmailToken.used_at.is_(None)).values(used_at=_now()))


def _link(path: str, raw: str) -> str:
    return f"{get_settings().public_url}{path}?token={raw}"


# --------------------------- Hız sınırı --------------------------- #
def rate_key(kind: str, value: str) -> str:
    digest = hmac.new(get_settings().app_secret.encode(), value.strip().lower().encode(),
                      hashlib.sha256).hexdigest()[:40]
    return f"{kind}:{digest}"


def rate_allow(db: Session, key: str, limit: int, window: timedelta) -> bool:
    """Pencere içindeki olay sayısı sınırın altındaysa olayı kaydedip True döner."""
    db.execute(delete(RateEvent).where(RateEvent.created_at < _now() - timedelta(days=1)))
    n = db.scalar(select(func.count()).select_from(RateEvent)
                  .where(RateEvent.key == key, RateEvent.created_at >= _now() - window)) or 0
    if n >= limit:
        return False
    db.add(RateEvent(key=key, created_at=_now()))
    db.flush()
    return True


# --------------------------- Doğrulama --------------------------- #
def resend_wait_seconds(db: Session, user: User) -> int:
    """Son doğrulama postasından bu yana bekleme süresi dolmadıysa kalan saniye."""
    last = db.scalar(select(func.max(EmailToken.created_at))
                     .where(EmailToken.user_id == user.id, EmailToken.purpose == "verify"))
    if last is None:
        return 0
    left = RESEND_COOLDOWN_S - (_now() - _aware(last)).total_seconds()
    return max(0, int(left + 0.999))


def verification_sends_today(db: Session, user: User) -> int:
    return db.scalar(select(func.count()).select_from(EmailToken).where(
        EmailToken.user_id == user.id, EmailToken.purpose == "verify",
        EmailToken.created_at >= _now() - timedelta(days=1))) or 0


def prepare_verification(db: Session, user: User):
    """Doğrulama token'ı üretir; gönderimi yapan çağrılabilir döner (BackgroundTasks)."""
    raw = create_token(db, user, "verify", user.email)
    msg = message("verify", user_language(user), user.email, user.username, _link("/verify-email", raw))
    return lambda: send_email(msg)


def verify_email(db: Session, raw: str) -> User | None:
    tok = consume_token(db, raw, "verify")
    if tok is None:
        return None
    user = db.get(User, tok.user_id)
    # Bağlantı başka bir adres için üretildiyse (adres sonradan değişti) doğrulama yok.
    if user is None or not user.email or user.email != tok.email:
        return None
    user.email_verified_at = _now()
    return user


# --------------------------- Şifre sıfırlama --------------------------- #
def prepare_reset(db: Session, user: User):
    raw = create_token(db, user, "reset", user.email)
    msg = message("reset", user_language(user), user.email, user.username, _link("/reset-password", raw))
    return lambda: send_email(msg)
