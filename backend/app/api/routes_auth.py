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

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..config import get_settings

router = APIRouter(tags=["auth"])


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
