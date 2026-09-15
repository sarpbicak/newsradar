"""Geri bildirim ucu: POST /feedback (HERKESE AÇIK — anon da yazabilir).

Kimlik doğrulama ZORUNLU değil: token varsa user_id kaydedilir, yoksa anonim.
Spam koruması: IP başına saatlik sınır (ephemeral; IP saklanmaz). Mesaj boş olamaz
ve uzunluk sınırı vardır (schema). Yalnızca admin okur (routes_admin).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db
from ..db.models import Feedback, User
from ..security import get_client_ip
from ..session import AnonCreateLimiter
from .routes_auth import get_current_user
from .schemas import FeedbackAck, FeedbackIn
from .usage import record_event

router = APIRouter(tags=["feedback"])

# IP başına saatlik geri bildirim sınırı (AnonCreateLimiter aynı pencere mantığını verir).
_feedback_limiter = AnonCreateLimiter(per_hour=get_settings().feedback_per_ip_hour)


def device_from_user_agent(ua: str | None) -> str:
    """User-Agent'tan kaba cihaz sınıfı: 'mobil' | 'masaüstü' | 'bilinmiyor'."""
    if not ua:
        return "bilinmiyor"
    low = ua.lower()
    if any(k in low for k in ("mobi", "android", "iphone", "ipod", "windows phone")):
        return "mobil"
    if "ipad" in low or "tablet" in low:
        return "mobil"  # tablet de dokunmatik/mobil deneyim tarafında
    return "masaüstü"


def _optional_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    """Token varsa kullanıcıyı çöz; yoksa/geçersizse None (401 ATMAZ)."""
    if not authorization:
        return None
    try:
        return get_current_user(authorization=authorization, db=db)
    except HTTPException:
        return None


@router.post("/feedback", response_model=FeedbackAck)
def submit_feedback(
    payload: FeedbackIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(_optional_user),
) -> FeedbackAck:
    """Geri bildirim kaydet. Anon ya da kayıtlı; user_id varsa bağlanır."""
    ip = get_client_ip(request)
    if not _feedback_limiter.allow(ip):
        raise HTTPException(
            status_code=429,
            detail="Çok fazla geri bildirim gönderildi — biraz sonra tekrar deneyin.",
        )
    ua = (request.headers.get("user-agent") or "")[:300] or None
    fb = Feedback(
        user_id=user.id if user else None,
        message=payload.message,     # schema strip + uzunluk doğruladı
        contact=payload.contact,     # schema temizledi (boşsa None)
        user_agent=ua,
    )
    db.add(fb)
    db.flush()
    if user is not None:
        record_event(db, user.id, "feedback_sent", {"feedback_id": fb.id})
    return FeedbackAck(ok=True)
