"""Claude yapılandırılmış çıktı şemaları (tool-use ile zorlanır) + doğrulama.

Sonnet 4.6 katı structured-outputs (output_config.format) desteklemediğinden,
yapılandırılmış çıktıyı *zorunlu tool-use* ile alıyoruz: bir "tool" tanımlıyoruz,
tool_choice ile onu zorluyoruz ve tool_use.input JSON'unu okuyoruz. Bu desen
tüm modellerde çalışır. (Bkz. analysis/claude_client.py)
"""

from __future__ import annotations

from ..db.models import (
    CONVICTIONS,
    EVENT_TYPES,
    IMPACT_HORIZONS,
    RISK_FLAGS,
    SENTIMENT_TRENDS,
    STANCES,
)

# --------------------------------------------------------------------------- #
#  Makale-başı analiz tool'u
# --------------------------------------------------------------------------- #
ARTICLE_TOOL_NAME = "record_article_analyses"

ARTICLE_ANALYSIS_TOOL = {
    "name": ARTICLE_TOOL_NAME,
    "description": (
        "Toplu haber analizini kaydet. Girdideki HER makale için tam olarak bir "
        "analiz nesnesi döndür; sıra ve `id` girdiyle eşleşmeli."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "analyses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "description": "Girdideki makale id'si"},
                        "sentiment": {
                            "type": "number",
                            "description": "-1.0 (çok olumsuz) .. 1.0 (çok olumlu)",
                        },
                        "event_type": {"type": "string", "enum": list(EVENT_TYPES)},
                        "risk_flags": {
                            "type": "array",
                            "items": {"type": "string", "enum": list(RISK_FLAGS)},
                        },
                        "impact_horizon": {"type": "string", "enum": list(IMPACT_HORIZONS)},
                        "relevance": {
                            "type": "number",
                            "description": "0..1 — bu entity ile ilgililik. 0.3 altı elenir.",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Tek cümlelik gerekçe, TÜRKÇE.",
                        },
                        "co_mentioned_entities": {
                            "type": "array",
                            "description": (
                                "Bu haberin İÇERİĞİNDE anlamlı biçimde geçen, haberin "
                                "konusu olan DİĞER şirketler (en fazla 3). Analiz edilen "
                                "varlığın KENDİSİNİ, haber sitesi/borsa adını, genel "
                                "terimleri (S&P 500, Nasdaq) ve yalnızca geçerken anılan "
                                "isimleri EKLEME. Hiçbiri yoksa boş dizi ([]) döndür."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "Şirket adı, örn. AMD"},
                                    "ticker": {
                                        "type": ["string", "null"],
                                        "description": "Borsa sembolü biliniyorsa (AMD), yoksa null",
                                    },
                                    "is_public": {
                                        "type": ["boolean", "null"],
                                        "description": "Halka açık mı; emin değilsen null",
                                    },
                                    "country": {
                                        "type": ["string", "null"],
                                        "description": (
                                            "Şirketin merkez/ana borsa ülkesi, ISO kodu "
                                            "(US, TR, DE, FR...). Emin değilsen null."
                                        ),
                                    },
                                    "exchange": {
                                        "type": ["string", "null"],
                                        "description": (
                                            "İşlem gördüğü ana borsa biliniyorsa "
                                            "(NASDAQ, NYSE, BIST, XETRA...), yoksa null."
                                        ),
                                    },
                                },
                                "required": ["name", "ticker", "is_public", "country", "exchange"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": [
                        "id", "sentiment", "event_type", "risk_flags",
                        "impact_horizon", "relevance", "rationale", "co_mentioned_entities",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["analyses"],
        "additionalProperties": False,
    },
}

# --------------------------------------------------------------------------- #
#  Entity-başı toplu analiz tool'u
# --------------------------------------------------------------------------- #
ENTITY_TOOL_NAME = "record_entity_assessment"

ENTITY_ANALYSIS_TOOL = {
    "name": ENTITY_TOOL_NAME,
    "description": (
        "Bir varlık için haber-akışı bazlı toplu değerlendirmeyi kaydet. Yön (stance) "
        "net olmalı; gerekçesiz BUY/SELL verme. Fiyat tahmini DEĞİL — haber sinyali."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "risk_score": {"type": "integer", "description": "0 (düşük) .. 100 (yüksek risk)"},
            "sentiment_trend": {"type": "string", "enum": list(SENTIMENT_TRENDS)},
            "top_drivers": {
                "type": "array",
                "description": "Tam 3 kısa etken, TÜRKÇE.",
                "items": {"type": "string"},
            },
            "summary": {"type": "string", "description": "2-3 cümle özet, TÜRKÇE."},
            "stance": {"type": "string", "enum": list(STANCES)},
            "conviction": {"type": "string", "enum": list(CONVICTIONS)},
            "what_to_verify": {
                "type": "array",
                "description": "Harekete geçmeden önce 2-4 somut kontrol, TÜRKÇE.",
                "items": {"type": "string"},
            },
            "invalidation": {
                "type": "string",
                "description": "Bu görüşü çürütecek olay/haber — tek cümle, TÜRKÇE.",
            },
        },
        "required": [
            "risk_score", "sentiment_trend", "top_drivers", "summary",
            "stance", "conviction", "what_to_verify", "invalidation",
        ],
        "additionalProperties": False,
    },
}

# İlgililik eşiği: bunun altındaki makaleler analizden sonra elenir.
RELEVANCE_THRESHOLD = 0.3


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def sanitize_co_mentioned(raw: object) -> list[dict]:
    """Co-mentioned şirket listesini güvenli hale getirir (en fazla 3, toleranslı).

    Eski analizlerde bu alan olmayabilir; eksik/bozuk girdi boş liste döner (hata değil).
    """
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for c in raw[:3]:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name", "")).strip()
        if not name:
            continue
        ticker = c.get("ticker")
        ticker = str(ticker).strip().upper() if ticker else None
        is_public = c.get("is_public")
        is_public = is_public if isinstance(is_public, bool) else None
        country = c.get("country")
        country = str(country).strip() if country else None
        exchange = c.get("exchange")
        exchange = str(exchange).strip() if exchange else None
        out.append({
            "name": name, "ticker": ticker or None, "is_public": is_public,
            "country": country or None, "exchange": exchange or None,
        })
    return out


def sanitize_article_analysis(item: dict) -> dict:
    """Claude'dan gelen tek makale analizini güvenli aralıklara çeker."""
    return {
        "id": int(item["id"]),
        "sentiment": clamp(float(item.get("sentiment", 0.0)), -1.0, 1.0),
        "event_type": item.get("event_type") if item.get("event_type") in EVENT_TYPES else "other",
        "risk_flags": [f for f in item.get("risk_flags", []) if f in RISK_FLAGS],
        "impact_horizon": item.get("impact_horizon") if item.get("impact_horizon") in IMPACT_HORIZONS else "short",
        "relevance": clamp(float(item.get("relevance", 0.0)), 0.0, 1.0),
        "rationale": str(item.get("rationale", "")).strip(),
        # Yeni alan; eski çıktılarda yoksa boş liste (kod tolere eder).
        "co_mentioned": sanitize_co_mentioned(item.get("co_mentioned_entities")),
    }


def sanitize_entity_analysis(item: dict) -> dict:
    """Claude'dan gelen entity değerlendirmesini güvenli değerlere çeker."""
    trend = item.get("sentiment_trend")
    stance = item.get("stance")
    conviction = item.get("conviction")
    drivers = [str(d).strip() for d in item.get("top_drivers", []) if str(d).strip()]
    verify = [str(v).strip() for v in item.get("what_to_verify", []) if str(v).strip()]
    return {
        "risk_score": int(clamp(float(item.get("risk_score", 50)), 0, 100)),
        "sentiment_trend": trend if trend in SENTIMENT_TRENDS else "stable",
        "top_drivers": drivers[:3],
        "summary": str(item.get("summary", "")).strip(),
        "stance": stance if stance in STANCES else "neutral",
        "conviction": conviction if conviction in CONVICTIONS else "low",
        "what_to_verify": verify[:4],
        "invalidation": str(item.get("invalidation", "")).strip(),
    }
