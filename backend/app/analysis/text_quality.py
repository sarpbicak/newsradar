"""Kullanıcıya gösterilen metinlerin kalite kuralları — TEK yerde.

Ana kural: kullanıcının gördüğü hiçbir alan cümle ortasında bitmez.
- Uzunluğu PROMPT yönetir (hedef sınırlar: PROMPT_LIMITS).
- Koddaki tavanlar (HARD_CAPS) yalnızca EMNİYET: aşılırsa metin, sınır içindeki SON TAM
  CÜMLENİN sonunda kesilir. Sınır içinde hiç cümle sonu yoksa kesilmez — metin olduğu gibi
  bırakılır ve loglanır. Yarım cümle, tam ama uzun cümleden her zaman daha kötüdür.
- Şablon kalıpları: BANNED_PATTERNS (regex denetim; okunur hali BANNED_PHRASES prompt'a
  yasak olarak yazılır, eval'de denetlenir) ve
  entity'ler arasında tekrar eden 3+ kelimelik öbekler (repeated_ngrams).
- Dil sızıntısı (language_leak_hits): TR metinde İngilizce işlev kelimesi, EN metinde Türkçe
  kelime/harf → değerlendirme bir kez notla yeniden istenir.
- Şablon çöküşü (headline_openings): aynı taramada >3 entity'nin hükmü aynı ilk 3 kelimeyle
  başlıyorsa uyarı loglanır.
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
        "haberler karışık", "haber akışı karışık", "karışık haber(ler)", "haber akışı dengeli",
    ],
    "en": [
        "largely/mostly/predominantly/broadly/generally positive/negative/bullish/bearish/"
        "upbeat/downbeat/optimistic/pessimistic",
        "news flow leans positive/negative", "news flow is mixed", "news is mixed",
        "mixed news", "… is mixed: / … is mixed,", "news is balanced / news balanced",
    ],
}
_GAP = r"(?:\s+[^\W\d_]+)?\s+"  # en fazla bir ara kelime
BANNED_PATTERNS = {
    "tr": [
        re.compile(r"\b(?:ağırlık\w*|çoğunlukla|büyük\s+ölçüde|genel\s+olarak)" + _GAP
                   + r"(?:olumlu|olumsuz|iyimser|kötümser)\w*", re.IGNORECASE),
        re.compile(r"\bhaberler" + _GAP + r"karışık\w*", re.IGNORECASE),
        re.compile(r"\bhaber\s+akışı" + _GAP + r"karışık\w*", re.IGNORECASE),
        # Şablon çöküşü: "Karışık haberler: …", "Haber akışı dengeli …" (IGNORECASE Türkçe
        # I/ı/İ/i eşdeğerliğini de kapsar: "KARIŞIK HABER").
        re.compile(r"\bkarışık\s+haber\w*", re.IGNORECASE),
        re.compile(r"\bhaber\s+akışı" + _GAP + r"dengeli\w*", re.IGNORECASE),
    ],
    "en": [
        re.compile(r"\b(?:largely|mostly|predominantly|broadly|generally)" + _GAP
                   + r"(?:positive|negative|bullish|bearish|upbeat|downbeat|optimistic|pessimistic)\b",
                   re.IGNORECASE),
        re.compile(r"\bnews\s+flow\s+leans" + _GAP + r"(?:positive|negative)\b", re.IGNORECASE),
        re.compile(r"\bnews\s+flow\s+is" + _GAP + r"mixed\b", re.IGNORECASE),
        # Şablon çöküşü: "X news is mixed", "Mixed news: …", "The picture is mixed: …",
        # "news is balanced" / "news balanced".
        re.compile(r"\bnews\s+is\s+mixed\b", re.IGNORECASE),
        re.compile(r"\bmixed\s+news\b", re.IGNORECASE),
        re.compile(r"\bis\s+mixed[:,]", re.IGNORECASE),
        re.compile(r"\bnews\s+(?:is\s+)?balanced\b", re.IGNORECASE),
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
    lang = "en" if language == "en" else "tr"
    for rx in BANNED_PATTERNS[lang]:
        for m in rx.finditer(text or ""):
            raw = m.group(0)
            found = " ".join((tr_lower(raw) if lang == "tr" else raw.lower()).split())
            if found not in hits:
                hits.append(found)
    return hits


def tr_lower(text: str) -> str:
    """Türkçe-farkında küçük harf: I → ı, İ → i (str.lower() 'İ'yi 'i̇' yapar, 'I'yı 'i')."""
    return (text or "").replace("I", "ı").replace("İ", "i").lower()


# ------------------------------ dil sızıntısı ------------------------------ #
# TR çıktıda İngilizce kelime ("piyasanın already tepki vermesi") ya da EN çıktıda Türkçe
# kelime/karakter → değerlendirme BİR KEZ notla yeniden istenir (pipeline._quality_notes).
# Özel adlar (şirket/ürün/kişi) serbest olduğu için kural dar tutulur:
#  - TR: yalnızca aşağıdaki yaygın İngilizce işlev kelimeleri, TAM kelime olarak. Büyük
#    harfli "The" (The Verge, The Information gibi yayın/ürün adları) sayılmaz.
#  - EN: Türkçe'ye özgü harf (ğ ş ı, ayrıca ü ö ç) içeren KÜÇÜK harfle başlayan kelime
#    (büyük harfle başlayan "Türk Telekom", "Koç" özel addır) ya da yaygın Türkçe kelime.
LEAK_WORDS = {
    "tr": ("already", "however", "although", "because", "while", "still", "which", "also", "the"),
    "en": ("ve", "ile", "için", "ama", "ancak", "değil", "gibi", "çok", "daha", "olarak",
           "bir", "bu", "şirketin", "haberler"),
}
_B = r"(?<![\w'’-])"   # kelime başı (kesme/tire ile birleşik parçalar sayılmaz)
_E = r"(?![\w'’-])"    # kelime sonu
_EN_IN_TR = re.compile(
    _B + r"(?:(?i:already|however|although|because|while|still|which|also)|the)" + _E
)
_TR_WORD_IN_EN = re.compile(_B + r"(?:" + "|".join(LEAK_WORDS["en"]) + r")" + _E)
_TR_CHAR_WORD = re.compile(_B + r"[a-zğüşıöç][\w]*" + _E)
_TR_CHARS = set("ğüşıöçİĞÜŞÖÇ")


def language_leak_hits(text: str, language: str) -> list[str]:
    """Hedef dile ait OLMAYAN kelimeler (küçük harf, tekrarsız, sırayla). Boş = temiz."""
    text = text or ""
    if (language or "tr").lower() == "en":
        found = [m.group(0) for m in _TR_WORD_IN_EN.finditer(text)]
        found += [m.group(0) for m in _TR_CHAR_WORD.finditer(text)
                  if _TR_CHARS & set(m.group(0))]
    else:
        found = [m.group(0) for m in _EN_IN_TR.finditer(text)]
    out: list[str] = []
    for f in found:
        f = f.lower()
        if f not in out:
            out.append(f)
    return out


# ------------------------------ şablon çöküşü ------------------------------ #
def headline_openings(headlines: dict[str, tuple[str, list[str]]], n_words: int = 3,
                      max_same: int = 3) -> dict[str, list[str]]:
    """Aynı taramada hükmü AYNI ilk n kelimeyle başlayan entity grupları (> max_same).

    headlines: {entity_adı: (hüküm, [entity'nin adları — ad/kısa ad/query])}.
    Entity'nin kendi adı "<x>" ile değiştirilir; böylece "Tesla news is mixed" ile
    "NVIDIA news is mixed" aynı açılış ("<x> news is") sayılır. Dönen: {açılış: [adlar]}."""
    groups: dict[str, list[str]] = defaultdict(list)
    for name, (headline, aliases) in headlines.items():
        alias_toks = {tr_lower(t) for a in aliases for t in _TOKEN.findall(a or "")}
        toks: list[str] = []
        for t in _TOKEN.findall(headline or ""):
            low = tr_lower(t)
            base = re.split(r"['’]", low)[0]  # Tesla's / Tesla'nın → tesla
            tok = "<x>" if base in alias_toks else low
            if tok == "<x>" and toks and toks[-1] == "<x>":
                continue  # çok kelimeli ad ("Space Exploration Technologies") tek sayılır
            toks.append(tok)
        if len(toks) >= n_words:
            groups[" ".join(toks[:n_words])].append(name)
    return {k: v for k, v in groups.items() if len(v) > max_same}


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
