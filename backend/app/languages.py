"""Arayüz ve AI içeriği dilleri — TEK yer.

Kullanıcının kayıtlı dili, `?lang=` parametresi, e-postalar, sohbet ve değerlendirme çevirileri
bu modülü okur. Almanca geçici olarak bayrakla açılıp kapanır (NEWSRADAR_ENABLE_DE, varsayılan
kapalı; frontend'de VITE_ENABLE_DE): kapalıyken "de" her yerde "en" sayılır ve DE çevirisi
yapılmaz. Kod ve çeviriler yerinde kalır.
Yeni dil: SUPPORTED_LANGUAGES'a ekle, pipeline.assessment_languages'a ekle, frontend sözlüğünü ekle.
"""

from __future__ import annotations

from .config import get_settings

SUPPORTED_LANGUAGES = ("tr", "en", "de")
DEFAULT_LANGUAGE = "tr"


def de_enabled() -> bool:
    return get_settings().enable_de


def ui_languages() -> tuple[str, ...]:
    """Şu an açık diller (DE kapalıyken yalnızca tr, en)."""
    return SUPPORTED_LANGUAGES if de_enabled() else ("tr", "en")


def effective_language(value: str | None, default: str = DEFAULT_LANGUAGE) -> str:
    """Okunan dil (kayıtlı tercih, istek): DE kapalıyken "de" → "en"; bilinmeyen → default."""
    v = (value or "").strip().lower()
    if v == "de" and not de_enabled():
        return "en"
    return v if v in ui_languages() else default


def normalize_language(value: str | None, default: str = DEFAULT_LANGUAGE) -> str:
    """Kaydedilecek dil kodu (küçük harf) ya da `default`; DE kapalıyken "de" → "en"."""
    return effective_language(value, default)


def user_language(user) -> str:
    """Kullanıcının etkin dili (e-posta, sohbet, kart içeriği): kayıtlı tercih, DE kapalıyken en."""
    return effective_language(getattr(user, "language", None))


def language_from_accept(header: str | None) -> str:
    """Accept-Language'in ilk dili: de → de (DE kapalıyken en), tr → tr, diğerleri → en
    (frontend initialLang ile aynı)."""
    first = (header or "").strip().lower()[:2]
    if first == "de":
        return "de" if de_enabled() else "en"
    return "tr" if first == "tr" else "en"
