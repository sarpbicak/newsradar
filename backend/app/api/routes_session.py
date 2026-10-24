"""Anonim cihaz oturumu ucu: POST /session/bootstrap.

Herkese açık (şifre GEREKTİRMEZ). Frontend açılışta çağırır:
- device_id cookie'si varsa → o kullanıcıya taze token döner (return-visitor: aynı
  cihazda liste korunur; anon ya da hesaba yükseltilmiş fark etmez).
- yoksa → yeni ANON kullanıcı açar, HttpOnly cookie yazar, token döner.
IP yalnızca oturum-oluşturma hız sınırı için (ephemeral); KİMLİK olarak kullanılmaz.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db
from ..db.models import User
from ..security import get_client_ip
from ..session import (
    anon_create_limiter,
    create_anonymous_user,
    find_user_by_device,
    new_device_id,
)
from .routes_auth import make_user_token
from .routes_users import _user_out
from .schemas import UserTokenOut

router = APIRouter(prefix="/session", tags=["session"])


def _set_device_cookie(response: Response, device_id: str) -> None:
    s = get_settings()
    response.set_cookie(
        key=s.session_cookie_name,
        value=device_id,
        max_age=s.session_cookie_days * 86400,
        httponly=True,               # JS okuyamaz (XSS'e karşı)
        secure=s.cookie_secure,      # yalnızca HTTPS
        samesite=s.cookie_samesite,  # Render (farklı site): "none" · AWS (aynı site): "lax"
        domain=s.cookie_domain,      # AWS: .newsradarapp.com · boş: yalnızca API host'u
        path="/",
    )


@router.post("/bootstrap", response_model=UserTokenOut)
def bootstrap(request: Request, response: Response, db: Session = Depends(get_db, scope="function")) -> UserTokenOut:
    """Cihaz oturumu al/oluştur (şifresiz). Token + kullanıcı döner, cookie'yi tazeler."""
    settings = get_settings()
    device_id = request.cookies.get(settings.session_cookie_name)

    user = find_user_by_device(db, device_id) if device_id else None
    if user is None:
        # Yeni anon oturum — kötüye kullanım/maliyet koruması.
        ip = get_client_ip(request)
        if not anon_create_limiter.allow(ip):
            raise HTTPException(
                status_code=429,
                detail="Çok fazla yeni oturum açıldı, biraz sonra tekrar deneyin.",
            )
        if settings.max_users > 0:
            n = db.scalar(select(func.count()).select_from(User)) or 0
            if n >= settings.max_users:
                raise HTTPException(
                    status_code=503,
                    detail="Site şu an dolu, biraz sonra tekrar deneyin.",
                )
        device_id = new_device_id()
        # Tarayıcı dilini varsayılan öner (Accept-Language "tr..." → tr, aksi halde en).
        accept = (request.headers.get("accept-language") or "").strip().lower()
        default_lang = "tr" if accept.startswith("tr") else "en"
        user = create_anonymous_user(db, device_id, language=default_lang)

    _set_device_cookie(response, device_id)  # süreyi her ziyarette tazele
    return UserTokenOut(token=make_user_token(user), user=_user_out(user))


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    """Çıkış: cihaz cookie'sini siler.

    Neden: misafir hesaba geçince (/users/upgrade) cihaz kimliği aynı kullanıcı satırında
    kalır ("aynı cihazda hatırlanma"). Yalnızca token silinirse bir sonraki /session/bootstrap
    bu cookie ile kayıtlı hesabı SESSİZCE geri getirir (çıkış olmaz). Cookie silinince
    bootstrap yeni bir misafir oluşturur. Kimlik doğrulama gerektirmez (yalnızca cookie siler)."""
    s = get_settings()
    response.status_code = 204
    response.delete_cookie(
        key=s.session_cookie_name, path="/", domain=s.cookie_domain,
        secure=s.cookie_secure, httponly=True, samesite=s.cookie_samesite,
    )
    return response

