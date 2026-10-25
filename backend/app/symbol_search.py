"""Sembol arama — Finnhub /search sarmalayıcısı (ücretsiz planda global).

Kullanıcı ticker eklerken şirket adından sembol bulabilsin diye. Anahtar yoksa
ya da çağrı patlarsa BOŞ liste döner (hata vermez). Sadece hisse senedi sonuçları.
Her sonuçta borsa, ülke ve para birimi (app.markets). ABD dışı semboller de hisse olarak
eklenir: haberleri GDELT'ten gelir; fiyat/analist yuvası boş olduğu için "veri yok".
ABD sonuçları önde (fiyat ve analist verisi olanlar), en fazla `limit` sonuç.
"""

from __future__ import annotations

import logging

import httpx

from .config import get_settings
from .markets import market_of, suffix_of

logger = logging.getLogger("newsradar.symbolsearch")

_BASE = "https://finnhub.io/api/v1"
# Hisse senedi tipleri (Finnhub `type` alanı). Boş tip de kabul (bazı sonuçlarda yok).
_STOCK_HINTS = ("stock", "adr", "equity", "reit", "dr")

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
        # Bilinmeyen borsa son eki (tabloda yok) → pazarı söylenemez, atla. Tek harfli son ek
        # ABD hisse sınıfıdır (BRK.B) ve kalır.
        tail = symbol.rsplit(".", 1)[-1] if "." in symbol else ""
        if tail and suffix_of(symbol) is None and len(tail) > 1:
            continue
        seen.add(symbol)
        m = market_of(symbol)
        cleaned.append(
            {
                "symbol": symbol,
                "description": desc,
                "type": (r.get("type") or "").strip(),
                "market": m.code,
                "us_supported": m.is_us,
                "exchange_name": m.exchange,
                "country_tr": m.country_tr,
                "country_en": m.country_en,
                "currency": m.currency,
                "suggested_language": m.news_lang,
            }
        )

    # ABD-destekli (Finnhub kapsamı) önde; grup içinde Finnhub alaka sırası korunur.
    cleaned.sort(key=lambda x: not x["us_supported"])
    return cleaned[:limit]
