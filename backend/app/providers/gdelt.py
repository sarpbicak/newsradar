"""GDELT DOC 2.0 sağlayıcısı — anahtar kelimeli şirketler ve ABD dışı hisseler için haber.

Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
Örnek: GET https://api.gdeltproject.org/api/v2/doc/doc?query="OpenAI" (sourcelang:english OR
       sourcelang:german OR sourcelang:turkish)&mode=artlist&format=json&maxrecords=75
       &sort=datedesc&startdatetime=YYYYMMDDHHMMSS
Kullanım şartı (https://www.gdeltproject.org/about.html#termsofuse): akademik/ticari/kamu
kullanımı ücretsiz ve sınırsız; kullanımda GDELT Project'e atıf + site bağlantısı ZORUNLU
(arayüz altbilgisinde var). Anahtar gerekmez.

GDELT yalnızca başlık verir (açıklama yok); sorgu aranan ifadeyi içeren haberleri döndürür →
entity_filtered=True (Finnhub/NewsAPI gibi). Gürültüyü mevcut alaka filtresi eler: LLM
relevance < 0.3 → haber atılır. Başlık-eşleşmesi ön-filtresi BİLEREK uygulanmaz: kayıtlı
keyword verisinde LLM'in alakalı bulduğu haberlerin çoğunun başlığında şirket adı geçmiyordu
(Anthropic: 152'nin yalnızca 36'sı) — başlık filtresi onları da atardı. Hız: belge bir sınır belirtmiyor; ihtiyatla istekler arası en az 5 sn ve
aynı sorgu 10 dk önbellekten. GDELT hataları düz metin döner (JSON değil) → kibar uyarı.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import httpx

from ..db.models import Entity
from ..entity_names import readable_name
from ..markets import base_symbol, market_of
from ..messages import msg
from .base import FetchedArticle, NewsProvider, ProviderResult

logger = logging.getLogger("newsradar.providers")

_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_LANGS = ("english", "german", "turkish")   # haber dili filtresi: en / de / tr
_MAX_RECORDS = 75
MIN_INTERVAL_S = 5.0                         # istekler arası en az (ihtiyatlı)
CACHE_TTL_S = 600

_lock = threading.Lock()
_last_call = [0.0]
_cache: dict[tuple[str, str], tuple[float, ProviderResult]] = {}


def search_terms(entity: Entity) -> list[str]:
    """Aranacak ifadeler: keyword → sorgu; hisse → okunur şirket adı (+ ≥4 harfli sembol kökü)."""
    if entity.type == "keyword":
        return [entity.query.strip()]
    name = (entity.display_name or readable_name(entity.name) or entity.name or "").strip()
    terms = [name] if name else []
    base = base_symbol(entity.query)
    if len(base) >= 4 and base.isalpha() and base.casefold() != name.casefold():
        terms.append(base)
    return terms


def build_query(terms: list[str]) -> str:
    phrase = " OR ".join(f'"{t}"' for t in terms if t)
    phrase = f"({phrase})" if len(terms) > 1 else phrase
    langs = " OR ".join(f"sourcelang:{lang}" for lang in _LANGS)
    return f"{phrase} ({langs})"


def _parse_seendate(value: str | None) -> datetime | None:
    """GDELT 'seendate': 20261024T103000Z."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
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
            url=url, title=title, source=(item.get("domain") or "GDELT").strip(), description="",
            image_url=item.get("socialimage") or None, published_at=_parse_seendate(item.get("seendate")),
        ))
    return out


class GdeltProvider(NewsProvider):
    name = "gdelt"
    entity_type = "keyword"
    entity_filtered = True  # sorgu ifadeyi şart koşar; alaka güvencesi LLM eşiğinde

    def is_available(self) -> bool:
        return True  # anahtar gerekmez

    def _wait_turn(self) -> None:
        with _lock:
            gap = MIN_INTERVAL_S - (time.monotonic() - _last_call[0])
            if gap > 0:
                time.sleep(gap)
            _last_call[0] = time.monotonic()

    def fetch(self, entity: Entity, since: datetime) -> ProviderResult:
        terms = search_terms(entity)
        if not terms:
            return ProviderResult(provider=self.name)
        query = build_query(terms)
        start = since.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")
        key = (query, start[:10])  # saat çözünürlüğünde önbellek anahtarı
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
            return hit[1]
        params = {"query": query, "mode": "artlist", "format": "json", "maxrecords": _MAX_RECORDS,
                  "sort": "datedesc", "startdatetime": start}
        self._wait_turn()
        try:
            resp = httpx.get(_URL, params=params, timeout=20.0)
        except httpx.HTTPError as exc:
            return ProviderResult(provider=self.name, warning=msg("connection_error", source="gdelt", error=exc))
        if resp.status_code == 429 or "limit requests" in resp.text[:200].lower():
            logger.warning("[gdelt] hız sınırı ('%s')", query)
            return ProviderResult(provider=self.name, warning=msg("gdelt_busy"))
        if resp.status_code >= 400:
            return ProviderResult(provider=self.name, warning=msg("http_error", source="gdelt",
                                                                    status=resp.status_code, symbol=terms[0]))
        try:
            data = resp.json() if resp.text.strip() else {}
        except ValueError:
            # Düz metin hata (ör. "The specified phrase is too short") → kalıcı değil, kullanıcıya kısa not.
            logger.warning("[gdelt] JSON olmayan yanıt ('%s'): %s", query, resp.text[:160])
            return ProviderResult(provider=self.name, warning=msg("gdelt_error", detail=resp.text.strip()[:120]))
        result = ProviderResult(provider=self.name, articles=parse_articles(data))
        _cache[key] = (time.monotonic(), result)
        return result


def news_language(entity: Entity) -> str:
    """Öneri/varsayılan dil: hissede borsanın dili, keyword'de entity dili."""
    if entity.type == "ticker":
        return market_of(entity.query).news_lang
    return (entity.language or "en").lower()
