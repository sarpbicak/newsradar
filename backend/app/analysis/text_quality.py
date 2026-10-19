"""Kullanıcıya gösterilen metinlerin kalite kuralları — TEK yerde.

Ana kural: kullanıcının gördüğü hiçbir alan cümle ortasında bitmez.
- Uzunluğu PROMPT yönetir (hedef sınırlar: PROMPT_LIMITS).
- Koddaki tavanlar (HARD_CAPS) yalnızca EMNİYET: aşılırsa metin, sınır içindeki SON TAM
  CÜMLENİN sonunda kesilir. Sınır içinde hiç cümle sonu yoksa kesilmez — metin olduğu gibi
  bırakılır ve loglanır. Yarım cümle, tam ama uzun cümleden her zaman daha kötüdür.
- Şablon kalıpları: BANNED_PATTERNS (regex denetim; okunur hali BANNED_PHRASES prompt'a
  yasak olarak yazılır, eval'de denetlenir) ve
  entity'ler arasında tekrar eden 3+ kelimelik öbekler (repeated_ngrams).
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

logger = logging.getLogger("newsradar.text")

# Prompt'ta modele verilen hedef sınırlar (kelime).
PROMPT_LIMITS = {
    "headline_verdict": {"tr": 14, "en": 16},
    "ai_take": 100,
}

# Koddaki EMNİYET tavanları (kelime). Normalde prompt sınırları yeter; bunlar yalnızca
# model kuralı ciddi biçimde aştığında devreye girer.
HARD_CAPS = {
    "headline_verdict": {"tr": 28, "en": 30},
    "ai_take": 180,
    "summary": 120,
    "invalidation": 60,
    "top_drivers": 40,       # madde başına
    "what_to_verify": 60,    # madde başına
}


def hard_cap(field: str, language: str) -> int:
    cap = HARD_CAPS[field]
    if isinstance(cap, dict):
        return cap["en" if (language or "tr").lower() == "en" else "tr"]
    return cap


# Şablon kalıpları — her şirkete yapıştırılabilen, bilgi taşımayan yargı öbekleri.
# BANNED_PHRASES: prompt'ta ve tekrar deneme notunda gösterilen OKUNUR liste.
# BANNED_PATTERNS: asıl denetim (regex). Kalıp ailesi: [niceleyici] (+ en fazla bir ara kelime)
# [yön sıfatı] — ara kelime 'ağırlıklı OLARAK olumlu', 'ağırlıkla SERT olumsuz',
# 'mostly VERY negative' gibi hallerini de yakalar. TR sıfat ekleri de sayılır ('olumsuzdu').
BANNED_PHRASES = {
    "tr": [
        "ağırlıklı olarak olumlu/olumsuz", "ağırlıkla/ağırlıkta olumlu/olumsuz",
        "çoğunlukla olumlu/olumsuz", "büyük ölçüde olumlu/olumsuz",
        "genel olarak olumlu/olumsuz",
        "ağırlıklı olarak/çoğunlukla/büyük ölçüde/genel olarak iyimser/kötümser",
        "haberler karışık", "haber akışı karışık",
    ],
    "en": [
        "largely/mostly/predominantly/broadly/generally positive/negative/bullish/bearish/"
        "upbeat/downbeat/optimistic/pessimistic",
        "news flow leans positive/negative", "news flow is mixed",
    ],
}
_GAP = r"(?:\s+[^\W\d_]+)?\s+"  # en fazla bir ara kelime
BANNED_PATTERNS = {
    "tr": [
        re.compile(r"\b(?:ağırlık\w*|çoğunlukla|büyük\s+ölçüde|genel\s+olarak)" + _GAP
                   + r"(?:olumlu|olumsuz|iyimser|kötümser)\w*", re.IGNORECASE),
        re.compile(r"\bhaberler" + _GAP + r"karışık\w*", re.IGNORECASE),
        re.compile(r"\bhaber\s+akışı" + _GAP + r"karışık\w*", re.IGNORECASE),
    ],
    "en": [
        re.compile(r"\b(?:largely|mostly|predominantly|broadly|generally)" + _GAP
                   + r"(?:positive|negative|bullish|bearish|upbeat|downbeat|optimistic|pessimistic)\b",
                   re.IGNORECASE),
        re.compile(r"\bnews\s+flow\s+leans" + _GAP + r"(?:positive|negative)\b", re.IGNORECASE),
        re.compile(r"\bnews\s+flow\s+is" + _GAP + r"mixed\b", re.IGNORECASE),
    ],
}

# Tool-call işaretlemesi sızıntısı: model nadiren bir string alanın içine sonraki
# parametrenin ham XML'ini yazıyor ('…uyuşmuyor.</summary>\n<parameter name="stance">').
# strict mod bunu engelleyemez (yalnızca tipi garanti eder). Etiket = harfle başlayan
# <ad ...> / </ad>; haber metnindeki '<5%' gibi ifadeler eşleşmez.
_MARKUP = re.compile(r"</?[A-Za-z_][\w:.-]*(?:\s[^<>]*)?>")


def has_markup_leak(text: str) -> bool:
    return bool(_MARKUP.search(text or ""))


def strip_markup_leak(text: str, label: str = "") -> str:
    """İlk etiketten itibaren atar (sızan kısım hep metnin sonuna eklenmiş olur)."""
    m = _MARKUP.search(text or "")
    if not m:
        return text
    logger.warning("[metin] %s içinde tool-call işaretlemesi sızmış — ilk etiketten kesildi: %r",
                   label or "alan", text[m.start():m.start() + 60])
    return text[: m.start()].rstrip()


# Cümle sonu: . ! ? … — ardından boşluk/metin sonu gelmeli (ondalık "4.5" cümle sonu değil).
# Kapanış tırnağı/parantezi noktalamadan sonra gelebilir.
_CLOSERS = "\"'”’)»]"
_SENTENCE_END = re.compile(r"[.!?…][" + re.escape(_CLOSERS) + r"]*(?=\s|$)")


def ends_with_terminal(text: str) -> bool:
    """Metin . ! ? … ile (ardından en fazla kapanış tırnağı/parantez) bitiyor mu?"""
    t = (text or "").rstrip().rstrip(_CLOSERS)
    return bool(t) and t[-1] in ".!?…"


def word_count(text: str) -> int:
    return len((text or "").split())


def clip_to_sentence(text: str, max_words: int, label: str = "") -> str:
    """max_words'ü aşan metni sınır içindeki SON TAM CÜMLENİN sonunda keser.

    Sınır içinde cümle sonu yoksa metin DEĞİŞMEZ (yarım cümle üretilmez) ve loglanır."""
    text = (text or "").strip()
    words = text.split()
    if len(words) <= max_words:
        return text
    prefix = " ".join(words[:max_words])
    ends = list(_SENTENCE_END.finditer(prefix))
    if not ends:
        logger.warning("[metin] %s %d kelime > %d emniyet tavanı ama sınır içinde cümle "
                       "sonu yok — KESİLMEDİ (yarım cümle üretilmez).",
                       label or "alan", len(words), max_words)
        return text
    clipped = prefix[: ends[-1].end()].strip()
    logger.warning("[metin] %s %d kelime > %d emniyet tavanı → son tam cümlede kesildi "
                   "(%d kelime).", label or "alan", len(words), max_words, word_count(clipped))
    return clipped


# ------------------------------ denetim (eval/test) ------------------------------ #
def unterminated_fields(data: dict) -> list[tuple[str, str]]:
    """Noktalama (. ! ? …) ile bitmeyen metin alanları/maddeleri: [(alan, metin)]."""
    bad: list[tuple[str, str]] = []
    for f in ("headline_verdict", "ai_take", "summary", "invalidation"):
        v = str(data.get(f) or "").strip()
        if v and not ends_with_terminal(v):
            bad.append((f, v))
    for f in ("top_drivers", "what_to_verify"):
        for item in data.get(f) or []:
            v = str(item).strip()
            if v and not ends_with_terminal(v):
                bad.append((f, v))
    return bad


def banned_phrase_hits(text: str, language: str) -> list[str]:
    """Metinde BULUNAN yasaklı ifadeler (eşleşen metin, küçük harf, tekrarsız, sırayla)."""
    hits: list[str] = []
    for rx in BANNED_PATTERNS["en" if language == "en" else "tr"]:
        for m in rx.finditer(text or ""):
            found = " ".join(m.group(0).lower().split())
            if found not in hits:
                hits.append(found)
    return hits


_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "but",
    "with", "its", "it", "as", "at", "by", "from", "that", "this", "be", "was",
    "ve", "ile", "bir", "bu", "da", "de", "ama", "için", "gibi", "olarak", "çok", "en",
}
_TOKEN = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)


def _ngrams(text: str, n: int) -> set[str]:
    toks = [t.lower() for t in _TOKEN.findall(text or "")]
    out = set()
    for i in range(len(toks) - n + 1):
        gram = toks[i : i + n]
        if sum(1 for t in gram if t not in _STOP and not t.isdigit()) >= 2:
            out.add(" ".join(gram))
    return out


def repeated_ngrams(texts: dict[str, str], n: int = 3, min_docs: int = 2) -> dict[str, list[str]]:
    """Birden çok entity'nin metninde geçen n-kelimelik öbekler: {öbek: [entity, ...]}.
    En az iki anlamlı (stopword/rakam olmayan) kelime içeren öbekler sayılır."""
    where: dict[str, list[str]] = defaultdict(list)
    for name, text in texts.items():
        for g in _ngrams(text, n):
            where[g].append(name)
    return {g: names for g, names in sorted(where.items()) if len(names) >= min_docs}
