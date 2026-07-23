"""Sembol arama — Finnhub /search sarmalayıcısı.

Kullanıcı ticker eklerken şirket adından sembol bulabilsin diye. Anahtar yoksa
ya da çağrı patlarsa BOŞ liste döner (hata vermez). Sadece hisse senedi sonuçları,
ABD borsası (sembolde nokta yok) olanlar önde, en fazla `limit` sonuç.
"""

from __future__ import annotations

import logging

import httpx

from .config import get_settings

logger = logging.getLogger("newsradar.symbolsearch")

_BASE = "https://finnhub.io/api/v1"
# Hisse senedi tipleri (Finnhub `type` alanı). Boş tip de kabul (bazı sonuçlarda yok).
_STOCK_HINTS = ("stock", "adr", "equity", "reit", "dr")

# Yabancı borsa son eki → insan-okur ad (Finnhub ücretsiz katmanı bunları kapsamaz).
_EXCHANGE_NAMES = {
    "IS": "Borsa İstanbul",
    "DE": "XETRA (Frankfurt)",
    "F": "Frankfurt",
    "PA": "Euronext Paris",
    "L": "Londra (LSE)",
    "MC": "Bolsa de Madrid",
    "MI": "Borsa Italiana",
    "AS": "Euronext Amsterdam",
    "BR": "Euronext Brüksel",
    "LS": "Euronext Lizbon",
    "SW": "SIX (İsviçre)",
    "ST": "Nasdaq Stockholm",
    "HE": "Nasdaq Helsinki",
    "CO": "Nasdaq Kopenhag",
    "OL": "Oslo Børs",
    "VI": "Wiener Börse",
    "WA": "GPW (Varşova)",
    "AT": "Athens Exchange",
    "TO": "Toronto (TSX)",
    "HK": "Hong Kong",
    "T": "Tokyo",
}
# Son ek → önerilen keyword dili (yoksa en).
_SUFFIX_LANG = {
    "IS": "tr",
    "DE": "de", "F": "de", "VI": "de", "SW": "de",
    "PA": "fr", "BR": "fr",
}


def _suffix_of(symbol: str) -> str | None:
    """ABD-dışı sembol son eki (ASELS.E.IS → IS), yoksa None (ABD)."""
    return symbol.rsplit(".", 1)[-1].upper() if "." in symbol else None


def _is_stock(type_str: str) -> bool:
    t = (type_str or "").strip().lower()
    if not t:
        return True  # tip belirtilmemiş → dışlama
    return any(h in t for h in _STOCK_HINTS)


def search_symbols(query: str, limit: int = 8) -> list[dict]:
    """Şirket adı/sembol için Finnhub /search; sadeleştirilmiş sonuç listesi döner."""
    settings = get_settings()
    q = (query or "").strip()
    if not settings.finnhub_available or len(q) < 2:
        return []

    try:
        resp = httpx.get(
            f"{_BASE}/search",
            params={"q": q, "token": settings.finnhub_api_key},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("Sembol arama başarısız (boş dönüldü): %s", exc)
        return []

    results = data.get("result", []) if isinstance(data, dict) else []
    cleaned: list[dict] = []
    seen: set[str] = set()
    for r in results:
        symbol = (r.get("symbol") or "").strip()
        desc = (r.get("description") or "").strip()
        if not symbol or not desc or symbol in seen:
            continue
        if not _is_stock(r.get("type", "")):
            continue
        seen.add(symbol)
        suffix = _suffix_of(symbol)
        us_supported = suffix is None  # nokta yoksa ABD → Finnhub kapsıyor
        cleaned.append(
            {
                "symbol": symbol,
                "description": desc,
                "type": (r.get("type") or "").strip(),
                "market": suffix or "US",
                "us_supported": us_supported,
                # ABD-dışı için insan-okur borsa adı + önerilen keyword dili.
                "exchange_name": "ABD" if us_supported else _EXCHANGE_NAMES.get(suffix, suffix),
                "suggested_language": "en" if us_supported else _SUFFIX_LANG.get(suffix, "en"),
            }
        )

    # ABD-destekli (Finnhub kapsamı) önde; grup içinde Finnhub alaka sırası korunur.
    cleaned.sort(key=lambda x: not x["us_supported"])
    return cleaned[:limit]
