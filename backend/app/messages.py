"""Kullanıcıya giden uyarı/bilgi mesajları — KOD + PARAMETRE (çeviri frontend'de).

Her mesaj bir sözlüktür: {"code": "...", "entity": "Tesla" | None, "params": {...}}.
Frontend `msg.<code>` anahtarıyla kullanıcının dilinde (TR/EN) metne çevirir; `source`
parametresi `src.<source>` anahtarıyla çevrilir. Backend yalnızca log/CLI için Türkçe
metin üretir (render). Yeni bir kod eklerken frontend/src/i18n.jsx'e de TR+EN ekleyin.
"""

from __future__ import annotations

# Log/CLI için Türkçe şablonlar (kullanıcıya giden metin frontend'de çevrilir).
_TR = {
    # yenileme
    "refresh_running": "Yenileme zaten çalışıyor.",
    "few_news": "Son {days} günde yeterli haber bulunamadı; yeni haber çıktıkça güncellenecek.",
    "llm_key_missing": "Analiz motorunun anahtarı tanımlı değil: {detail}",
    "budget_exceeded": "Günlük analiz bütçesi dolu — yeni analiz yapılmadı.",
    "budget_stopped": "Günlük analiz bütçesi tarama sırasında doldu — kalan analizler atlandı.",
    "analysis_unavailable": "Analiz servisi geçici olarak kullanılamıyor — çekilen haberler kaydedildi.",
    # haber çekme
    "no_provider": "'{type}' tipi için sağlayıcı yok.",
    "news_fresh_skip": "Son {hours} saatte çekildi — NewsAPI atlandı (mevcut veri kullanılıyor).",
    "newsapi_quota": "NewsAPI kotası doldu ({used}/{limit}), {hours} saat sonra sıfırlanır.",
    "db_write_error": "Yazma hatası, entity atlandı: {error}",
    # sağlayıcılar
    "key_missing": "{key} tanımlı değil — atlandı.",
    "http_error": "{source} hatası ({status}) — {symbol} atlandı.",
    "connection_error": "{source} bağlantı/çözümleme hatası: {error}",
    "gdelt_busy": "Haber kaynağı (GDELT) şu an yoğun; bir sonraki yenilemede tekrar denenecek.",
    "gdelt_blocked": "Haber kaynağı (GDELT) istekleri sınırladı; bir süre istek atılmayacak (devre kesici).",
    "gdelt_error": "Haber kaynağı (GDELT) bu aramayı yanıtlamadı: {detail}",
    "no_data": "{symbol} için {source} verisi yok.",
    "bad_response": "{source} beklenmeyen yanıt döndü ({symbol}).",
    "newsapi_status": "NewsAPI durum='{status}': {message}",
    "provider_error": "{source} beklenmeyen hata: {error}",
    # analiz hattı
    "prefilter_error": "Ön-filtre hatası (atlandı): {error}",
    "llm_zero": "LLM 0 analiz döndürdü ({batches} batch gönderildi) — model/endpoint sorunu olabilir.",
    "article_truncated": "Makale #{article_id} analiz edilemedi: yanıt kesildi.",
    "split_limit": "{count} makale atlandı: bölme sınırına ulaşıldı, yanıt hâlâ kesiliyor.",
    "batch_error": "Batch analiz hatası (bölünmedi): {error}",
    "assessment_failed": "Değerlendirme başarısız ({lang}): {error}",
    "entity_error": "Analiz beklenmeyen hata (atlandı): {error}",
}

_SOURCE_TR = {
    "finnhub_news": "Finnhub", "finnhub_price": "Finnhub fiyat",
    "finnhub_analyst": "Finnhub analist", "fmp_target": "FMP hedef fiyat",
    "newsapi": "NewsAPI", "gdelt": "GDELT",
}


def msg(code: str, entity: str | None = None, **params) -> dict:
    """Kullanıcıya gidecek mesaj. params JSON'a çevrilebilir basit değerler olmalı."""
    return {"code": code, "entity": entity, "params": {k: _plain(v) for k, v in params.items()}}


def with_entity(m: dict, entity: str) -> dict:
    """Sağlayıcıdan entity'siz gelen mesaja entity adını ekler (kopya döner)."""
    return {**m, "entity": m.get("entity") or entity}


def _plain(v):
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return str(v)


def render(m: dict | str) -> str:
    """Log/CLI için Türkçe metin. (Eski düz string mesajlar olduğu gibi döner.)"""
    if isinstance(m, str):
        return m
    params = dict(m.get("params") or {})
    if "source" in params:
        params["source"] = _SOURCE_TR.get(params["source"], params["source"])
    tpl = _TR.get(m.get("code"), m.get("code", "?") + " {params}")
    try:
        text = tpl.format(**params, params=params)
    except (KeyError, IndexError):
        text = f"{m.get('code')} {params}"
    return f"[{m['entity']}] {text}" if m.get("entity") else text


CODES = frozenset(_TR)
