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
import time

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db
from ..db.models import User
from ..security import get_client_ip, login_limiter

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
# Durumsuz, imzalı token: "<uid>.<iat>.<hmac_sha256(APP_SECRET, 'uid:iat:pwhash')>".
# - iat (epoch sn): son kullanma süresi (TOKEN_TTL_DAYS) için.
# - pwhash imzaya girer (token'da GÖRÜNMEZ): şifre değişince eski token'lar geçersiz olur.
# - İmza sırrı APP_SECRET (yoksa APP_PASSWORD). Şifre/hash/e-posta token'da TAŞINMAZ.
def _sign(uid: int, iat: int, password_hash: str, secret: str) -> str:
    msg = f"{uid}:{iat}:{password_hash}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def make_user_token(user: User) -> str:
    iat = int(time.time())
    sig = _sign(user.id, iat, user.password_hash, get_settings().app_secret)
    return f"{user.id}.{iat}.{sig}"


def _bearer(authorization: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Veri uçları için bağımlılık: geçerli+süresi dolmamış KİŞİSEL token yoksa 401."""
    settings = get_settings()
    if not settings.app_secret:
        raise HTTPException(status_code=503, detail="APP_SECRET/APP_PASSWORD ayarlanmamış; giriş devre dışı.")
    invalid = HTTPException(status_code=401, detail="Geçersiz veya süresi dolmuş oturum. Lütfen tekrar giriş yapın.")

    token = _bearer(authorization)
    parts = token.split(".") if token else []
    if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
        raise invalid  # eski 2-parçalı token dahil → yeniden giriş
    uid, iat, sig = int(parts[0]), int(parts[1]), parts[2]

    # Süre kontrolü (iat gelecekteyse de reddet — kurcalama).
    now = int(time.time())
    ttl = settings.token_ttl_days * 86400
    if iat > now + 300 or now - iat > ttl:
        raise invalid

    user = db.get(User, uid)
    if user is None:
        raise invalid
    # İmza: kullanıcının GÜNCEL pwhash'iyle doğrula → şifre değiştiyse token geçersiz.
    expected = _sign(uid, iat, user.password_hash, settings.app_secret)
    if not hmac.compare_digest(sig, expected):
        raise invalid
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
def login(payload: LoginIn, request: Request) -> LoginOut:
    """Parolayı doğrular; doğruysa oturum token'ı döner, yanlışsa 401. Hız-sınırlı."""
    settings = get_settings()
    if not settings.app_password:
        raise HTTPException(
            status_code=503,
            detail="APP_PASSWORD ayarlanmamış. backend/.env dosyasına ekleyin.",
        )
    ip = get_client_ip(request)
    locked = login_limiter.locked_seconds(ip)
    if locked:
        raise HTTPException(status_code=429, detail=f"Çok fazla deneme. {locked // 60 + 1} dk sonra tekrar deneyin.")
    # Sabit-zamanlı karşılaştırma (zamanlama saldırısına karşı).
    if not hmac.compare_digest(payload.password, settings.app_password):
        login_limiter.record_failure(ip)
        raise HTTPException(status_code=401, detail="Yanlış şifre.")
    login_limiter.record_success(ip)
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
