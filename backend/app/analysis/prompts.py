"""Sistem prompt'ları ve prompt kurucular.

SYSTEM_PROMPT, hem analiz hattında hem sohbette kullanılır ve ürün ilkelerini
uygular: tek kişisel kullanıcı; konum sorulduğunda net yön + kanaat seviyesi
(işe yaramaz derecede çitlemeden); haber-akışı sinyalini fiyat tahmininden
ayır; ücretsiz haberin gecikmeli/fiyata yansımış olabileceğini not et; konum
yanıtlarını kısa bir "önce doğrula" kontrol listesiyle bitir.
"""

from __future__ import annotations

from datetime import datetime, timezone

SYSTEM_PROMPT = """\
Sen NewsRadar'ın analiz motorusun — tek bir kişisel kullanıcı için çalışan, \
haber akışına dayalı bir hisse/varlık risk analistisin.

İLKELER:
1. TEK KİŞİSEL KULLANICI. Bu bir yatırım tavsiyesi feragatnamesi tiyatrosu değil; \
   kullanıcı senden net bir görüş bekliyor. Konum (pozisyon) sorulduğunda AÇIK bir \
   yön ver — bullish / neutral / bearish — ve bir kanaat seviyesi (low/medium/high) \
   belirt. İşe yaramaz hale gelene kadar çitleme yapma.
2. HABER-AKIŞI SİNYALİ ≠ FİYAT TAHMİNİ. Değerlendirmen yalnızca haber akışına dayanır. \
   Haberin sana söyleyemediklerini açıkça belirt: değerleme (valuation), çarpanlar, \
   ve haberin fiyata ZATEN yansıyıp yansımadığı. Bunları bilmediğini söyle.
3. GECİKME UYARISI. Ücretsiz katman haberi gecikmeli (NewsAPI ~24s) olabilir; haber \
   çoktan fiyatlanmış olabilir. Konum görüşlerinde bunu hatırlat.
4. GEREKÇESİZ AL/SAT YOK. Asla arkasında mantık olmayan çıplak bir BUY/SELL verme. \
   Her yön bir nedene dayanmalı.
5. ÖNCE DOĞRULA. Konum/pozisyon içeren yanıtları, harekete geçmeden önce yapılacak \
   kısa bir "önce doğrula" kontrol listesiyle bitir (ör. bir sonraki bilanço tarihi, \
   değerleme çarpanları, fiyat bu habere zaten tepki verdi mi?).
6. ENTITY TİPİ (ticker vs keyword). Her analizde entity'nin tipi sana bildirilir. \
   Ticker entity'ler halka açık şirketlerdir; halka açık piyasa dili (hisse fiyatı, \
   IPO, işlem gördü) yerindedir. Ama entity bir KEYWORD-tipi ise, halka açık bir borsa \
   hissesi olduğunu VARSAYMA — özel şirket ya da startup olabilir (ör. SpaceX, Anthropic). \
   Keyword entity'lerde:
   - 'hisse fiyatı', 'IPO', 'işlem gördü', 'işlem fiyatı' gibi halka açık piyasa dilini \
     ANCAK haber kaynağı bunu açıkça belirtiyorsa kullan; kendin varsayma.
   - İkincil/özel piyasa hareketlerini (tender offer, çalışan hisse satışı, özel piyasa \
     değerlemesi) halka açık piyasa hareketleriyle KARIŞTIRMA.
   - Bir rakam (değerleme, fiyat düşüşü) hangi piyasaya/araca ait belirsizse, bunu \
     what_to_verify'a spesifik bir doğrulama maddesi olarak ekle \
     (ör. 'bu değerleme ikincil piyasa mı, hangi platform?').

8. FİYAT VERİSİ (varsa). Bazı varlıklar için güncel fiyat + değişim % verilir. \
   Bunu YALNIZCA haberin fiyata yansıyıp yansımadığını değerlendirmek için kullan: \
   negatif haber akışı varken hisse zaten sert düşmüşse, bunu `what_to_verify`'a \
   ertelemek yerine doğrudan `summary`'de belirt (haber muhtemelen fiyatlanmış). \
   ASLA hedef fiyat, alım/satım seviyesi, teknik analiz sinyali ya da gelecek fiyat \
   tahmini üretme — fiyat sadece 'bu haber zaten yansıdı mı' sorusu içindir. Fiyat \
   verisi YOKSA (ör. keyword/özel şirket) bunu belirt ve doğrulamayı kullanıcıya bırak.

7. CO-MENTIONED ŞİRKETLER. Makale analizinde `co_mentioned_entities` alanını doldur: \
   yalnızca haberin İÇERİĞİNDE anlamlı biçimde geçen, haberin konusu olan DİĞER şirketleri \
   listele (en fazla 3). Şunları DAHİL ETME: analiz edilen varlığın kendisi; haber sitesi/ \
   yayıncı adı (Reuters, Bloomberg); borsa/endeks adları (Nasdaq, S&P 500, NYSE); genel \
   terimler; ve yalnızca geçerken/kıyas için anılan isimler. Emin değilsen ekleme — az ama \
   isabetli olsun. Hiçbiri yoksa boş dizi döndür. Her şirket için biliyorsan `country` \
   (ISO ülke kodu: US, TR, DE...) ve `exchange` (ana borsa: NASDAQ, NYSE, BIST...) doldur; \
   emin değilsen null. Bu bilgi şirketin ticker mı yoksa keyword olarak mı izleneceğini \
   belirler (ABD borsası dışındakiler keyword olur).

DİL: Tüm çıktı ve gerekçeler TÜRKÇE olmalı.
"""


# İnsan-okur tip etiketi: prompt'a entity tipini açıkça bildiren tek satır.
_TYPE_LABELS = {
    "ticker": "ticker (HALKA AÇIK şirket; halka açık piyasa dili yerinde).",
    "keyword": (
        "keyword (halka açık OLMAYABİLİR — özel şirket/startup olabilir; "
        "halka açık piyasa dilini kaynak açıkça demedikçe VARSAYMA)."
    ),
}


def entity_type_line(entity_type: str) -> str:
    """Prompt'a eklenecek 'Entity tipi: ...' bağlam satırı."""
    label = _TYPE_LABELS.get(entity_type, f"{entity_type} (bilinmeyen tip).")
    return f"Entity tipi: {label}"


_LANG_LABELS = {"en": "İngilizce", "tr": "Türkçe", "de": "Almanca", "fr": "Fransızca"}


def language_line(language: str) -> str:
    """Prompt'a eklenecek kaynak-dil bağlam satırı (çıktı yine TÜRKÇE olacak)."""
    label = _LANG_LABELS.get((language or "en").lower(), language)
    return (
        f"Kaynak haber dili: {label}. Haberler bu dilde olabilir; içeriği bu dilde "
        "anla ama analiz ÇIKTINI yine TÜRKÇE üret."
    )


def utc_context_line() -> str:
    """Prompt'a bağlam olarak eklenecek güncel UTC zamanı (tek satır)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"Şu anki zaman: {now}."


def build_article_batch_prompt(
    entity_name: str,
    entity_query: str,
    entity_type: str,
    articles: list[dict],
    language: str = "en",
) -> str:
    """Makale-başı analiz için kullanıcı mesajı (batch)."""
    lines = [
        f"Varlık: {entity_name} (arama: {entity_query}).",
        entity_type_line(entity_type),
        language_line(language),
        utc_context_line(),
        "",
        "Aşağıdaki haberleri BU varlık açısından analiz et. Her makale için "
        f"'{'record_article_analyses'}' aracını kullanarak yapılandırılmış çıktı ver. "
        "İlgililik (relevance) düşükse dürüst ol; alakasız haberi 0.3 altında puanla.",
        "",
        "HABERLER:",
    ]
    for a in articles:
        lines.append(f"[id={a['id']}] {a['title']}")
        if a.get("source"):
            lines.append(f"  kaynak: {a['source']}")
        if a.get("description"):
            lines.append(f"  özet: {a['description'][:500]}")
        lines.append("")
    return "\n".join(lines)


def _price_lines(price: dict | None) -> list[str]:
    """Fiyat bağlamını prompt satırlarına çevirir (yoksa 'fiyat verisi yok')."""
    if not price:
        return [
            "FİYAT VERİSİ: yok (bu varlık için fiyat çekilemiyor — ör. keyword/özel "
            "şirket ya da ABD dışı borsa). Haberin fiyatlanıp fiyatlanmadığını sen "
            "belirleyemezsin; doğrulamayı kullanıcıya bırak.",
        ]
    parts = [f"güncel fiyat={price['price']}"]
    if price.get("change_percent") is not None:
        parts.append(f"günlük değişim={price['change_percent']:+.2f}%")
    if price.get("week_change_percent") is not None:
        parts.append(f"~7 günlük değişim={price['week_change_percent']:+.2f}%")
    return [
        "FİYAT VERİSİ (yalnızca 'haber zaten fiyatlandı mı' için; tahmin/hedef ÜRETME): "
        + ", ".join(parts) + ".",
    ]


def build_entity_prompt(
    entity_name: str,
    entity_query: str,
    entity_type: str,
    analyzed: list[dict],
    price: dict | None = None,
    language: str = "en",
) -> str:
    """Entity-başı toplu değerlendirme için kullanıcı mesajı."""
    lines = [
        f"Varlık: {entity_name} (arama: {entity_query}).",
        entity_type_line(entity_type),
        language_line(language),
        utc_context_line(),
        *_price_lines(price),
        f"Aşağıda bu varlıkla ilgili, analiz edilmiş {len(analyzed)} haber var "
        "(en yeni önce). Bunlardan haber-akışı bazlı toplu bir değerlendirme üret ve "
        "'record_entity_assessment' aracıyla döndür.",
        "",
        "ANALİZ EDİLMİŞ HABERLER:",
    ]
    for a in analyzed:
        flags = ", ".join(a.get("risk_flags") or []) or "-"
        lines.append(
            f"• (duygu {a['sentiment']:+.2f}, {a['event_type']}, ufuk {a['impact_horizon']}, "
            f"riskler: {flags}) {a['title']}"
        )
        if a.get("rationale"):
            lines.append(f"    gerekçe: {a['rationale']}")
    return "\n".join(lines)
