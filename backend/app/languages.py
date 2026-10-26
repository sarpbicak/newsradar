"""Arayüz ve AI içeriği dilleri — TEK yer.

Kullanıcının kayıtlı dili, `?lang=` parametresi ve değerlendirme çevirileri bu listeyi okur.
Yeni dil: buraya ekle, pipeline.ASSESSMENT_LANGUAGES'a ekle (çeviri), frontend sözlüğünü ekle.
"""

from __future__ import annotations

UI_LANGUAGES = ("tr", "en", "de")
DEFAULT_LANGUAGE = "tr"


def normalize_language(value: str | None, default: str = DEFAULT_LANGUAGE) -> str:
    """Geçerli dil kodu (küçük harf) ya da `default`."""
    v = (value or "").strip().lower()
    return v if v in UI_LANGUAGES else default


def language_from_accept(header: str | None) -> str:
    """Accept-Language'in ilk dili: de → de, tr → tr, diğerleri → en (frontend initialLang ile aynı)."""
    first = (header or "").strip().lower()[:2]
    return first if first in ("de", "tr") else "en"
