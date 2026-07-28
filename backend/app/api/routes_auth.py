"""Basit paylaşılan-şifre kapısı: POST /auth/login + `require_auth` bağımlılığı.

İki kişilik kişisel araç için tam bir auth sistemi değil, tek ortak parola yeter.
Parola yalnızca backend'de (`.env` → APP_PASSWORD) tutulur ve karşılaştırma burada
sabit-zamanlı (`hmac.compare_digest`) yapılır; frontend'e parola hiç gitmez.

Token durumsuz: parolanın (sabit ön ek + parola) SHA-256 özeti. Böylece sunucu
yeniden başlasa da token geçerli kalır ve token parolayı ifşa etmez. Frontend bu
token'ı `Authorization: Bearer <token>` başlığında geri gönderir.
"""

from __future__ import annotations

import hashlib
import hmac

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db
from ..db.models import User

router = APIRouter(tags=["auth"])


# --------------------------- Şifre hash (bcrypt) --------------------------- #
def hash_password(plain: str) -> str:
    """Kişisel şifreyi bcrypt ile hash'ler (düz metin ASLA saklanmaz)."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Düz şifreyi bcrypt hash'iyle karşılaştırır (sabit-zamanlı)."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ----------------------- Kişisel token (Katman 2) ------------------------- #
# Durumsuz, imzalı token: "<user_id>.<hmac_sha256(app_password, 'user:<id>')>".
# app_password imza anahtarı olarak kullanılır (zaten gizli); token user_id'yi taşır
# ve sunucu yeniden başlasa da geçerli kalır. Şifre/hash token'a girmez.
def make_user_token(user_id: int) -> str:
    secret = get_settings().app_password
    sig = hmac.new(secret.encode(), f"user:{user_id}".encode(), hashlib.sha256).hexdigest()
    return f"{user_id}.{sig}"


def _user_id_from_token(token: str, secret: str) -> int | None:
    parts = token.split(".", 1)
    if len(parts) != 2 or not parts[0].isdigit():
        return None
    uid, sig = parts
    expected = hmac.new(secret.encode(), f"user:{uid}".encode(), hashlib.sha256).hexdigest()
    return int(uid) if hmac.compare_digest(sig, expected) else None


def _bearer(authorization: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Veri uçları için bağımlılık: geçerli KİŞİSEL token yoksa 401. User döner."""
    settings = get_settings()
    if not settings.app_password:
        raise HTTPException(status_code=503, detail="APP_PASSWORD ayarlanmamış; giriş devre dışı.")
    token = _bearer(authorization)
    uid = _user_id_from_token(token, settings.app_password) if token else None
    if uid is None:
        raise HTTPException(status_code=401, detail="Geçersiz veya eksik oturum. Lütfen giriş yapın.")
    user = db.get(User, uid)
    if user is None:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı. Lütfen tekrar giriş yapın.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Admin-only uçlar için: kullanıcı admin değilse 403."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Bu alan yalnızca yöneticiye açık.")
    return user


def _expected_token(password: str) -> str:
    """Paroladan türetilen durumsuz oturum token'ı (parolayı ifşa etmez)."""
    return hashlib.sha256(f"newsradar-auth:{password}".encode()).hexdigest()


class LoginIn(BaseModel):
    password: str


class LoginOut(BaseModel):
    token: str


@router.post("/auth/login", response_model=LoginOut)
def login(payload: LoginIn) -> LoginOut:
    """Parolayı doğrular; doğruysa oturum token'ı döner, yanlışsa 401."""
    settings = get_settings()
    if not settings.app_password:
        raise HTTPException(
            status_code=503,
            detail="APP_PASSWORD ayarlanmamış. backend/.env dosyasına ekleyin.",
        )
    if not hmac.compare_digest(payload.password, settings.app_password):
        raise HTTPException(status_code=401, detail="Yanlış şifre.")
    return LoginOut(token=_expected_token(settings.app_password))


def require_auth(authorization: str | None = Header(default=None)) -> None:
    """Korumalı uçlar için bağımlılık: geçerli Bearer token yoksa erişimi reddeder."""
    settings = get_settings()
    if not settings.app_password:
        raise HTTPException(
            status_code=503,
            detail="APP_PASSWORD ayarlanmamış; giriş devre dışı.",
        )
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    expected = _expected_token(settings.app_password)
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=401, detail="Geçersiz veya eksik oturum. Lütfen giriş yapın."
        )
