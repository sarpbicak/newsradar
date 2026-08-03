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
                                    "why_relevant": {
                                        "type": ["string", "null"],
                                        "description": (
                                            "BU şirketin (analiz edilen varlık değil, önerilen "
                                            "şirket) neden gündemde olduğu — tek cümle TÜRKÇE, "
                                            "ör. 'AMD, MI400 ile NVIDIA'nın veri merkezi payını "
                                            "hedefliyor'. Emin değilsen null."
                                        ),
                                    },
                                },
                                "required": [
                                    "name", "ticker", "is_public", "country", "exchange",
                                    "why_relevant",
                                ],
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
        "net olmalı; gerekçesiz BUY/SELL verme. Fiyat tahmini DEĞİL — haber sinyali. "
        "ÇEŞİTLİLİK ZORUNLU: headline_verdict ve ai_take BU ŞİRKETE özgü EN AZ BİR SOMUT "
        "detay içermeli — ürün/olay adı, rakam ya da sektörel dinamik (ör. 'Helios "
        "lansmanı güçlü', 'reklam geliri baskı altında', 'F-35 tedarik haberi'). Sadece "
        "'haberler karışık/olumlu/olumsuz' ile başlayıp genel devam eden cümle YETERSİZ. "
        "ŞABLON YASAK: 'Haberler karışık, analistler yüksek hedefte — ayrışma var' gibi "
        "hazır kalıpları AYNEN tekrarlama; ayrışmayı belirtirken bile o şirketin somut "
        "durumunu kullan (ör. 'Bulut büyümesi yavaşlıyor ama analistler hâlâ %40 yukarı "
        "hedefliyor'). Farklı şirketlere aynı cümleyi YAPIŞTIRMA — her hüküm o şirketin "
        "haberinden ayırt edilebilir olmalı. Bu kural ai_take için de geçerli: genel laf "
        "değil, o şirketin somut durumu. "
        "BÜYÜK/KÜÇÜK HARF: tüm metin alanlarında normal Türkçe yazım — yalnızca cümle "
        "başı ve özel isimler büyük harfle başlar. Cümle ortasında rastgele büyük harf "
        "YOK ('analistler Yine de' YANLIŞ → 'analistler yine de' DOĞRU)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "headline_verdict": {
                "type": "string",
                "description": (
                    "Finans bilmeyen bir LİSE ÖĞRENCİSİNİN anlayacağı tek cümlelik, düz "
                    "Türkçe HÜKÜM — EN FAZLA 14 KELİME (kartta 3 satıra sığmalı). "
                    "Kartın en üstünde büyük gösterilecek. "
                    "ŞU ÜÇ ŞEYİ İÇERMELİ: (a) haber akışının yönü (olumlu/olumsuz/kararsız), "
                    "(b) ne kadar güvenilir olduğu (çok/az habere dayanıyor, tutarlı mı), "
                    "(c) VARSA analist beklentisi ile haberlerin ayrışması ya da fiyatın zaten "
                    "tepki verdiği. JARGON KESİNLİKLE YASAK: 'volatilite', 'momentum', "
                    "'konsolidasyon', 'değerleme', 'katalizör' gibi kelimeler KULLANMA; "
                    "günlük Türkçe kullan. "
                    "BU şirkete ÖZGÜ en az bir SOMUT detay içermeli (ürün/olay adı, rakam, "
                    "sektörel dinamik). Sadece 'haberler karışık/olumlu/olumsuz' ile başlayan "
                    "genel cümle YETERSİZ — doğrudan o şirketin elindeki haberlerden çıkan somut "
                    "gelişmeyle başla. Şablon kalıpları aynen tekrarlama; başka şirkete "
                    "kopyalanabilen hüküm YANLIŞTIR."
                ),
            },
            "ai_take": {
                "type": "string",
                "description": (
                    "'AI ne düşünüyor?' — 3-5 cümlelik, KONUŞMA DİLİNDE, bütünsel bir "
                    "yorum. Haber akışı + fiyat hareketi + analist konsensüsü + kanıt gücünü "
                    "SENTEZLE; bir arkadaşın anlatır gibi düz Türkçe (jargon YOK). "
                    "BU şirketin KENDİ durumunu anlat: elindeki haberlerden çıkan somut "
                    "detayları kullan (ürün adı, olay, rakam, kişi). Her şirkete uyacak genel "
                    "bir yorum YAZMA — yorumun başka bir şirkete olduğu gibi kopyalanabiliyorsa "
                    "YANLIŞTIR, o şirkete özgü olmalı. ŞUNLARI YAP: (a) net bir duruş al; "
                    "(b) kısa vade ile uzun vadeyi ayır; (c) varsa çelişkileri (haber↔analist "
                    "ayrışması) o şirketin somut durumuyla açıkla; (d) somut ne izlenmeli belirt "
                    "(bu şirketin haberlerinden doğan spesifik olay/tarih/rakam). "
                    "ŞUNLARI YAPMA: kendi hedef fiyatını UYDURMA (yalnızca verilen FMP analist "
                    "hedefini aktarabilirsin; kendi fiyat hedefin ASLA); 'kesin yükselir/düşer' "
                    "gibi kesinlik satma, belirsizliği dürüstçe söyle; değerleme yapamadığını, "
                    "sadece haber akışı + fiyat + analist verisine baktığını gerektiğinde belirt "
                    "(her cümlede tekrarlama)."
                ),
            },
            "risk_score": {
                "type": "integer",
                "description": (
                    "0 (düşük risk) .. 100 (yüksek risk). ÖNCE haber akışının net yönünü "
                    "belirle, SONRA o yönün bandından seç — 60 gibi bir sayıya VARSAYILAN "
                    "olarak DÜŞME: güçlü olumlu → 15-30; hafif olumlu → 30-42; gerçekten "
                    "karışık/belirsiz → 45-58; olumsuz → 60-74; ciddi olumsuz (skandal, dava, "
                    "güvenlik ihlali, büyük kayıp) → 75-90. Olumlu haber akışı olan bir şirkete "
                    "60 VERME (o düşük olmalı); ciddi olumsuz habere de 60 verme (o yüksek "
                    "olmalı). Yuvarlak çıpalardan (50, 60) kaç; kanıtın gücü ve haberlerin "
                    "sertliğine göre gerçek değeri seç. Skorlar şirketler arası açıkça farklılaşmalı."
                ),
            },
            "sentiment_trend": {"type": "string", "enum": list(SENTIMENT_TRENDS)},
            "top_drivers": {
                "type": "array",
                "description": (
                    "Tam 3 kısa etken, TÜRKÇE. Genel ifade DEĞİL — BU şirketin haberlerinden "
                    "doğan somut etken (ürün/olay/rakam/kişi adı geçsin). Başka şirkete de "
                    "uyacak genel maddeler yazma."
                ),
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
            "headline_verdict", "ai_take", "risk_score", "sentiment_trend", "top_drivers",
            "summary", "stance", "conviction", "what_to_verify", "invalidation",
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
        why = c.get("why_relevant")
        why = str(why).strip() if why else None
        out.append({
            "name": name, "ticker": ticker or None, "is_public": is_public,
            "country": country or None, "exchange": exchange or None,
            "why_relevant": why or None,
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
    # Hüküm cümlesi: en fazla 14 kelimeye kırp (kartta 3 satırı aşmasın).
    verdict = " ".join(str(item.get("headline_verdict", "")).strip().split()[:14])
    # Claude yorumu: 3-5 cümle; en fazla ~120 kelimeye kırp (aşırı uzamasın).
    take = " ".join(str(item.get("ai_take", "")).strip().split()[:120])
    return {
        "headline_verdict": verdict,
        "ai_take": take,
        "risk_score": int(clamp(float(item.get("risk_score", 50)), 0, 100)),
        "sentiment_trend": trend if trend in SENTIMENT_TRENDS else "stable",
        "top_drivers": drivers[:3],
        "summary": str(item.get("summary", "")).strip(),
        "stance": stance if stance in STANCES else "neutral",
        "conviction": conviction if conviction in CONVICTIONS else "low",
        "what_to_verify": verify[:4],
        "invalidation": str(item.get("invalidation", "")).strip(),
    }
