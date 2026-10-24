"""Kişisel hesap uçları (Katman 2): register / login / me.

register+login GENEL ŞİFRE kapısının arkasındadır (require_auth) — yani önce Katman 1
geçilmeli. me KİŞİSEL token ister (get_current_user). Şifreler bcrypt ile hash'lenir.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db, session_scope
from ..db.models import User
from ..security import account_key, account_limiter, get_client_ip, login_limiter
from .routes_auth import (
    get_current_user,
    hash_password,
    make_user_token,
    require_auth,
    verify_password,
)
from .schemas import EmailIn, RegisterIn, UserLoginIn, UserOut, UserTokenOut
from .usage import record_event

router = APIRouter(prefix="/users", tags=["users"])
logger = logging.getLogger("newsradar.security")

MIN_PASSWORD_LEN = 8
# Kullanıcı adı: alfanumerik + alt çizgi, 3–30 karakter (boşluk/kontrol karakteri yok).
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")

# YARIŞ KORUMASI: kayıt sayımı + insert + commit'i process içinde SERİLEŞTİR. count-
# then-insert atomik olmadığı için iki eşzamanlı kayıt limiti aşabiliyordu (test edildi:
# 1 slot varken 2 eşzamanlı kayıt → 3 kullanıcı). uvicorn tek-process çok-thread
# çalıştığı için threading.Lock yeterli; kritik bölüm kilit İÇİNDE commit'lenir ki
# sonraki thread taze (commit'lenmiş) sayıyı görsün.
_register_lock = threading.Lock()


def _check_locked(request: Request) -> None:
    locked = login_limiter.locked_seconds(get_client_ip(request))
    if locked:
        raise HTTPException(status_code=429, detail=f"Çok fazla deneme. {locked // 60 + 1} dk sonra tekrar deneyin.")


def _record_register_failed(reason: str, attempted: str, request: Request) -> None:
    """Başarısız kayıt denemesini kaydeder + ORTAK hız sayacına ekler.

    (1) usage_events'e yaz (admin panelde görsün). Kayıt anonimdir → olayı ADMIN'e
    iliştir; admin yoksa (ilk kayıt) atla. AYRI session (istek session'ı hata yolunda
    rollback edilir → olay kaybolmasın).
    (2) login_limiter.record_failure: /auth/login + /users/login ile AYNI IP sayacına
    eklenir → saldırgan denemeleri uçlara dağıtarak sınırı atlayamaz (uç-bağımsız)."""
    ip = get_client_ip(request)
    login_limiter.record_failure(ip)
    with session_scope() as s2:
        admin = s2.scalar(
            select(User).where(User.is_admin.is_(True)).order_by(User.created_at).limit(1)
        )
        if admin is not None:
            record_event(s2, admin.id, "register_failed",
                         {"reason": reason, "username": attempted[:50], "ip": ip})


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id, username=u.username, is_admin=u.is_admin,
        is_anonymous=u.is_anonymous,
        created_at=u.created_at, last_login_at=u.last_login_at,
        guide_dismissed=u.guide_dismissed, tutorial_done=u.tutorial_done,
        language=getattr(u, "language", "tr") or "tr",
        email=getattr(u, "email", None),
    )


# E-posta: basit ve kasıtlı olarak gevşek biçim denetimi (tek @, noktalı alan adı, boşluk yok).
# Doğrulama postası henüz yok (sonraki adım); burada yalnızca biçim + benzersizlik.
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s.]{2,}$")


def normalize_email(raw: str | None) -> str | None:
    """Küçük harf + kırpılmış e-posta; biçim geçersizse None."""
    e = (raw or "").strip().lower()
    return e if e and len(e) <= 254 and _EMAIL_RE.match(e) else None


def _find_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def _require_email(raw: str | None, db: Session, exclude_id: int | None = None) -> str:
    """Kayıt/ekleme için e-posta: zorunlu, biçimli, benzersiz (küçük harfe göre)."""
    email = normalize_email(raw)
    if email is None:
        raise HTTPException(status_code=422, detail="Geçerli bir e-posta adresi gir.")
    other = _find_by_email(db, email)
    if other is not None and other.id != exclude_id:
        raise HTTPException(status_code=409, detail="Bu e-posta adresi zaten kayıtlı.")
    return email


def _find_by_username_ci(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.username) == username.lower()))


@router.post("/register", response_model=UserTokenOut, status_code=201)
def register(payload: RegisterIn, request: Request, db: Session = Depends(get_db, scope="function")) -> UserTokenOut:
    """Yeni kişisel hesap (HERKESE AÇIK — genel şifre kapısı kaldırıldı; max_users + anon
    hız sınırı korur). İlk kullanıcı (ya da ADMIN_USERNAME) admin olur."""
    _check_locked(request)
    settings = get_settings()
    username = payload.username.strip()
    if not _USERNAME_RE.match(username):
        _record_register_failed("invalid_username", username, request)
        raise HTTPException(
            status_code=422,
            detail="Kullanıcı adı 3–30 karakter olmalı; yalnızca harf, rakam ve alt çizgi.",
        )
    if len(payload.password) < MIN_PASSWORD_LEN:
        _record_register_failed("short_password", username, request)
        raise HTTPException(
            status_code=422, detail=f"Şifre en az {MIN_PASSWORD_LEN} karakter olmalı."
        )

    # KRİTİK BÖLÜM (yarış-güvenli): sayım + benzersizlik + insert + commit tek kilit
    # altında ve commit KİLİT İÇİNDE yapılır → iki eşzamanlı kayıt limiti aşamaz.
    with _register_lock:
        if settings.max_users > 0:
            n = db.scalar(select(func.count()).select_from(User)) or 0
            if n >= settings.max_users:
                _record_register_failed("limit", username, request)
                raise HTTPException(
                    status_code=403,
                    detail="Kullanıcı limiti dolu. Yönetici ile iletişime geçin.",
                )
        if _find_by_username_ci(db, username) is not None:
            _record_register_failed("duplicate", username, request)
            raise HTTPException(status_code=409, detail="Bu kullanıcı adı zaten alınmış.")
        try:
            email = _require_email(payload.email, db)
        except HTTPException:
            _record_register_failed("email", username, request)
            raise

        # Admin belirleme: ADMIN_USERNAME eşleşirse ya da hiç kullanıcı yoksa (ilk kayıt).
        admin_username = settings.admin_username
        if admin_username:
            is_admin = username.lower() == admin_username.lower()
        else:
            is_admin = (db.scalar(select(func.count()).select_from(User)) or 0) == 0

        user = User(username=username, email=email, password_hash=hash_password(payload.password), is_admin=is_admin)
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            _record_register_failed("duplicate", username, request)
            raise HTTPException(status_code=409, detail="Bu kullanıcı adı ya da e-posta zaten kayıtlı.")

        user.last_login_at = datetime.now(timezone.utc)
        record_event(db, user.id, "login", {"via": "register"})
        # KİLİT İÇİNDE commit: satır kalıcı olsun ki bir sonraki eşzamanlı kayıt onu saysın.
        db.commit()
        token = make_user_token(user)
        out = _user_out(user)
    return UserTokenOut(token=token, user=out)


@router.post("/login", response_model=UserTokenOut)
def login(payload: UserLoginIn, request: Request, db: Session = Depends(get_db, scope="function")) -> UserTokenOut:
    """Kişisel giriş. Kullanıcı adı büyük/küçük harf duyarsız; şifre bcrypt ile doğrulanır.

    Hız-sınırlı (kaba kuvvet). Hata mesajı kullanıcı adı/şifre ayrımı yapmaz (enum'a karşı)."""
    ip = get_client_ip(request)
    attempted = payload.username.strip()
    akey = account_key(attempted)
    # IP kilidi VEYA hesap kilidi (hesap kilidi XFF spoofing'i etkisiz kılar).
    locked = login_limiter.locked_seconds(ip) or account_limiter.locked_seconds(akey)
    if locked:
        raise HTTPException(status_code=429, detail=f"Çok fazla deneme. {locked // 60 + 1} dk sonra tekrar deneyin.")
    # Kullanıcı adı YA DA e-posta ile giriş ("@" içeriyorsa e-posta; kullanıcı adı regex'i "@" içermez).
    if "@" in attempted:
        em = normalize_email(attempted)
        user = _find_by_email(db, em) if em else None
    else:
        user = _find_by_username_ci(db, attempted)
    if user is None or not verify_password(payload.password, user.password_hash):
        # TANI: hesaplanan IP ile ham XFF'i logla — canlıda IP'nin tutarlı mı yoksa her
        # istekte farklı mı geldiği (XFF/proxy sorunu) buradan görülür.
        logger.warning("[rate-limit] /users/login başarısız — ip=%s xff=%r",
                       ip, request.headers.get("x-forwarded-for"))
        login_limiter.record_failure(ip)
        account_limiter.record_failure(akey)  # hesap-bazlı (XFF spoof'a karşı)
        # Başarısız denemeyi admin panelinde göster (KULLANICI ADI dahil → kimin/neyin
        # takıldığı görünsün). AYRI session: aşağıdaki 401 request session'ını rollback
        # eder → event kaybolmasın.
        with session_scope() as s2:
            if user is not None:
                record_event(s2, user.id, "login_failed", {"ip": ip, "username": user.username})
            else:
                # Bilinmeyen kullanıcı adı (muhtemel sondaj) → admin'e iliştir, görünür olsun.
                admin = s2.scalar(
                    select(User).where(User.is_admin.is_(True)).order_by(User.created_at).limit(1)
                )
                if admin is not None:
                    record_event(s2, admin.id, "login_failed",
                                 {"ip": ip, "username": attempted[:50], "unknown": True})
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı.")
    login_limiter.record_success(ip)
    account_limiter.record_success(akey)  # başarılı giriş → hesap kilidini temizle
    user.last_login_at = datetime.now(timezone.utc)
    record_event(db, user.id, "login", None)
    return UserTokenOut(token=make_user_token(user), user=_user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    """Mevcut kişisel kullanıcı bilgisi (is_admin dahil)."""
    return _user_out(user)


@router.post("/upgrade", response_model=UserTokenOut)
def upgrade(payload: RegisterIn, user: User = Depends(get_current_user),
            db: Session = Depends(get_db, scope="function")) -> UserTokenOut:
    """Anonim oturumu KALICI hesaba çevir (liste/geçmiş korunur — aynı satır).

    Yalnızca anonim kullanıcı için. Kullanıcı adı + şifre belirlenir; device_id_hash
    korunur (aynı cihazda hatırlanmaya devam). Şifre değiştiği için TAZE token döner."""
    if not user.is_anonymous:
        raise HTTPException(status_code=409, detail="Bu hesap zaten kalıcı.")
    username = payload.username.strip()
    if not _USERNAME_RE.match(username):
        raise HTTPException(status_code=422,
                            detail="Kullanıcı adı 3–30 karakter; yalnızca harf, rakam, alt çizgi.")
    if len(payload.password) < MIN_PASSWORD_LEN:
        raise HTTPException(status_code=422, detail=f"Şifre en az {MIN_PASSWORD_LEN} karakter olmalı.")
    if _find_by_username_ci(db, username) is not None:
        raise HTTPException(status_code=409, detail="Bu kullanıcı adı zaten alınmış.")
    user.email = _require_email(payload.email, db)
    user.username = username
    user.password_hash = hash_password(payload.password)
    user.is_anonymous = False
    user.last_login_at = datetime.now(timezone.utc)
    record_event(db, user.id, "login", {"via": "upgrade"})
    db.flush()
    return UserTokenOut(token=make_user_token(user), user=_user_out(user))


@router.post("/me/email", response_model=UserOut)
def set_email(payload: EmailIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db, scope="function")) -> UserOut:
    """E-posta ekle/değiştir (eski hesaplarda boş olabilir). Yalnızca kalıcı hesap."""
    if user.is_anonymous:
        raise HTTPException(status_code=403, detail="Önce hesap oluştur.")
    user.email = _require_email(payload.email, db, exclude_id=user.id)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Bu e-posta adresi zaten kayıtlı.")
    return _user_out(user)


@router.post("/me/guide-dismiss", response_model=UserOut)
def dismiss_guide(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")) -> UserOut:
    """"NewsRadar ne yapar?" açıklama kutusunu kalıcı olarak kapat (kullanıcı tercihi)."""
    user.guide_dismissed = True
    return _user_out(user)


@router.post("/me/tutorial-done", response_model=UserOut)
def finish_tutorial(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")) -> UserOut:
    """İlk giriş tutorial'ını tamamlandı işaretle (bir daha gösterilmez)."""
    user.tutorial_done = True
    return _user_out(user)


class LanguageIn(BaseModel):
    language: str


@router.post("/me/language", response_model=UserOut)
def set_language(payload: LanguageIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db, scope="function")) -> UserOut:
    """Arayüz dilini kaydet ("tr" | "en"). Geçersizse tr'ye düşer."""
    lang = (payload.language or "").strip().lower()
    user.language = lang if lang in ("tr", "en") else "tr"
    # YANITTAN ÖNCE commit: arayüz bu yanıtı bekleyip hemen GET /entities çekiyor; commit
    # gecikirse kartlar ESKİ dilde geliyordu (dil karışmasının bir yolu). get_db artık
    # scope="function" ile zaten yanıttan önce commit ediyor; bu açık commit fonksiyon
    # doğrudan çağrıldığında da (test_language_missing C) kalıcılığı garanti eder.
    db.commit()
    return _user_out(user)
