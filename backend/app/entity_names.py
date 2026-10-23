"""Entity görünen adı (display_name) — uzun resmi adlar için kısa ad, TEK yerde.

Sembol aramasından gelen resmi adlar ("Advanced Micro Devices", "Meta Platforms") kartta
uzun ve yabancı duruyor; kullanıcı şirketi kısa adıyla tanır (AMD, Meta). Frontend
`display_name or name` gösterir.

Kural bilerek KÜÇÜK ve AÇIK: yalnızca aşağıdaki eşleme tablosu. Ad normalize edilir
(küçük harf, noktalama, parantez içi ve şirket ekleri — Inc/Corp/Corporation/Ltd… — atılır)
ve tabloda aranır. Bilinmeyen ad → None (ad olduğu gibi gösterilir). Kısa ad zaten adın
kendisiyse de None (gereksiz tekrar yazılmaz).
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger("newsradar")

# normalize edilmiş ad → kısa görünen ad. Yeni şirket eklerken anahtarı _norm() çıktısıyla yaz.
KNOWN_DISPLAY_NAMES: dict[str, str] = {
    "advanced micro devices": "AMD",
    "meta platforms": "Meta",
    "space exploration technologies": "SpaceX",
    "alphabet": "Google",
    "nvidia": "NVIDIA",
    "amazon com": "Amazon",
    "tesla": "Tesla",
    "microsoft": "Microsoft",
    "apple": "Apple",
    "international business machines": "IBM",
    "taiwan semiconductor manufacturing": "TSMC",
    "palantir technologies": "Palantir",
    "aselsan elektronik sanayi ve ticaret": "Aselsan",
}

# Adın SONUNDAN atılan şirket ekleri (tekrarlı: "Holdings Inc" → ikisi de gider).
_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited",
    "plc", "llc", "ag", "sa", "nv", "se", "holdings", "holding", "aş", "as",
}
_PARENS = re.compile(r"\([^)]*\)")
_SHARE_CLASS = re.compile(r"\b(?:class|cl)\s+[a-c]\b")
_TR_AS = re.compile(r"\ba\.\s*[şs]\.?")  # Türk şirket eki "A.Ş." → tek kelime "aş"
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def _norm(text: str) -> str:
    """Karşılaştırma anahtarı: Türkçe-güvenli küçük harf, parantez/noktalama/ek temizliği."""
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace("İ", "i").lower()  # 'İ'.lower() → 'i̇' (birleşik nokta) olmasın
    t = _PARENS.sub(" ", t)
    t = t.replace("&", " and ")
    t = _SHARE_CLASS.sub(" ", t)
    t = _TR_AS.sub(" aş ", t)
    words = [w for w in _NON_WORD.sub(" ", t).replace("_", " ").split() if w]
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)


def display_name_for(name: str) -> str | None:
    """Bilinen uzun ad için kısa görünen ad; bilinmiyorsa ya da adla aynıysa None."""
    short = KNOWN_DISPLAY_NAMES.get(_norm(name))
    if not short or short == (name or "").strip():
        return None
    return short


def backfill_display_names(conn) -> int:
    """display_name'i BOŞ olan entity'leri eşleme tablosundan doldurur (idempotent).

    Dolu (elle verilmiş ya da önceden doldurulmuş) değerlere dokunmaz. conn: SQLAlchemy
    Connection (init_db içinden engine.begin()). Kaç satır güncellendiğini döner."""
    rows = conn.exec_driver_sql(
        "SELECT id, name FROM entities WHERE display_name IS NULL"
    ).fetchall()
    n = 0
    for eid, name in rows:
        short = display_name_for(name)
        if short:
            conn.exec_driver_sql(
                "UPDATE entities SET display_name = ? WHERE id = ? AND display_name IS NULL",
                (short, eid),
            )
            n += 1
    if n:
        logger.info("display_name backfill: %d entity kısa adla dolduruldu.", n)
    return n


# ------------------------------ mükerrer şirket ------------------------------ #
# Aynı şirket iki kayıtla izlenebiliyor: ticker "Space Exploration Technologies" (SPCX) ve
# keyword "SpaceX". Kural basit ve açık: her entity için şirket ANAHTARLARI üretilir —
# normalize ad, kısa ad (display_name ya da yukarıdaki eşleme tablosu = bilinen takma adlar)
# ve keyword'ün sorgusu — ve iki entity'nin anahtarları kesişiyorsa AYNI şirkettir. Ticker
# sembolü anahtar DEĞİL ("F", "ON" gibi kısa semboller keyword adlarıyla yanlış eşleşmesin).
def _compact(text: str) -> str:
    """Boşluksuz anahtar: "Space X" ile "SpaceX" aynı sayılsın."""
    return _norm(text).replace(" ", "")


def company_keys(name: str, entity_type: str | None = None, query: str | None = None,
                 display_name: str | None = None) -> set[str]:
    """Bir entity'nin şirket anahtarları (boş değerler atlanır)."""
    cands = [name, display_name, display_name_for(name)]
    if entity_type == "keyword" and query:
        cands += [query, display_name_for(query)]
    return {k for k in (_compact(c) for c in cands if c) if k}


def entity_keys(e) -> set[str]:
    """ORM Entity (ya da aynı alanlara sahip nesne) için company_keys."""
    return company_keys(e.name, e.type, e.query, getattr(e, "display_name", None))


def duplicate_groups(rows: list[dict]) -> list[list[dict]]:
    """Aynı şirketi temsil eden entity grupları (2+ üyeli). rows: {'name','type','query',
    'display_name', ...}. Anahtar kesişimi geçişlidir (union-find)."""
    parent = list(range(len(rows)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[str, int] = {}
    for i, r in enumerate(rows):
        for k in company_keys(r.get("name") or "", r.get("type"), r.get("query"),
                              r.get("display_name")):
            if k in owner:
                parent[find(i)] = find(owner[k])
            else:
                owner[k] = i
    groups: dict[int, list[dict]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(find(i), []).append(r)
    return [g for g in groups.values() if len(g) > 1]
