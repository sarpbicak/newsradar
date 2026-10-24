"""Claude yapılandırılmış çıktı şemaları (tool-use ile zorlanır) + doğrulama.

Yapılandırılmış çıktıyı *tool-use* ile alıyoruz: bir "tool" tanımlıyoruz, modeli onu
çağırmaya yönlendiriyoruz (destekleyen modelde zorunlu tool_choice) ve tool_use.input
JSON'unu okuyoruz. (Bkz. analysis/claude_client.py, model_specs.py)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from ..db.models import (
    CONVICTIONS,
    EVENT_TYPES,
    IMPACT_HORIZONS,
    RISK_FLAGS,
    SENTIMENT_TRENDS,
    STANCES,
)
from .text_quality import PROMPT_LIMITS, clip_to_sentence, hard_cap, strip_markup_leak

logger = logging.getLogger("newsradar.schemas")

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
#  Kısa / uzun vade (aynı değerlendirme çağrısının parçası — ek LLM çağrısı yok)
# --------------------------------------------------------------------------- #
# 5 kademeli haber yönü. "insufficient_data": o vade için yeterli haber yok (model ya da kod
# koyar). "mixed" YALNIZCA kod koyar: hüküm, etken yönleriyle tekrar denemeden sonra da
# çelişiyorsa (ör. "olumlu" ama etkenlerin çoğu "down").
HORIZON_VERDICTS = ("very_negative", "negative", "neutral", "positive", "very_positive")
NO_DATA_VERDICT = "insufficient_data"
MIXED_VERDICT = "mixed"
HORIZON_FIELDS = ("short_term", "long_term")
SHORT_TERM_DAYS = 7     # kısa vade: son 7 günün olayları
LONG_TERM_DAYS = 90     # uzun vade: 30-90 günlük yapısal etkenler (son 90 günün haberleri)
MIN_SHORT_ARTICLES = 2  # bunun altında kısa vade "yetersiz veri"
MIN_LONG_ARTICLES = 3   # bunun altında uzun vade "yetersiz veri"


def _horizon_schema(desc: str) -> dict:
    return {
        "type": "object",
        "description": desc,
        "properties": {
            "verdict": {"type": "string", "enum": [*HORIZON_VERDICTS, NO_DATA_VERDICT]},
            "drivers": {
                "type": "array",
                "description": (
                    "2-3 etken, istenen çıkış dilinde; her biri BU şirkete özgü kısa TAM cümle "
                    "ve şirket için yönü ('up' olumlu, 'down' olumsuz). insufficient_data ise boş."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "direction": {"type": "string", "enum": ["up", "down"]},
                    },
                    "required": ["text", "direction"],
                    "additionalProperties": False,
                },
            },
            "summary": {
                "type": "string",
                "description": "Bu vade için tek TAM cümle, istenen çıkış dilinde. insufficient_data ise boş.",
            },
        },
        "required": ["verdict", "drivers", "summary"],
        "additionalProperties": False,
    }


def _as_utc(value: object) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def horizon_counts(payload: list[dict], now: datetime | None = None) -> dict[str, int]:
    """Değerlendirme bağlamında vade başına haber sayısı (tarih yoksa sayılmaz)."""
    now = now or datetime.now(timezone.utc)
    dates = [d for d in (_as_utc(p.get("published_at")) for p in payload) if d is not None]
    return {
        "short_term": sum(1 for d in dates if now - d <= timedelta(days=SHORT_TERM_DAYS)),
        "long_term": sum(1 for d in dates if now - d <= timedelta(days=LONG_TERM_DAYS)),
    }


def horizon_has_data(field: str, counts: dict[str, int]) -> bool:
    need = MIN_SHORT_ARTICLES if field == "short_term" else MIN_LONG_ARTICLES
    return counts.get(field, 0) >= need


def horizon_consistent(h: dict | None) -> bool:
    """Hüküm etken yönleriyle uyumlu mu? Olumlu tarafta 'up', olumsuz tarafta 'down' ağır
    basmalı; nötr ve yönsüz etkenler denetlenmez."""
    if not isinstance(h, dict):
        return True
    v = h.get("verdict")
    drivers = h.get("drivers") if isinstance(h.get("drivers"), list) else []
    dirs = [d.get("direction") for d in drivers if isinstance(d, dict)]
    up, down = dirs.count("up"), dirs.count("down")
    if up + down == 0:
        return True
    if v in ("positive", "very_positive"):
        return up > down
    if v in ("negative", "very_negative"):
        return down > up
    return True


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
        "DİL: tüm metin alanları İSTENEN ÇIKIŞ DİLİNDE (prompt'ta belirtilir: Türkçe ya da "
        "İngilizce) üretilir. BÜYÜK/KÜÇÜK HARF: normal yazım — yalnızca cümle başı ve özel "
        "isimler büyük. Cümle ortasında rastgele büyük harf YOK."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "headline_verdict": {
                "type": "string",
                "description": (
                    "Finans bilmeyen bir LİSE ÖĞRENCİSİNİN anlayacağı, düz, İSTENEN ÇIKIŞ "
                    "DİLİNDE tek TAM cümle HÜKÜM — TR en fazla "
                    f"{PROMPT_LIMITS['headline_verdict']['tr']} kelime, EN en fazla "
                    f"{PROMPT_LIMITS['headline_verdict']['en']} kelime; bu sınırı AŞMA, sığmıyorsa "
                    "daha az şey söyle. Nokta ile biter. Kartın en üstünde büyük gösterilecek. "
                    "ŞU ÜÇ ŞEYİ İÇERMELİ: (a) haber akışının yönü (olumlu/olumsuz/kararsız), "
                    "(b) ne kadar güvenilir olduğu (çok/az habere dayanıyor, tutarlı mı), "
                    "(c) VARSA analist beklentisi ile haberlerin ayrışması ya da fiyatın zaten "
                    "tepki verdiği. JARGON KESİNLİKLE YASAK: 'volatilite', 'momentum', "
                    "'konsolidasyon', 'değerleme', 'katalizör' gibi kelimeler KULLANMA; "
                    "günlük dil kullan. "
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
                    "'AI ne düşünüyor?' — 3-5 cümlelik, en fazla "
                    f"{PROMPT_LIMITS['ai_take']} kelime (bu sınırı AŞMA, sığmıyorsa daha az şey "
                    "söyle; son cümle tam ve noktalı), KONUŞMA DİLİNDE, bütünsel bir "
                    "yorum (istenen çıkış dilinde). Haber akışı + fiyat hareketi + analist konsensüsü + kanıt gücünü "
                    "SENTEZLE; bir arkadaşın anlatır gibi düz, istenen çıkış dilinde (jargon YOK). "
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
                    "Tam 3 kısa etken, İSTENEN ÇIKIŞ DİLİNDE; her madde nokta ile biten kısa "
                    "bir TAM cümle. Genel ifade DEĞİL — BU şirketin haberlerinden "
                    "doğan somut etken (ürün/olay/rakam/kişi adı geçsin). Başka şirkete de "
                    "uyacak genel maddeler yazma."
                ),
                "items": {"type": "string"},
            },
            # top_drivers ile AYNI SIRADA yön: etken şirket için olumluysa "up", olumsuzsa "down".
            # Eksik/yanlış gelirse sanitize None yapar; yön gösterilmez.
            "top_driver_directions": {
                "type": "array",
                "description": (
                    "top_drivers ile aynı sırada ve aynı sayıda: her etken şirket için olumluysa "
                    "'up', olumsuzsa 'down'."
                ),
                "items": {"type": "string", "enum": ["up", "down"]},
            },
            "summary": {"type": "string", "description": "2-3 tam cümle özet, istenen çıkış dilinde; nokta ile biter."},
            "stance": {"type": "string", "enum": list(STANCES)},
            "conviction": {"type": "string", "enum": list(CONVICTIONS)},
            "what_to_verify": {
                "type": "array",
                "description": (
                    "Harekete geçmeden önce 2-4 somut kontrol, istenen çıkış dilinde; her madde "
                    "nokta ile biten TAM bir cümle."
                ),
                "items": {"type": "string"},
            },
            "invalidation": {
                "type": "string",
                "description": "Bu görüşü çürütecek olay/haber — tek TAM cümle, istenen çıkış dilinde; nokta ile biter.",
            },
            "short_term": _horizon_schema(
                "KISA VADE (~7 gün): son haberlerdeki OLAYLARA odaklı haber yönü. Fiyat tahmini değil."
            ),
            "long_term": _horizon_schema(
                "UZUN VADE (30-90 gün): YAPISAL etkenlere (iş modeli, pazar, maliyet, düzenleme, "
                "süregelen eğilim) dayalı haber yönü. Fiyat tahmini değil."
            ),
        },
        "required": [
            "headline_verdict", "ai_take", "risk_score", "sentiment_trend", "top_drivers", "top_driver_directions",
            "summary", "stance", "conviction", "what_to_verify", "invalidation", "short_term", "long_term",
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


def _as_list(value: object, label: str) -> list:
    """Liste alanını güvenle listeye çevirir. Model (özellikle zorunlu tool_choice olmayan
    Sonnet 5.5) bazen diziyi TEK string olarak döndürür; string'i karakter karakter dolaşmak
    kartta "G • o • o • g" üretiyordu. JSON dizi string'i → parse; aksi halde satır/madde
    işaretlerinden bölünür."""
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    text = value.strip()
    logger.warning("[şema] %s dizi yerine string geldi — listeye çevriliyor.", label)
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except ValueError:
            pass
    parts = [p.strip(" \t•*-") for p in re.split(r"\n+|\s+•\s+|^\s*[-*•]\s+", text, flags=re.M)]
    return [p for p in parts if p]


def sanitize_horizon(raw: object, clip) -> dict | None:
    """Tek vadeyi güvenli değerlere çeker; geçersiz/eksikse None (eski kayıt gibi davranır).
    Tekrar denemeden sonra da hüküm etkenlerle çelişiyorsa hüküm "mixed" olur."""
    if not isinstance(raw, dict):
        return None
    verdict = raw.get("verdict")
    if verdict not in (*HORIZON_VERDICTS, NO_DATA_VERDICT):
        return None
    if verdict == NO_DATA_VERDICT:
        return {"verdict": NO_DATA_VERDICT, "drivers": [], "summary": ""}
    drivers = []
    for d in _as_list(raw.get("drivers"), "horizon.drivers"):
        text, direction = (d.get("text"), d.get("direction")) if isinstance(d, dict) else (d, None)
        if str(text or "").strip():
            drivers.append({"text": clip("top_drivers", text),
                            "direction": direction if direction in ("up", "down") else None})
    out = {"verdict": verdict, "drivers": drivers[:3], "summary": clip("horizon_summary", raw.get("summary", ""))}
    if not horizon_consistent(out):
        logger.warning("[şema] vade hükmü (%s) etken yönleriyle çelişiyor → mixed.", verdict)
        out["verdict"] = MIXED_VERDICT
    return out


def apply_horizon_floor(clean: dict, counts: dict[str, int]) -> dict:
    """Haber sayısı eşiğin altındaki vadeyi (modelin cevabından bağımsız) "yetersiz veri"
    yapar: 7 günde 1 haberle kısa vade hükmü verilmesin."""
    for field in HORIZON_FIELDS:
        if clean.get(field) is not None and not horizon_has_data(field, counts):
            clean[field] = {"verdict": NO_DATA_VERDICT, "drivers": [], "summary": ""}
    return clean


# --------------------------------------------------------------------------- #
#  Tek kaynak + çeviri: metin alanları dilden bağımsız alanlardan ayrılır
# --------------------------------------------------------------------------- #
# Çevrilen (dile bağlı) alanlar. Hüküm, risk, yönler, enum'lar ÇEVİRİYE GİTMEZ → değişemez.
TEXT_FIELDS = ("headline_verdict", "ai_take", "summary", "invalidation")
TEXT_LIST_FIELDS = ("top_drivers", "what_to_verify")


def localizable_texts(clean: dict) -> dict:
    """Temizlenmiş değerlendirmeden yalnızca metinler (düz yapı; çeviri aracıyla aynı)."""
    out = {f: clean.get(f) or "" for f in TEXT_FIELDS}
    out.update({f: list(clean.get(f) or []) for f in TEXT_LIST_FIELDS})
    for h in HORIZON_FIELDS:
        v = clean.get(h) or {}
        out[f"{h}_summary"] = v.get("summary") or ""
        out[f"{h}_drivers"] = [d.get("text") or "" for d in (v.get("drivers") or [])]
    return out


def apply_texts(base: dict, texts: dict | None) -> dict:
    """Dilden bağımsız alanlar `base`'den, metinler `texts`'ten (yoksa base'deki kalır).
    Liste uzunluğu tutmazsa o liste için kaynak metin korunur (yön/sıra kaymasın)."""
    out = dict(base)
    if not texts:
        return out
    for f in TEXT_FIELDS:
        if texts.get(f):
            out[f] = texts[f]
    for f in TEXT_LIST_FIELDS:
        if isinstance(texts.get(f), list) and len(texts[f]) == len(base.get(f) or []):
            out[f] = list(texts[f])
    for h in HORIZON_FIELDS:
        v = base.get(h)
        if not isinstance(v, dict):
            continue
        v = {**v, "drivers": [dict(d) for d in (v.get("drivers") or [])]}
        if texts.get(f"{h}_summary"):
            v["summary"] = texts[f"{h}_summary"]
        tr = texts.get(f"{h}_drivers")
        if isinstance(tr, list) and len(tr) == len(v["drivers"]):
            for d, t in zip(v["drivers"], tr):
                d["text"] = t
        out[h] = v
    return out


TRANSLATION_TOOL_NAME = "record_translation"
_str = {"type": "string"}
_list = {"type": "array", "items": {"type": "string"}}
TRANSLATION_TOOL = {
    "name": TRANSLATION_TOOL_NAME,
    "description": (
        "Verilen metin alanlarının çevirisini kaydet. Her alan aynı anlamda, doğal hedef dilde; "
        "listelerde AYNI sayıda madde, AYNI sırada. Boş alan boş kalır."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            **{f: _str for f in TEXT_FIELDS},
            **{f: _list for f in TEXT_LIST_FIELDS},
            **{f"{h}_summary": _str for h in HORIZON_FIELDS},
            **{f"{h}_drivers": _list for h in HORIZON_FIELDS},
        },
        "required": [*TEXT_FIELDS, *TEXT_LIST_FIELDS,
                     *(f"{h}_{k}" for h in HORIZON_FIELDS for k in ("summary", "drivers"))],
        "additionalProperties": False,
    },
}


def sanitize_translation(raw: object, source: dict, language: str) -> dict | None:
    """Çeviri çıktısını doğrular: her alan var, listeler kaynakla aynı uzunlukta, kaynakta dolu
    olan alan boş değil. Geçersizse None (çağıran yeniden dener ya da çeviriyi yazmaz)."""
    if not isinstance(raw, dict):
        return None
    lang = "en" if language == "en" else "tr"

    def clip(field: str, value: object) -> str:
        label = f"{field}/{lang}/çeviri"
        text = strip_markup_leak(str(value or "").strip(), label)
        return clip_to_sentence(text, hard_cap(field, lang), label)

    out: dict = {}
    for key, src in source.items():
        field = key
        if key.endswith("_summary") and key.split("_summary")[0] in HORIZON_FIELDS:
            field = "horizon_summary"
        elif key.endswith("_drivers"):
            field = "top_drivers"
        val = raw.get(key)
        if isinstance(src, list):
            items = _as_list(val, f"çeviri.{key}")
            if len(items) != len(src):
                logger.warning("[çeviri] %s: %d madde bekleniyordu, %d geldi.", key, len(src), len(items))
                return None
            out[key] = [clip(field, x) for x in items]
            if any(s and not t for s, t in zip(src, out[key])):
                return None
        else:
            out[key] = clip(field, val) if src else ""
            if src and not out[key]:
                return None
    return out


def sanitize_entity_analysis(item: dict, language: str = "tr") -> dict:
    """Claude'dan gelen entity değerlendirmesini güvenli değerlere çeker.

    Metin alanları ASLA cümle ortasında kesilmez: uzunluğu prompt yönetir; koddaki tavan
    yalnızca emniyettir (text_quality.HARD_CAPS) ve aşılırsa son tam cümlede kesilir,
    sınır içinde cümle sonu yoksa metin olduğu gibi bırakılır (bkz. clip_to_sentence)."""
    lang = "en" if (language or "tr").lower() == "en" else "tr"

    def clip(field: str, value: object) -> str:
        label = f"{field}/{lang}"
        text = strip_markup_leak(str(value or "").strip(), label)
        return clip_to_sentence(text, hard_cap(field, lang), label)

    trend = item.get("sentiment_trend")
    stance = item.get("stance")
    conviction = item.get("conviction")
    # Etken ile yönü birlikte süz (boş etken atılınca yönler kaymasın).
    raw_dirs = item.get("top_driver_directions") if isinstance(item.get("top_driver_directions"), list) else []
    pairs = [(clip("top_drivers", d), raw_dirs[i] if i < len(raw_dirs) else None)
             for i, d in enumerate(_as_list(item.get("top_drivers"), "top_drivers")) if str(d).strip()][:3]
    drivers = [d for d, _ in pairs]
    directions = [x if x in ("up", "down") else None for _, x in pairs]
    verify = [clip("what_to_verify", v)
              for v in _as_list(item.get("what_to_verify"), "what_to_verify") if str(v).strip()]
    verdict = clip("headline_verdict", item.get("headline_verdict", ""))
    take = clip("ai_take", item.get("ai_take", ""))
    return {
        "headline_verdict": verdict,
        "ai_take": take,
        "risk_score": int(clamp(float(item.get("risk_score", 50)), 0, 100)),
        "sentiment_trend": trend if trend in SENTIMENT_TRENDS else "stable",
        "top_drivers": drivers[:3],
        # Hiç geçerli yön yoksa None (eski kayıtlarla aynı: yön gösterilmez).
        "driver_directions": directions if any(directions) else None,
        "summary": clip("summary", item.get("summary", "")),
        "stance": stance if stance in STANCES else "neutral",
        "conviction": conviction if conviction in CONVICTIONS else "low",
        "what_to_verify": verify[:4],
        "invalidation": clip("invalidation", item.get("invalidation", "")),
        # Kısa / uzun vade (yoksa None: eski kayıtlar gibi tek etikete düşülür).
        "short_term": sanitize_horizon(item.get("short_term"), clip),
        "long_term": sanitize_horizon(item.get("long_term"), clip),
    }
