"""Claude analiz hattı — ucuz ön-filtre + entity başına tavan + paralel çağrı.

Akış (analyze_all_async):
  1. ÖN-FİLTRE (ucuz, Claude'suz): entity adı/ticker'ı başlık+açıklamada hiç
     geçmeyen makaleler DB'de `prefiltered=True` işaretlenir ve hiç gönderilmez.
  2. TAVAN: entity başına en fazla `max_articles_per_entity` makale (en yeniler
     öncelikli); artanı bir sonraki yenilemeye kalır (analyzed=False).
  3. PARALEL analiz: makaleler `batch_size`'lik gruplar halinde, aynı anda
     `analysis_concurrency` çağrı (asyncio.Semaphore) ile Claude'a gönderilir.
     DB erişimi tek bir asyncio kilidiyle serileştirilir (SQLite 'locked' önlenir);
     ağ çağrıları paraleldir.
  4. Makale sonuçları yazılır (relevance < eşik → elenir), sonra entity-başı
     toplu değerlendirme üretilir.

Dayanıklılık: bir batch/entity hata verirse loglanır ve gerisi devam eder.
"""

from __future__ import annotations

import asyncio
import json
import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import session_scope
from ..db.models import (
    PREFILTER_VERSION, Article, Entity, EntityAnalysis, PriceSnapshot, Suggestion,
)
from ..analyst import analyst_context_for
from ..prices import price_context_for
from ..providers import get_provider_for
from .claude_client import ClaudeClient, ClaudeError, ProviderQuotaError, TruncationError
from .prompts import (
    SYSTEM_PROMPT,
    build_article_batch_prompt,
    build_entity_prompt,
)
from .text_quality import PROMPT_LIMITS, banned_phrase_hits, hard_cap, word_count
from .schemas import (
    ARTICLE_ANALYSIS_TOOL,
    ENTITY_ANALYSIS_TOOL,
    RELEVANCE_THRESHOLD,
    sanitize_article_analysis,
    sanitize_entity_analysis,
)

logger = logging.getLogger("newsradar.analysis")

def _effective_batch_size(batch_size: int, language: str | None) -> int:
    """İngilizce-dışı (ör. Türkçe) çıktı ~%50 fazla token yer → batch'i yarıya indir
    (tek yanıtta kesilme riskini azalt)."""
    if (language or "en").lower() != "en":
        return max(1, batch_size // 2)
    return batch_size


AGGREGATE_LOOKBACK = 200  # entity değerlendirmesinde kaç son makale bağlam olarak verilir
# (tavanla uyumlu: değerlendirme son 40'a değil, birikmiş son ~200 analiz edilmiş
#  makaleye bakar; _read_assessment_payload lookback = max(AGGREGATE_LOOKBACK, cap)).
# NOT: Entity değerlendirme çağrısı ARTIK settings.max_output_tokens kullanır
# (eskiden sabit 4096'ya bağlıydı → NEWSRADAR_MAX_OUTPUT_TOKENS okunmuyordu ve uzun
# TR çıktıları kesiliyordu; kartlar boş kalıyordu). Kesilmede kurtarma:
# _assess_entity_with_recovery (2× token → gerekirse bağlamı yarıya indir).
# Kesilmede batch bölme derinliği güvenlik sınırı. Doğal taban durumu tek makale
# (len<=1) olduğu için 10'luk batch normalde 4 bölmede tek makaleye iner; bu sınır
# yalnızca patolojik özyinelemeye karşı emniyet supabı (en kötü ihtimalle tek makale
# kaybı hedefi korunur — bkz. _run_batch/run_batch_sync).
_MAX_SPLIT_DEPTH = 6
# Tavan sınırsızken (0) entity-DEĞERLENDİRME okuması tek prompt'u şişirmesin diye
# okunacak analiz edilmiş makale üst sınırı (makale-başı analiz yine sınırsız).
ASSESSMENT_READ_CAP = 200
MAX_ANALYSIS_HISTORY = 100  # entity başına saklanacak en fazla değerlendirme kaydı
# GEREKSİZ DEĞERLENDİRMEYİ ATLA (en büyük maliyet kazancı): entity değerlendirmesi (dil
# başına) yalnızca (a) son değerlendirmeden sonra yeni analiz edilmiş makale varsa, (b) fiyat
# o zamandan beri ≥ |%3| oynadıysa ya da (c) son değerlendirme 24 saatten eskiyse yapılır.
ASSESSMENT_MAX_AGE_HOURS = 24
ASSESSMENT_PRICE_MOVE_PCT = 3.0
SUGGESTION_TTL_DAYS = 30    # bu süreden eski + az anılan öneriler temizlenir


# MALİYET BARİYERİ: Haiku 5.5'te prompt >100k token olursa çağrının TÜM kalemleri 5×
# fiyattan faturalanır. Değerlendirme prompt'u (system + tool + bağlam) bu sınırın altında
# tutulur; aşacaksa bağlam (en eski makaleler) kırpılır ve loglanır. Pay: 100k'ya 10k.
ASSESSMENT_PROMPT_TOKEN_LIMIT = 90_000
# Kaba tahmin: karakter / 2.5 (Türkçe + yeni tokenizer için bilinçli olarak yüksek tahmin).
# Tahmin sınırın %60'ını geçerse kesin sayım (count_tokens, ücretsiz) yapılır.
_CHARS_PER_TOKEN_EST = 2.5


def _estimate_prompt_tokens(client, user: str, tool: dict) -> tuple[int, bool]:
    """(token, kesin_mi). Ucuz tahmin; sınıra yakınsa istemcinin count_prompt_tokens'ı."""
    chars = len(SYSTEM_PROMPT) + len(user) + len(json.dumps(tool, ensure_ascii=False))
    est = int(chars / _CHARS_PER_TOKEN_EST)
    if est < ASSESSMENT_PROMPT_TOKEN_LIMIT * 0.6:
        return est, False
    counter = getattr(client, "count_prompt_tokens", None)
    if callable(counter):
        try:
            return int(counter(system=SYSTEM_PROMPT, user=user, tool=tool)), True
        except Exception as exc:  # noqa: BLE001 — sayım başarısızsa tahmine düş
            logger.warning("Token sayımı başarısız, tahmin kullanılıyor: %s", exc)
    return est, False


def _fit_assessment_context(client, build_fn, payload: list[dict], name: str) -> list[dict]:
    """Değerlendirme prompt'u ASSESSMENT_PROMPT_TOKEN_LIMIT'i aşmayacak şekilde bağlamı
    kırpar (payload yeniden→eskiye sıralı; en eskiler düşer). Kırpma loglanır."""
    items = payload
    for _ in range(6):
        tokens, exact = _estimate_prompt_tokens(client, build_fn(items), ENTITY_ANALYSIS_TOOL)
        if tokens <= ASSESSMENT_PROMPT_TOKEN_LIMIT or len(items) <= 1:
            return items
        keep = max(1, int(len(items) * ASSESSMENT_PROMPT_TOKEN_LIMIT / tokens * 0.9))
        logger.warning("[%s] değerlendirme prompt'u ~%d token (%s) > %d sınırı → bağlam "
                       "%d→%d makaleye kırpıldı (100k üstü 5× fiyat bariyeri).",
                       name, tokens, "kesin" if exact else "tahmin",
                       ASSESSMENT_PROMPT_TOKEN_LIMIT, len(items), keep)
        items = items[:keep]
    return items


# Kalite tekrar denemesi notları (çıkış dilinde). Hüküm emniyet tavanını aşarsa "daha kısa
# yaz"; hüküm/ai_take/summary yasaklı ifade içerirse "şu ifadeleri kullanma".
_SHORTER_NOTE = {
    "tr": ("NOT: Önceki denemede headline_verdict {n} kelimeydi — çok uzun. Bu sefer en fazla "
           "{limit} kelimelik TEK cümle yaz; sığmıyorsa daha az şey söyle. Diğer alanlar da "
           "kendi sınırlarına uysun."),
    "en": ("NOTE: In the previous attempt headline_verdict was {n} words — too long. This time "
           "write ONE sentence of at most {limit} words; if it doesn't fit, say fewer things. "
           "Keep the other fields within their limits too."),
}
_BANNED_NOTE = {
    "tr": ("NOT: Önceki denemede yasaklı kalıp ifadeler kullanıldı. Şu ifadeleri KULLANMA: {phrases}. "
           "Bunların yerine bu şirketin somut olayıyla başla."),
    "en": ("NOTE: The previous attempt used banned boilerplate phrases. Do NOT use: {phrases}. "
           "Lead with this company's concrete event instead."),
}
_BANNED_FIELDS = ("headline_verdict", "ai_take", "summary")


def _quality_notes(data: dict, lang: str) -> list[str]:
    """Yeniden istemeyi gerektiren kalite sorunları için notlar (boş = temiz)."""
    notes = []
    n = word_count(str(data.get("headline_verdict") or ""))
    if n > hard_cap("headline_verdict", lang):
        notes.append(_SHORTER_NOTE[lang].format(n=n, limit=PROMPT_LIMITS["headline_verdict"][lang]))
    text = " ".join(str(data.get(f) or "") for f in _BANNED_FIELDS)
    hits = banned_phrase_hits(text, lang)
    if hits:
        notes.append(_BANNED_NOTE[lang].format(phrases=", ".join(f"'{h}'" for h in hits)))
    return notes


def _assess_entity_with_recovery(client, build_fn, payload, name, lang: str = "tr"):
    """Değerlendirme + kalite denetimi. (adata, kullanılan_payload) döner.

    Hüküm emniyet tavanını (text_quality.HARD_CAPS) aşarsa ya da hüküm/ai_take/summary
    yasaklı ifade (text_quality.BANNED_PHRASES) içerirse değerlendirme BİR KEZ ilgili
    notlarla yeniden istenir (sorunlar birlikteyse notlar tek denemede gider — en fazla bir
    ek çağrı, döngü yok). Daha az sorunlu yanıt kullanılır (eşitlikte yenisi); kalan sorun
    loglanır: uzun hükmü sanitize son tam cümlede keser, yasaklı ifade olduğu gibi kalır."""
    lang = "en" if (lang or "tr").lower() == "en" else "tr"
    data, used = _assess_with_truncation_recovery(client, build_fn, payload, name)
    notes = _quality_notes(data, lang)
    if not notes:
        return data, used
    logger.warning("[%s] kalite sorunu → notlarla bir kez yeniden isteniyor: %s",
                   name, " | ".join(notes))
    note = "\n\n".join(notes)
    try:
        data2, used2 = _assess_with_truncation_recovery(
            client, lambda items: f"{build_fn(items)}\n\n{note}", used, name)
    except ProviderQuotaError:
        raise
    except ClaudeError as exc:
        logger.warning("[%s] kalite tekrar denemesi başarısız (%s) — ilk yanıt kullanılıyor.",
                       name, exc)
        return data, used
    notes2 = _quality_notes(data2, lang)
    if len(notes2) > len(notes):
        logger.warning("[%s] tekrar deneme daha sorunlu — ilk yanıt kullanılıyor.", name)
        data2, used2, notes2 = data, used, notes
    if notes2:
        logger.warning("[%s] tekrar denemeden sonra kalan sorun (metin olduğu gibi tutuldu, "
                       "uzun hüküm son tam cümlede kesilecek): %s", name, " | ".join(notes2))
    return data2, used2


def _assess_with_truncation_recovery(client, build_fn, payload, name):
    """Entity değerlendirmesini (TEK çağrı → batch gibi bölünemez) kesilmeye karşı
    kurtarmalı çalıştırır. (adata, kullanılan_payload) döner.

    Sıra: (1) settings.max_output_tokens ile dene → kesilirse (2) 2× token ile yeniden →
    yine kesilirse (3) bağlam makalelerini YARIYA indirip 2× token ile son bir kez.
    Böylece entity tamamen değerlendirmesiz (boş kart) kalmaz. Son deneme de kesilirse
    TruncationError (ClaudeError alt sınıfı) yükselir; çağıran uyarıya çevirir.
    """
    base = get_settings().max_output_tokens
    payload = _fit_assessment_context(client, build_fn, payload, name)
    # Loglarda gerçekten hangi tavanın kullanıldığı görünsün (NEWSRADAR_MAX_OUTPUT_TOKENS
    # okunuyor mu teşhisi için — eskiden sabit 4096'ya bağlıydı).
    logger.info("[%s] değerlendirme çağrısı max_tokens=%d (%d makale bağlam)",
                name, base, len(payload))

    def _one(items, mt):
        return client.call_tool(
            system=SYSTEM_PROMPT, user=build_fn(items),
            tool=ENTITY_ANALYSIS_TOOL, max_tokens=mt,
        )

    try:
        return _one(payload, base), payload
    except TruncationError:
        logger.warning("[%s] değerlendirme kesildi (max_tokens=%d) → 2× (%d) ile yeniden.",
                       name, base, base * 2)
    try:
        return _one(payload, base * 2), payload
    except TruncationError:
        half = max(1, len(payload) // 2)
        logger.warning("[%s] hâlâ kesik → bağlam %d→%d makaleye indirilip 2× token ile deneniyor.",
                       name, len(payload), half)
        used = payload[:half]
        return _one(used, base * 2), used


def _suggestion_key(name: str, ticker: str | None) -> str:
    """Öneri tekilleştirme anahtarı: ticker varsa ona, yoksa isme göre."""
    if ticker:
        return f"t:{ticker.strip().upper()}"
    return f"n:{name.strip().lower()}"


def _accumulate_suggestions(
    session: Session, entity_id: int, source_language: str, co_list: list[dict]
) -> None:
    """Co-mentioned şirketleri suggestions tablosuna yaz/güncelle (upsert).

    source_language: co-mention'ın geldiği entity'nin dili — keyword olarak
    eklenecekse bu dil miras alınır (ilk görülende sabitlenir).
    Gerekçe olarak her şirketin KENDİ `why_relevant`'ı kullanılır (makale-alaka
    gerekçesi DEĞİL — o iç not kullanıcıya sızmasın).
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for c in co_list:
        why = c.get("why_relevant")
        key = _suggestion_key(c["name"], c["ticker"])
        sug = session.scalar(select(Suggestion).where(Suggestion.norm_key == key))
        if sug is None:
            session.add(
                Suggestion(
                    name=c["name"], ticker=c["ticker"], is_public=c["is_public"],
                    country=c.get("country"), exchange=c.get("exchange"),
                    source_language=source_language or "en",
                    norm_key=key, mention_count=1, source_entity_ids=[entity_id],
                    why_relevant=why, first_seen_at=now, last_seen_at=now,
                )
            )
            # autoflush=False: aynı session'da sonraki aynı-şirket aramaları bunu
            # bulabilsin diye hemen flush et (yoksa mükerrer insert → unique hatası).
            session.flush()
        else:
            sug.mention_count += 1
            sug.last_seen_at = now
            if why:
                sug.why_relevant = why  # en güncel şirket-özel gerekçe
            # Eksik bilgiyi sonradan öğrenilirse doldur.
            if not sug.ticker and c["ticker"]:
                sug.ticker = c["ticker"]
            if sug.is_public is None and c["is_public"] is not None:
                sug.is_public = c["is_public"]
            if not sug.country and c.get("country"):
                sug.country = c["country"]
            if not sug.exchange and c.get("exchange"):
                sug.exchange = c["exchange"]
            ids = list(sug.source_entity_ids or [])
            if entity_id not in ids:
                ids.append(entity_id)
                sug.source_entity_ids = ids  # yeni liste ata → değişiklik algılansın


def reconcile_prefilter() -> int:
    """Eski ön-filtre sürümüyle elenmiş makaleleri yeniden değerlendirmeye açar.

    prefiltered=True ama prefilter_version güncelin (PREFILTER_VERSION) altındaysa →
    prefiltered=False. Böylece kural değişince (sürüm artınca) açılışta bir kez etkili
    olur; idempotent (sıfırlanan satırlar bir daha eşleşmez). Render'da da otomatik çalışır.

    Not: yalnızca bayrağı açar — makaleler bir sonraki yenilemede analiz edilir.
    """
    with session_scope() as session:
        result = session.execute(
            update(Article)
            .where(
                Article.prefiltered.is_(True),
                Article.prefilter_version < PREFILTER_VERSION,
            )
            .values(prefiltered=False)
        )
        return result.rowcount or 0


def prune_stale_suggestions() -> int:
    """30 günden beri görülmemiş ve hâlâ az anılan (<3) önerileri temizler."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=SUGGESTION_TTL_DAYS)
    with session_scope() as session:
        stale = session.scalars(
            select(Suggestion.id).where(
                Suggestion.mention_count < 3, Suggestion.last_seen_at < cutoff
            )
        ).all()
        if stale:
            session.execute(delete(Suggestion).where(Suggestion.id.in_(stale)))
        return len(stale)


@dataclass
class AnalyzeTotals:
    """Tüm yenileme için analiz sayaçları."""

    prefiltered: int = 0        # ön-filtrede elenen (Claude'a hiç gitmedi)
    analyzed: int = 0           # makale-başı analiz edilen
    discarded: int = 0          # relevance < eşik → elenen
    entity_assessments: int = 0  # entity-başı değerlendirme üretilen
    assessments_skipped: int = 0  # yeni veri olmadığı için atlanan değerlendirme (dil başına)
    returned: int = 0           # Claude'un döndürdüğü toplam analiz (teşhis)
    unmatched: int = 0          # döndürülüp bu entity'ye eşleşmeyen id (teşhis)
    selected: int = 0           # _prefilter'ın batch'e seçtiği makale sayısı (teşhis)
    warnings: list[str] = field(default_factory=list)
    quota_error: bool = False   # sağlayıcı kalıcı kota/bakiye hatası → tarama erken durdu
    quota_status_code: int | None = None  # 402/403 (sağlık paneli/teşhis)


# ------------------------------ Ön-filtre ------------------------------ #
def _normalize(text: str) -> str:
    """Türkçe-güvenli normalizasyon: casefold + aksan/özel karakter duyarsız.

    Python `.lower()` Türkçe için güvenilir değil (İ/ı, Ş, Ğ). Bunun yerine
    casefold + Unicode NFKD ile birleştirici işaretleri (aksan/çengel) atarız;
    böylece "ASELSAN'IN", "Türk", "Şişe" gibi haller ASCII karşılıklarıyla eşleşir.
    """
    text = (text or "").casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Türkçe dotless ı (U+0131) NFKD ile ayrışmaz; noktalı i ile birleştir ki
    # "Bankası" (ı) ↔ "BANKASI" (ascii I→i) eşleşsin. (ş/ğ/ç/ö/ü zaten NFKD ile çözülür.)
    return text.replace("ı", "i")


def _match_terms(name: str, query: str) -> list[str]:
    """Bir makalenin bu entity'ye ait olup olmadığını ucuza sınamak için terimler.

    Terimler normalize edilmiş (Türkçe-güvenli) döner.
    """
    terms: set[str] = set()
    for t in (query, name):
        t = _normalize((t or "").strip())
        if len(t) >= 2:
            terms.add(t)
    # Çok kelimeli adlarda tek tek kelimeler de eşleşsin (ör. "Berkshire Hathaway").
    for w in _normalize(name or "").split():
        if len(w) >= 3:
            terms.add(w)
    return list(terms)


_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "will",
    "ve", "ile", "bir", "icin", "ama", "gibi", "olan", "daha", "ihracat",
}


def _title_tokens(title: str) -> frozenset[str]:
    """Başlığı anlamlı kelime kümesine indirger (Türkçe-güvenli, stopword'süz)."""
    return frozenset(
        w for w in _normalize(title or "").split()
        if len(w) >= 4 and w not in _STOPWORDS
    )


def _titles_similar(t1: frozenset, t2: frozenset, thresh: float = 0.6) -> bool:
    """İki başlık kümesi aynı hikâye mi? Jaccard benzerliği eşiği (senkron kopyaları yakalar)."""
    if not t1 or not t2:
        return False
    inter = len(t1 & t2)
    union = len(t1 | t2)
    return union > 0 and inter / union >= thresh


def _dedup_by_title(articles: list[Article]) -> tuple[list[Article], int]:
    """Aynı haberin farklı kaynaklardaki kopyalarını TEK veri noktasına indirger.

    Başlık benzerliğiyle kümeler; her kümeden bir TEMSİLCİ (en uzun açıklamalı) LLM'e
    gider, kalan kopyalar prefiltered=True işaretlenir (sentiment 3 kez sayılmaz).
    Temsilcinin source_count'u = kümedeki kopya sayısı (ÖNEM sinyali korunur).
    Döner: (temsilciler [yeniden→eskiye], elenen kopya sayısı).
    """
    clusters: list[dict] = []  # {tokens, members}
    for a in articles:
        toks = _title_tokens(a.title)
        placed = False
        for c in clusters:
            if _titles_similar(toks, c["tokens"]):
                c["members"].append(a)
                placed = True
                break
        if not placed:
            clusters.append({"tokens": toks, "members": [a]})

    reps: list[Article] = []
    duplicates = 0
    for c in clusters:
        members = c["members"]
        # Temsilci: en uzun açıklama (LLM'e en çok bağlam). Eşitlikte ilk (en yeni).
        rep = max(members, key=lambda a: len(a.description or ""))
        rep.source_count = len(members)
        reps.append(rep)
        for a in members:
            if a is not rep:
                a.prefiltered = True
                a.prefilter_version = PREFILTER_VERSION
                duplicates += 1
    # En yeni önce, tarihsizler sona (tavan uygulanınca güncel haberler öncelikli).
    reps.sort(key=lambda a: a.published_at or datetime.min, reverse=True)
    return reps, duplicates


def _prefilter(session: Session, entity: Entity, max_articles: int) -> tuple[list[dict], int]:
    """Bekleyen makaleleri ön-filtreden geçirir; kabul edilenlerin payload'ını döner.

    ÖNEMLİ: Hem Finnhub (company-news, ticker'a göre) hem NewsAPI (arama terimine
    göre) haberleri ZATEN entity'ye göre filtreliyor. Bu durumda ikinci bir
    başlık-eşleşme kapısı gereksiz ve YANLIŞ eler — ör. "Lisa Su unveils Helios"
    başlığında 'AMD' geçmez ama Finnhub bunu AMD haberi olarak döndürür. Bu yüzden
    sağlayıcı entity-filtreliyse ön-filtre ATLANIR; alaka güvencesi tamamen
    Claude'un relevance<0.3 elemesindedir.

    Yalnızca sağlayıcı entity-filtreli DEĞİLSE (gelecekteki genel bir kaynak) sıkı
    başlık-eşleşme ön-filtresi uygulanır.
    Döner: (payload listesi, ön-filtrede elenen sayısı).
    """
    pending: list[Article] = list(
        session.scalars(
            select(Article)
            .where(
                Article.entity_id == entity.id,
                Article.analyzed.is_(False),
                Article.prefiltered.is_(False),
            )
            .order_by(Article.published_at.desc().nullslast())
        ).all()
    )

    provider = get_provider_for(entity)
    entity_filtered = provider.entity_filtered if provider else False

    # GEVŞEK: sağlayıcı zaten entity'ye göre filtreli → eleme yok, ama TEKRARLARI birleştir.
    if entity_filtered:
        reps, duplicates = _dedup_by_title(pending)  # kopyalar prefiltered işaretlenir
        capped = reps if max_articles <= 0 else reps[:max_articles]
        payload = [
            {"id": a.id, "title": a.title, "source": a.source, "description": a.description}
            for a in capped
        ]
        return payload, duplicates

    # SIKI (yalnızca entity-filtreli OLMAYAN kaynaklar için): Türkçe-güvenli başlık
    # eşleşmesi; başlık/açıklamada isim geçmeyenler elenir.
    terms = _match_terms(entity.name, entity.query)
    kept: list[Article] = []
    prefiltered = 0
    for a in pending:
        haystack = _normalize(f"{a.title} {a.description or ''}")
        if terms and any(term in haystack for term in terms):
            kept.append(a)
        else:
            a.prefiltered = True
            a.prefilter_version = PREFILTER_VERSION
            prefiltered += 1

    # Kalanların da tekrarlarını birleştir (aynı hikâye çok kaynakta).
    reps, duplicates = _dedup_by_title(kept)
    prefiltered += duplicates
    capped = reps if max_articles <= 0 else reps[:max_articles]
    payload = [
        {"id": a.id, "title": a.title, "source": a.source, "description": a.description}
        for a in capped
    ]
    return payload, prefiltered


# ------------------------- DB yazma yardımcıları ------------------------- #
# Bunlar to_thread ile ayrı thread'de ama tek bir asyncio kilidiyle SIRAYLA
# çağrılır — aynı anda tek SQLite yazarı olur (WAL + 'locked' güvenliği).
def _apply_article_results(entity_id: int, batch_datas: list[dict]) -> dict:
    """Makale-başı analiz sonuçlarını DB'ye yazar; alakasızları eler."""
    analyzed = 0
    discarded = 0
    returned = 0    # Claude'un döndürdüğü toplam analiz sayısı
    unmatched = 0   # döndürülen ama bu entity'nin makalesine eşleşmeyen id (Claude id uydurmuş/karıştırmış)
    invalid = 0     # sanitize edilemeyen (bozuk şema) analiz
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_scope() as session:
        source_entity = session.get(Entity, entity_id)
        source_language = source_entity.language if source_entity else "en"
        for data in batch_datas:
            for raw in data.get("analyses", []):
                returned += 1
                try:
                    clean = sanitize_article_analysis(raw)
                except (KeyError, ValueError, TypeError):
                    invalid += 1
                    continue
                article = session.get(Article, clean["id"])
                if article is None or article.entity_id != entity_id:
                    # Claude, gönderilmeyen ya da başka entity'nin id'sini döndürdü →
                    # sessizce kaybolurdu; artık sayılır ve loglanır.
                    unmatched += 1
                    continue
                if clean["relevance"] < RELEVANCE_THRESHOLD:
                    session.delete(article)  # alakasız → panelde gürültü tutma
                    discarded += 1
                    continue
                article.sentiment = clean["sentiment"]
                article.event_type = clean["event_type"]
                article.risk_flags = clean["risk_flags"]
                article.impact_horizon = clean["impact_horizon"]
                article.relevance = clean["relevance"]
                article.rationale = clean["rationale"]
                article.analyzed = True
                article.analyzed_at = now
                analyzed += 1
                # Öneri biriktir: yalnızca İLGİLİ (kalan) makalelerin co-mention'ları.
                if clean.get("co_mentioned"):
                    _accumulate_suggestions(
                        session, entity_id, source_language, clean["co_mentioned"]
                    )
    return {
        "analyzed": analyzed, "discarded": discarded,
        "returned": returned, "unmatched": unmatched, "invalid": invalid,
    }


def _read_assessment_payload(entity_id: int) -> list[dict]:
    """Entity değerlendirmesi için son analiz edilmiş makalelerden bağlam payload'ı.

    Lookback TAVANLA (max_articles_per_entity) tutarlı: 20'ye kilitlenmez; 40 makale
    analiz edildiyse değerlendirme (ve karttaki 'N haber') 40'a kadar yansır.
    Tavan SINIRSIZ (0) ise değerlendirme okuması tek prompt'u şişirmesin diye makul
    bir tavanla (ASSESSMENT_READ_CAP) sınırlanır."""
    cap = get_settings().max_articles_per_entity
    lookback = ASSESSMENT_READ_CAP if cap <= 0 else max(AGGREGATE_LOOKBACK, cap)
    with session_scope() as session:
        articles = session.scalars(
            select(Article)
            .where(Article.entity_id == entity_id, Article.analyzed.is_(True))
            .order_by(Article.published_at.desc().nullslast())
            .limit(lookback)
        ).all()
        return [
            {
                "title": a.title,
                "sentiment": a.sentiment or 0.0,
                "event_type": a.event_type or "other",
                "impact_horizon": a.impact_horizon or "short",
                "risk_flags": a.risk_flags or [],
                "rationale": a.rationale or "",
                "source_count": a.source_count or 1,
            }
            for a in articles
        ]


def _assessment_due(entity_id: int, language: str) -> str | None:
    """Bu dilde yeni değerlendirme gerekiyorsa SEBEBİNİ, gerekmiyorsa None döndürür."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_scope() as session:
        last_at = session.scalar(
            select(EntityAnalysis.created_at)
            .where(EntityAnalysis.entity_id == entity_id, EntityAnalysis.language == language)
            .order_by(EntityAnalysis.created_at.desc())
            .limit(1)
        )
        if last_at is None:
            return "ilk değerlendirme"
        if now - last_at > timedelta(hours=ASSESSMENT_MAX_AGE_HOURS):
            return f"son değerlendirme {ASSESSMENT_MAX_AGE_HOURS} saatten eski"
        new_articles = session.scalar(
            select(Article.id)
            .where(Article.entity_id == entity_id, Article.analyzed.is_(True),
                   Article.analyzed_at > last_at)
            .limit(1)
        )
        if new_articles is not None:
            return "yeni analiz edilmiş makale var"
        latest = session.scalar(
            select(PriceSnapshot.price).where(PriceSnapshot.entity_id == entity_id)
            .order_by(PriceSnapshot.fetched_at.desc()).limit(1)
        )
        then = session.scalar(
            select(PriceSnapshot.price)
            .where(PriceSnapshot.entity_id == entity_id, PriceSnapshot.fetched_at <= last_at)
            .order_by(PriceSnapshot.fetched_at.desc()).limit(1)
        )
        if latest and then:
            move = (latest - then) / then * 100
            if abs(move) >= ASSESSMENT_PRICE_MOVE_PCT:
                return f"fiyat %{move:+.1f} oynadı"
    return None


def _assessment_langs(entity_id: int, name: str, force: bool = False) -> list[str]:
    """Değerlendirilecek diller (tr/en); gereksizler loglanıp atlanır."""
    langs = []
    for lang in ("tr", "en"):
        reason = "zorla" if force else _assessment_due(entity_id, lang)
        if reason is None:
            logger.info("[%s] değerlendirme atlandı: yeni veri yok (%s)", name, lang)
        else:
            logger.info("[%s] değerlendirme yapılacak (%s): %s", name, lang, reason)
            langs.append(lang)
    return langs


def _avg_sentiment(payload: list[dict]) -> float | None:
    """Değerlendirmeye giren makalelerin ortalama duygusu (snapshot için)."""
    vals = [p.get("sentiment") for p in payload if p.get("sentiment") is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def _write_assessment(entity_id: int, data: dict, considered: int,
                      avg_sentiment: float | None, language: str = "tr") -> None:
    """Entity-başı değerlendirmeyi APPEND-ONLY kaydeder (DİL BAŞINA) ve geçmişi sınırlar.

    Aynı taramada tr ve en ayrı satır yazılır; geçmiş DİL BAŞINA 100 kayıtla sınırlanır ki
    delta/risk-geçmişi aynı dildeki kayıtlar arasında tutarlı kalsın."""
    clean = sanitize_entity_analysis(data, language)
    with session_scope() as session:
        session.add(
            EntityAnalysis(
                entity_id=entity_id,
                language=language,
                headline_verdict=clean["headline_verdict"],
                ai_take=clean["ai_take"],
                risk_score=clean["risk_score"],
                sentiment_trend=clean["sentiment_trend"],
                top_drivers=clean["top_drivers"],
                summary=clean["summary"],
                stance=clean["stance"],
                conviction=clean["conviction"],
                what_to_verify=clean["what_to_verify"],
                invalidation=clean["invalidation"],
                articles_considered=considered,
                avg_sentiment=avg_sentiment,
            )
        )
        session.flush()
        # DB şişmesin: bu DİLDE en yeni 100 dışındaki eski kayıtları temizle.
        stale = session.scalars(
            select(EntityAnalysis.id)
            .where(EntityAnalysis.entity_id == entity_id, EntityAnalysis.language == language)
            .order_by(EntityAnalysis.created_at.desc())
            .offset(MAX_ANALYSIS_HISTORY)
        ).all()
        if stale:
            session.execute(delete(EntityAnalysis).where(EntityAnalysis.id.in_(stale)))


# ------------------------- Paralel orkestrasyon ------------------------- #
async def analyze_all_async(
    client: ClaudeClient,
    progress_cb=None,
    entity_cb=None,
    entity_ids: set[int] | None = None,
    assess_client=None,
) -> AnalyzeTotals:
    """Aktif entity'ler için ön-filtre + paralel analiz + değerlendirme.

    client: makale-batch analizi; assess_client: entity değerlendirmesi (ayrı model
    olabilir — NEWSRADAR_ASSESSMENT_MODEL). Verilmezse ikisi için de `client` kullanılır.

    entity_ids verilirse yalnızca o entity'ler işlenir (kişisel elle yenileme);
    None ise tüm aktif entity'ler (scheduler). progress_cb(done, total): her entity
    tamamlandığında çağrılır (ilerleme kişisel elle yenilemede kullanıcının listesine göre).
    entity_cb(name): bir entity analize BAŞLADIĞINDA çağrılır (UI 'X analiz ediliyor…').
    """
    settings = get_settings()
    batch_size = max(1, settings.batch_size)
    max_articles = settings.max_articles_per_entity  # 0 = sınırsız (_prefilter yorumlar)
    concurrency = max(1, settings.analysis_concurrency)
    assess_client = assess_client or client

    # SİSTEM BÜTÇE TAVANI (canlı, USD): her çağrı llm_usage'a anında yazıldığı için bugünkü
    # harcama DB'den okunur; tavana ulaşılırsa YENİ entity/değerlendirme başlatılmaz.
    from ..budget import is_budget_exceeded

    def _over_budget() -> bool:
        return is_budget_exceeded()

    totals = AnalyzeTotals()

    # --- Aşama 1: ön-filtre + batch listesi (DB, tek thread) ---
    entity_tasks: list[dict] = []
    with session_scope() as session:
        q = select(Entity).where(Entity.active.is_(True))
        if entity_ids is not None:
            q = q.where(Entity.id.in_(entity_ids))
        entities = session.scalars(q).all()
        for e in entities:
            # Tek entity'nin ön-filtresi beklenmedik hata atsa BİLE diğerleri işlensin.
            # (Bu döngü _process_entity_safe DIŞINDA; sarılmazsa tek entity tüm
            #  analizi çökertir — 'çekiliyor ama analiz edilmiyor' tuzağı.)
            try:
                payload, pre = _prefilter(session, e, max_articles)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Ön-filtre çöktü, entity atlandı: %s", e.name)
                totals.warnings.append(f"[{e.name}] ön-filtre hatası (atlandı): {exc}")
                continue
            totals.prefiltered += pre
            ebs = _effective_batch_size(batch_size, e.language)  # Türkçe → yarı batch
            batches = [payload[i : i + ebs] for i in range(0, len(payload), ebs)]
            # Entity-başı görünürlük: hangi entity kaç makaleyle analize giriyor.
            # "analiz=23 ama AMD 0" gibi durumlar loglardan tek bakışta çözülür.
            logger.info(
                "[analiz] %s (id=%d, %s:%s) → analize=%d ön-filtre=%d batch=%d (batch_size=%d)",
                e.name, e.id, e.type, e.query, len(payload), pre, len(batches), ebs,
            )
            entity_tasks.append(
                {
                    "id": e.id, "name": e.name, "query": e.query, "type": e.type,
                    "language": e.language, "batches": batches,
                }
            )
        # session çıkışında prefiltered işaretleri commit edilir.

    total = len(entity_tasks)
    done = 0
    if progress_cb:
        progress_cb(done, total)

    sem = asyncio.Semaphore(concurrency)
    db_lock = asyncio.Lock()

    # Sağlayıcı KALICI kota/bakiye hatası (402/403): İLK alındığında bu yenilemenin TÜM
    # kalan LLM çağrılarını durdur (yeniden deneme YOK) ve TEK uyarı ver. Aksi halde her
    # batch tek tek aynı 403'ü alır → 89 aynı uyarı + boşa token yakımı.
    _quota_stopped = {"flag": False}

    def _note_quota(exc: ProviderQuotaError) -> None:
        """İlk kota hatasını işaretle + TEK uyarı. Idempotent (sonrakiler sessiz)."""
        if _quota_stopped["flag"]:
            return
        _quota_stopped["flag"] = True
        totals.quota_error = True
        totals.quota_status_code = getattr(exc, "status_code", None)
        totals.warnings.append(
            "Analiz servisi geçici olarak kullanılamıyor (sağlayıcı kapasite/bakiye "
            "limiti) — bu yenilemede analiz durduruldu, çekilen haberler kaydedildi."
        )
        logger.error("[quota] Sağlayıcı kota hatası — kalan LLM çağrıları durduruldu: %s", exc)

    async def _call(tool, user, max_tokens):
        """Semaphore altında tek Claude çağrısı (sync istemci → to_thread).

        Kota durduysa ağa HİÇ çıkma — anında iptal (uyarı zaten bir kez verildi)."""
        if _quota_stopped["flag"]:
            raise ProviderQuotaError("Analiz durduruldu (kota).", None)
        async with sem:
            if _quota_stopped["flag"]:
                raise ProviderQuotaError("Analiz durduruldu (kota).", None)
            try:
                return await asyncio.to_thread(
                    client.call_tool,
                    system=SYSTEM_PROMPT,
                    user=user,
                    tool=tool,
                    max_tokens=max_tokens,
                )
            except ProviderQuotaError as exc:
                _note_quota(exc)
                raise

    async def _run_batch(t: dict, b: list[dict], depth: int = 0):
        """Bir batch'i analiz eder. YALNIZCA KESİLME'de (TruncationError) batch'i ikiye
        bölüp yeniden dener; en kötü ihtimalle tek problemli makale kaybedilir. Kesilme
        DIŞI hatalar (rate limit/bağlantı/API) bölünmez — uyar + devam."""
        user = build_article_batch_prompt(t["name"], t["query"], t["type"], b, t["language"])
        try:
            return await _call(ARTICLE_ANALYSIS_TOOL, user, settings.max_output_tokens)
        except ProviderQuotaError:
            return None  # kota durdu — tek uyarı _note_quota'da; batch başına uyarı YOK
        except TruncationError as exc:
            if len(b) <= 1:
                aid = b[0].get("id", "?") if b else "?"
                totals.warnings.append(
                    f"[{t['name']}] makale #{aid} analiz edilemedi: yanıt kesildi, "
                    "makale çok uzun olabilir")
                return None
            if depth >= _MAX_SPLIT_DEPTH:
                totals.warnings.append(
                    f"[{t['name']}] {len(b)} makale atlandı: bölme sınırına ulaşıldı, "
                    "yanıt hâlâ kesiliyor")
                return None
            mid = len(b) // 2
            logger.info("[analiz] %s batch kesildi (%d makale) → %d+%d olarak yeniden deneniyor",
                        t["name"], len(b), mid, len(b) - mid)
            halves = await asyncio.gather(
                _run_batch(t, b[:mid], depth + 1), _run_batch(t, b[mid:], depth + 1)
            )
            merged: list[dict] = []
            for h in halves:
                if h:
                    merged.extend(h.get("analyses", []))
            return {"analyses": merged} if merged else None
        except ClaudeError as exc:
            # Kesilme DIŞI hata → bölme YOK (tekrar denemek aynı hatayı verir + token yakar).
            totals.warnings.append(f"[{t['name']}] batch analiz hatası (bölünmedi): {exc}")
            return None

    _budget_stopped = {"flag": False}

    def _note_budget() -> None:
        """Bütçe dolduğunda TEK uyarı (idempotent)."""
        if not _budget_stopped["flag"]:
            _budget_stopped["flag"] = True
            totals.warnings.append(
                "Günlük analiz bütçesi doldu — kalan analizler bu turda atlandı, yarın "
                "yeniden denenecek."
            )
            logger.warning("[budget] Günlük USD bütçesi tarama sırasında doldu — kalan "
                           "analizler atlanıyor.")

    async def _process_entity(t: dict):
        nonlocal done
        # KOTA DURDU: kalan entity'lere hiç başlama (LLM çağrısı yok), yalnızca ilerlemeyi say.
        if _quota_stopped["flag"]:
            done += 1
            if progress_cb:
                progress_cb(done, len(entity_tasks))
            return
        # SİSTEM BÜTÇE: tavana ulaşıldıysa bu entity'nin LLM çağrılarını YAPMA (atla).
        if _over_budget():
            _note_budget()
            done += 1
            if progress_cb:
                progress_cb(done, len(entity_tasks))
            return
        # UI: bu entity analize başladı → "X analiz ediliyor…" (eşzamanlı olduğu için
        # en son başlayan görünür; kullanıcıya taramanın canlı ve nerede olduğunu gösterir).
        if entity_cb:
            entity_cb(t["name"])
        # 1) Makale batch'leri — hepsi paralel (global semaphore ile sınırlı).
        #    Batch'ler hem entity içinde hem entity'ler arası eşzamanlı çalışır;
        #    aynı anda en fazla `concurrency` çağrı olur.
        raw = await asyncio.gather(*[_run_batch(t, b) for b in t["batches"]])
        batch_datas: list[dict] = [d for d in raw if d]

        # 2) Sonuçları yaz (DB kilidi altında, sırayla).
        async with db_lock:
            applied = await asyncio.to_thread(_apply_article_results, t["id"], batch_datas)
        totals.analyzed += applied["analyzed"]
        totals.discarded += applied["discarded"]
        totals.returned += applied["returned"]
        totals.unmatched += applied["unmatched"]
        # SESSİZ ARIZA KORUMASI: makale gönderdik ama LLM 0 analiz döndürdüyse
        # (ör. geçersiz model, boş yanıt) bunu bir uyarı olarak yüzeye çıkar — beş tur
        # teşhise mal olan "sessizce 0" durumu bir daha görünmez kalmasın.
        # KOTA DURDUYSA istisna: 0 analiz beklenen sonuçtur (kota uyarısı zaten verildi) →
        # entity başına "0 analiz" uyarısı EKLEME (aksi halde kota yine N uyarı biriktirir).
        if t["batches"] and applied["returned"] == 0 and not _quota_stopped["flag"]:
            totals.warnings.append(
                f"[{t['name']}] LLM 0 analiz döndürdü ({len(t['batches'])} batch "
                "gönderildi) — model/endpoint sorunu olabilir (NEWSRADAR_LLM_MODEL?)."
            )
        # Entity-başı sonuç: batch geldi mi, kaç analiz/eleme oldu. AMD gibi takılan
        # bir entity'nin batch_datas boşsa (Claude hatası) burada görünür.
        logger.info(
            "[analiz] %s → batch_yanıt=%d/%d claude_döndürdü=%d eşleşmedi=%d bozuk=%d "
            "analiz=%d elenen=%d",
            t["name"], len(batch_datas), len(t["batches"]),
            applied["returned"], applied["unmatched"], applied["invalid"],
            applied["analyzed"], applied["discarded"],
        )

        # 3) Değerlendirme gerekli mi (dil başına: yeni makale / fiyat ≥%3 / 24s)? Gerekliyse
        #    payload + fiyat bağlamını oku (DB), Claude çağır, yaz.
        async with db_lock:
            langs = await asyncio.to_thread(_assessment_langs, t["id"], t["name"])
        totals.assessments_skipped += 2 - len(langs)
        payload = []
        if langs:
            async with db_lock:
                payload = await asyncio.to_thread(_read_assessment_payload, t["id"])
                price_ctx = await asyncio.to_thread(price_context_for, t["id"])
                analyst_ctx = await asyncio.to_thread(analyst_context_for, t["id"])
        if payload:
            # İKİ DİLDE değerlendirme: arayüzü İngilizce olan kullanıcı içeriği de
            # İngilizce görsün. Makale analizi tek sefer; bu yalnızca +1 çağrı/dil.
            for out_lang in langs:
                if _quota_stopped["flag"]:
                    break  # kota durdu → dil döngüsünü de kes (yeniden deneme yok)
                if await asyncio.to_thread(_over_budget):
                    _note_budget()
                    break
                def _build(items, _ol=out_lang):
                    return build_entity_prompt(
                        t["name"], t["query"], t["type"], items,
                        price=price_ctx, language=t["language"], analyst=analyst_ctx,
                        out_lang=_ol,
                    )
                try:
                    # Kesilme kurtarmalı (2× token → gerekirse yarı bağlam). Semaphore altında.
                    async with sem:
                        if _quota_stopped["flag"]:
                            break
                        adata, used = await asyncio.to_thread(
                            _assess_entity_with_recovery, assess_client, _build, payload,
                            f"{t['name']}/{out_lang}", out_lang,
                        )
                    async with db_lock:
                        await asyncio.to_thread(
                            _write_assessment, t["id"], adata, len(used), _avg_sentiment(used), out_lang
                        )
                    totals.entity_assessments += 1
                except ProviderQuotaError as exc:
                    _note_quota(exc)  # değerlendirme _call'ı kullanmaz → burada işaretle
                    break
                except ClaudeError as exc:
                    totals.warnings.append(f"[{t['name']}/{out_lang}] değerlendirme başarısız: {exc}")

        done += 1
        if progress_cb:
            progress_cb(done, total)

    async def _process_entity_safe(t: dict):
        """Bir entity'nin analizi beklenmedik hata atsa BİLE diğerleri sürsün.

        Aksi halde (return_exceptions=False) tek entity'nin hatası tüm analizi
        çökertir ve o hatadan sonraki entity'ler HİÇ işlenmez — bu, 'makaleler
        çekilmiş ama analiz edilmemiş' takılı durumunun tipik sebebidir.
        """
        nonlocal done
        try:
            await _process_entity(t)
        except Exception as exc:  # noqa: BLE001 — tek entity hatası hattı durdurmasın
            logger.exception("Entity analiz task çöktü: %s", t["name"])
            totals.warnings.append(f"[{t['name']}] analiz beklenmeyen hata (atlandı): {exc}")
            done += 1
            if progress_cb:
                progress_cb(done, total)

    # Tüm entity'ler eşzamanlı; Claude çağrıları semaphore ile sınırlı. Hata izole.
    await asyncio.gather(*[_process_entity_safe(t) for t in entity_tasks])

    # Bakım: tablo şişmesin diye eski/az anılan önerileri temizle.
    async with db_lock:
        await asyncio.to_thread(prune_stale_suggestions)

    return totals


def analyze_entity_sync(entity_id: int, client: ClaudeClient, assess_client=None,
                        force_assessment: bool = False) -> AnalyzeTotals:
    """CLI/test için tek entity'yi senkron analiz eder (ön-filtre + batch + değerlendirme).

    assess_client verilmezse değerlendirme de `client` ile yapılır. Değerlendirme
    yenilemedeki kuralla aynı şekilde atlanabilir; force_assessment=True her iki dili zorlar."""
    settings = get_settings()
    assess_client = assess_client or client
    batch_size = max(1, settings.batch_size)
    max_articles = settings.max_articles_per_entity  # 0 = sınırsız (_prefilter yorumlar)
    totals = AnalyzeTotals()

    with session_scope() as session:
        entity = session.get(Entity, entity_id)
        if entity is None:
            logger.warning("[analiz] entity id=%d bulunamadı — atlandı.", entity_id)
            return totals
        name, query, etype, lang = entity.name, entity.query, entity.type, entity.language
        payload, pre = _prefilter(session, entity, max_articles)
        totals.prefiltered += pre
        totals.selected = len(payload)
        # analyze_all_async ile AYNI seçim yolu; CLI'de de ne seçildiği görünsün.
        logger.info(
            "[analiz] %s (id=%d, %s:%r) → analize=%d ön-filtre=%d",
            name, entity_id, etype, query, len(payload), pre,
        )

    ebs = _effective_batch_size(batch_size, lang)  # Türkçe → yarı batch
    batches = [payload[i : i + ebs] for i in range(0, len(payload), ebs)]

    def run_batch_sync(b, depth: int = 0):
        """YALNIZCA KESİLME'de (TruncationError) batch'i ikiye bölüp yeniden dener
        (recursive; en kötü tek makale kaybı). Kesilme dışı hatalar bölünmez."""
        user = build_article_batch_prompt(name, query, etype, b, lang)
        try:
            return client.call_tool(
                system=SYSTEM_PROMPT, user=user, tool=ARTICLE_ANALYSIS_TOOL,
                max_tokens=settings.max_output_tokens,
            )
        except TruncationError as exc:
            if len(b) <= 1:
                aid = b[0].get("id", "?") if b else "?"
                totals.warnings.append(
                    f"[{name}] makale #{aid} analiz edilemedi: yanıt kesildi, "
                    "makale çok uzun olabilir")
                return None
            if depth >= _MAX_SPLIT_DEPTH:
                totals.warnings.append(
                    f"[{name}] {len(b)} makale atlandı: bölme sınırına ulaşıldı, "
                    "yanıt hâlâ kesiliyor")
                return None
            mid = len(b) // 2
            logger.info("[analiz] %s batch kesildi (%d makale) → %d+%d olarak yeniden deneniyor",
                        name, len(b), mid, len(b) - mid)
            merged: list[dict] = []
            for half in (b[:mid], b[mid:]):
                r = run_batch_sync(half, depth + 1)
                if r:
                    merged.extend(r.get("analyses", []))
            return {"analyses": merged} if merged else None
        except ClaudeError as exc:
            totals.warnings.append(f"[{name}] batch analiz hatası (bölünmedi): {exc}")
            return None

    batch_datas: list[dict] = []
    for b in batches:
        r = run_batch_sync(b)
        if r:
            batch_datas.append(r)

    applied = _apply_article_results(entity_id, batch_datas)
    totals.analyzed += applied["analyzed"]
    totals.discarded += applied["discarded"]
    logger.info(
        "[analiz] %s → batch_yanıt=%d/%d claude_döndürdü=%d eşleşmedi=%d bozuk=%d "
        "analiz=%d elenen=%d",
        name, len(batch_datas), len(batches), applied["returned"],
        applied["unmatched"], applied["invalid"], applied["analyzed"], applied["discarded"],
    )
    # Bu sayaçları CLI özetinde göstermek için totals'a iliştir (opsiyonel alanlar).
    totals.returned = applied["returned"]
    totals.unmatched = applied["unmatched"]
    # SESSİZ ARIZA KORUMASI (bkz. _process_entity): batch gönderildi ama 0 döndüyse uyar.
    if batches and applied["returned"] == 0:
        totals.warnings.append(
            f"[{name}] LLM 0 analiz döndürdü ({len(batches)} batch gönderildi) — "
            "model/endpoint sorunu olabilir (NEWSRADAR_LLM_MODEL?)."
        )

    langs = _assessment_langs(entity_id, name, force=force_assessment)
    totals.assessments_skipped += 2 - len(langs)
    payload2 = _read_assessment_payload(entity_id) if langs else []
    if payload2:
        _price = price_context_for(entity_id)
        _analyst = analyst_context_for(entity_id)
        for out_lang in langs:
            def _build2(items, _ol=out_lang):
                return build_entity_prompt(
                    name, query, etype, items, price=_price, language=lang,
                    analyst=_analyst, out_lang=_ol,
                )
            try:
                # Kesilme kurtarmalı (settings.max_output_tokens → 2× → yarı bağlam).
                adata, used = _assess_entity_with_recovery(
                    assess_client, _build2, payload2, f"{name}/{out_lang}", out_lang)
                _write_assessment(entity_id, adata, len(used), _avg_sentiment(used), out_lang)
                totals.entity_assessments += 1
            except ClaudeError as exc:
                totals.warnings.append(f"[{name}/{out_lang}] değerlendirme başarısız: {exc}")

    return totals
