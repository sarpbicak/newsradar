"""Kişisel hesap uçları (Katman 2): register / login / me.

register+login GENEL ŞİFRE kapısının arkasındadır (require_auth) — yani önce Katman 1
geçilmeli. me KİŞİSEL token ister (get_current_user). Şifreler bcrypt ile hash'lenir.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db
from ..db.models import User
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


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id, username=u.username, is_admin=u.is_admin,
        created_at=u.created_at, last_login_at=u.last_login_at,
    )


def _find_by_username_ci(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.username) == username.lower()))


@router.post("/register", response_model=UserTokenOut, status_code=201,
             dependencies=[Depends(require_auth)])
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> UserTokenOut:
    """Yeni kişisel hesap. İlk kullanıcı (ya da ADMIN_USERNAME) admin olur."""
    username = payload.username.strip()
    if len(username) < 3:
        raise HTTPException(status_code=422, detail="Kullanıcı adı en az 3 karakter olmalı.")
    if len(payload.password) < MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=422, detail=f"Şifre en az {MIN_PASSWORD_LEN} karakter olmalı."
        )
    if _find_by_username_ci(db, username) is not None:
        raise HTTPException(status_code=409, detail="Bu kullanıcı adı zaten alınmış.")

    # Admin belirleme: ADMIN_USERNAME eşleşirse ya da hiç kullanıcı yoksa (ilk kayıt).
    admin_username = get_settings().admin_username
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
    return UserTokenOut(token=make_user_token(user.id), user=_user_out(user))


@router.post("/login", response_model=UserTokenOut, dependencies=[Depends(require_auth)])
def login(payload: UserLoginIn, db: Session = Depends(get_db)) -> UserTokenOut:
    """Kişisel giriş. Kullanıcı adı büyük/küçük harf duyarsız; şifre bcrypt ile doğrulanır."""
    user = _find_by_username_ci(db, payload.username.strip())
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı.")
    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    record_event(db, user.id, "login", None)
    return UserTokenOut(token=make_user_token(user.id), user=_user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    """Mevcut kişisel kullanıcı bilgisi (is_admin dahil)."""
    return _user_out(user)
