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


def _market_of(symbol: str) -> str:
    """Sembolden pazar ipucu: nokta yoksa ABD, varsa son ekten (IS, DE, L...)."""
    if "." in symbol:
        return symbol.rsplit(".", 1)[-1].upper()
    return "US"


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
        cleaned.append(
            {
                "symbol": symbol,
                "description": desc,
                "type": (r.get("type") or "").strip(),
                "market": _market_of(symbol),
            }
        )

    # ABD (market=US) önde; grup içinde Finnhub'ın alaka sırası korunur (stable sort).
    cleaned.sort(key=lambda x: x["market"] != "US")
    return cleaned[:limit]
