"""Kişisel hesap uçları (Katman 2): register / login / me.

register+login GENEL ŞİFRE kapısının arkasındadır (require_auth) — yani önce Katman 1
geçilmeli. me KİŞİSEL token ister (get_current_user). Şifreler bcrypt ile hash'lenir.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db, session_scope
from ..db.models import User
from ..security import get_client_ip, login_limiter
from .routes_auth import (
    get_current_user,
    hash_password,
    make_user_token,
    require_auth,
    verify_password,
)
from .schemas import RegisterIn, UserLoginIn, UserOut, UserTokenOut
from .usage import record_event

router = APIRouter(prefix="/users", tags=["users"])

MIN_PASSWORD_LEN = 8
# Kullanıcı adı: alfanumerik + alt çizgi, 3–30 karakter (boşluk/kontrol karakteri yok).
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")


def _check_locked(request: Request) -> None:
    locked = login_limiter.locked_seconds(get_client_ip(request))
    if locked:
        raise HTTPException(status_code=429, detail=f"Çok fazla deneme. {locked // 60 + 1} dk sonra tekrar deneyin.")


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id, username=u.username, is_admin=u.is_admin,
        created_at=u.created_at, last_login_at=u.last_login_at,
        guide_dismissed=u.guide_dismissed, tutorial_done=u.tutorial_done,
    )


def _find_by_username_ci(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.username) == username.lower()))


@router.post("/register", response_model=UserTokenOut, status_code=201,
             dependencies=[Depends(require_auth)])
def register(payload: RegisterIn, request: Request, db: Session = Depends(get_db)) -> UserTokenOut:
    """Yeni kişisel hesap. İlk kullanıcı (ya da ADMIN_USERNAME) admin olur. Hız/sayı sınırlı."""
    _check_locked(request)
    settings = get_settings()
    username = payload.username.strip()
    if not _USERNAME_RE.match(username):
        raise HTTPException(
            status_code=422,
            detail="Kullanıcı adı 3–30 karakter olmalı; yalnızca harf, rakam ve alt çizgi.",
        )
    if len(payload.password) < MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=422, detail=f"Şifre en az {MIN_PASSWORD_LEN} karakter olmalı."
        )
    # Kayıt sayısı sınırı: genel şifreyi bilen biri sınırsız hesap açmasın.
    if settings.max_users > 0:
        n = db.scalar(select(func.count()).select_from(User)) or 0
        if n >= settings.max_users:
            raise HTTPException(status_code=403, detail="Kayıt kapalı — kullanıcı sınırına ulaşıldı.")
    if _find_by_username_ci(db, username) is not None:
        raise HTTPException(status_code=409, detail="Bu kullanıcı adı zaten alınmış.")

    # Admin belirleme: ADMIN_USERNAME eşleşirse ya da hiç kullanıcı yoksa (ilk kayıt).
    admin_username = settings.admin_username
    if admin_username:
        is_admin = username.lower() == admin_username.lower()
    else:
        is_admin = db.scalar(select(func.count()).select_from(User)) == 0

    user = User(username=username, password_hash=hash_password(payload.password), is_admin=is_admin)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Bu kullanıcı adı zaten alınmış.")

    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    record_event(db, user.id, "login", {"via": "register"})
    return UserTokenOut(token=make_user_token(user), user=_user_out(user))


@router.post("/login", response_model=UserTokenOut, dependencies=[Depends(require_auth)])
def login(payload: UserLoginIn, request: Request, db: Session = Depends(get_db)) -> UserTokenOut:
    """Kişisel giriş. Kullanıcı adı büyük/küçük harf duyarsız; şifre bcrypt ile doğrulanır.

    Hız-sınırlı (kaba kuvvet). Hata mesajı kullanıcı adı/şifre ayrımı yapmaz (enum'a karşı)."""
    ip = get_client_ip(request)
    _check_locked(request)
    user = _find_by_username_ci(db, payload.username.strip())
    if user is None or not verify_password(payload.password, user.password_hash):
        login_limiter.record_failure(ip)
        # Var olan bir kullanıcıya yönelik başarısız denemeyi admin panelinde göster.
        # AYRI session: aşağıdaki 401 request session'ını rollback eder → event kaybolmasın.
        if user is not None:
            with session_scope() as s2:
                record_event(s2, user.id, "login_failed", {"ip": ip})
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı.")
    login_limiter.record_success(ip)
    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    record_event(db, user.id, "login", None)
    return UserTokenOut(token=make_user_token(user), user=_user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    """Mevcut kişisel kullanıcı bilgisi (is_admin dahil)."""
    return _user_out(user)


@router.post("/me/guide-dismiss", response_model=UserOut)
def dismiss_guide(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    """"NewsRadar ne yapar?" açıklama kutusunu kalıcı olarak kapat (kullanıcı tercihi)."""
    user.guide_dismissed = True
    return _user_out(user)


@router.post("/me/tutorial-done", response_model=UserOut)
def finish_tutorial(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    """İlk giriş tutorial'ını tamamlandı işaretle (bir daha gösterilmez)."""
    user.tutorial_done = True
    return _user_out(user)
