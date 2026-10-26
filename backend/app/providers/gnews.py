"""GNews sağlayıcısı — anahtar kelimeli şirketler ve ABD dışı hisseler için BİRİNCİL haber kaynağı.

Docs: https://docs.gnews.io/endpoints/search-endpoint · hatalar: https://docs.gnews.io/error-handling
Örnek: GET https://gnews.io/api/v4/search?q="OpenAI"&lang=en&in=title,description&max=10
       &from=2026-10-22T12:00:00Z&sortby=publishedAt   (anahtar X-Api-Key başlığında)

Ücretsiz plan (gnews.io/pricing, gnews.io/legal/terms-of-service; 2026-10-26):
- Günde 100 istek, istek başı en fazla 10 haber, saniyede 1 istek, 30 gün geçmiş.
- Haberler **12 saat gecikmeli** gelir (ücretli planlarda gerçek zamanlı): yeni bir gelişme
  GNews'ten en erken ~12 saat sonra görünür. İçerik alanı kısaltılmıştır (başlık + açıklama
  kullanıyoruz).
- Yalnızca ticari olmayan kullanım; makul önbellekleme izinli; atıf zorunlu değil (footer'da
  şeffaflık için "GNews" yazar).

Sorgu: şirket adı tam ifade ("Türk Hava Yolları"; hisse ise okunur ad + ≥4 harfli sembol kökü,
GDELT ile aynı terimler), başlık ve açıklamada; dil şirketin haber dili (en/de/tr; borsa ya da
entity dili, diğerleri en). İstek başına bir dil → şirket başına günde tek istek.

Anahtar URL'de DEĞİL X-Api-Key başlığında gider: hata metinleri ve loglar anahtarı taşımaz.
İstekler tek sırada, aralarında en az MIN_GAP_S (ücretsiz plan 1 istek/sn). Kota (günlük
sayaç, şirket başına aralık) ve GDELT yedeği alım katmanında (app/ingest.py, app/gnews_quota.py).
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import httpx

from ..config import get_settings
from ..db.models import Entity
from ..messages import msg
from .base import FetchedArticle, NewsProvider, ProviderResult
from .gdelt import news_language, search_terms

logger = logging.getLogger("newsradar.providers")

_URL = "https://gnews.io/api/v4/search"
LANGS = ("en", "de", "tr")
MAX_ARTICLES = 10          # ücretsiz planın istek başı üst sınırı
MIN_GAP_S = 1.1            # ücretsiz plan: saniyede 1 istek
_lock = threading.Lock()
_last = [float("-inf")]


def build_query(terms: list[str]) -> str:
    """Tam ifade(ler): "Ad" ya da "Ad" OR "KÖK" (GNews en fazla 200 karakter)."""
    return " OR ".join(f'"{t}"' for t in terms if t)[:200]


def query_language(entity: Entity) -> str:
    lang = news_language(entity)
    return lang if lang in LANGS else "en"


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_articles(data: dict) -> list[FetchedArticle]:
    out: list[FetchedArticle] = []
    for item in (data or {}).get("articles", []) or []:
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        if not url or not title:
            continue
        out.append(FetchedArticle(
            url=url, title=title, source=((item.get("source") or {}).get("name") or "GNews").strip(),
            description=(item.get("description") or "").strip(), image_url=item.get("image") or None,
            published_at=_parse_date(item.get("publishedAt")),
        ))
    return out


def _error_text(resp) -> str:
    try:
        errs = resp.json().get("errors")
    except ValueError:
        return resp.text.strip()[:160]
    if isinstance(errs, dict):
        return "; ".join(f"{k}: {v}" for k, v in errs.items())[:160]
    if isinstance(errs, list):
        return "; ".join(str(e) for e in errs)[:160]
    return resp.text.strip()[:160]


class GNewsProvider(NewsProvider):
    name = "gnews"
    entity_type = "keyword"
    entity_filtered = True  # sorgu şirket adını şart koşar; alaka güvencesi LLM eşiğinde

    def is_available(self) -> bool:
        return bool(get_settings().gnews_api_key)

    def fetch(self, entity: Entity, since: datetime) -> ProviderResult:
        """Tek istek. Hata → warning (kod gnews_error, status); alım katmanı GDELT'e düşer."""
        terms = search_terms(entity)
        if not terms:
            return ProviderResult(provider=self.name)
        params = {
            "q": build_query(terms), "lang": query_language(entity), "in": "title,description",
            "max": MAX_ARTICLES, "sortby": "publishedAt",
            "from": since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        headers = {"X-Api-Key": get_settings().gnews_api_key}
        with _lock:
            gap = MIN_GAP_S - (time.monotonic() - _last[0])
            if gap > 0:
                time.sleep(gap)
            try:
                resp = httpx.get(_URL, params=params, headers=headers, timeout=20.0)
            except httpx.HTTPError as exc:
                # Anahtar başlıkta: hata metni URL'yi içerse de anahtar yok.
                return ProviderResult(provider=self.name, warning=msg("gnews_error", status=0, detail=type(exc).__name__))
            finally:
                _last[0] = time.monotonic()
        if resp.status_code != 200:
            detail = _error_text(resp)
            logger.warning("[gnews] HTTP %s ('%s'): %s", resp.status_code, params["q"], detail)
            return ProviderResult(provider=self.name, warning=msg("gnews_error", status=resp.status_code, detail=detail))
        try:
            data = resp.json()
        except ValueError:
            return ProviderResult(provider=self.name, warning=msg("gnews_error", status=200, detail="non-JSON response"))
        return ProviderResult(provider=self.name, articles=parse_articles(data))
