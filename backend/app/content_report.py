"""İçerik raporu (SALT OKUNUR): dil bazında analiz durumu + mükerrer entity grupları.

  python -m app.cli content-report                  # NEWSRADAR_DB (container: /data/newsradar.db)
  python -m app.cli content-report --db kopya.db    # başka bir dosya
  python -m app.cli content-report --stale-hours 48

DB `mode=ro` URI ile açılır — hiçbir yazma/migration yapılmaz (init_db ÇAĞRILMAZ), canlı
DB'de güvenle çalışır. display_name kolonu henüz yoksa (deploy öncesi) eşleme tablosundan
hesaplanır.

(a) Her entity için tr/en dillerinde EN SON analiz zamanı; yoksa EKSİK, eşikten eskiyse
    ESKİ. En son metinde dil sızıntısı (TR'de İngilizce kelime / EN'de Türkçe) işaretlenir.
(b) Aynı şirketi temsil eden entity grupları (entity_names.duplicate_groups).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .analysis.text_quality import language_leak_hits
from .entity_names import display_name_for, duplicate_groups

LANGS = ("tr", "en")


def _parse_ts(v) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _age(dt: datetime, now: datetime) -> str:
    h = (now - dt).total_seconds() / 3600
    return f"{h:.0f} sa önce" if h < 48 else f"{h / 24:.0f} gün önce"


def open_readonly(path: str) -> sqlite3.Connection:
    """Salt okunur bağlantı (yazma denemesi 'attempt to write a readonly database' atar)."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def collect(con: sqlite3.Connection, stale_hours: float = 24.0,
            now: datetime | None = None) -> dict:
    """Rapor verisi (yazdırmadan bağımsız — test edilebilir)."""
    now = now or datetime.now(timezone.utc)
    cols = {r[1] for r in con.execute("PRAGMA table_info(entities)")}
    dn_sql = "display_name" if "display_name" in cols else "NULL AS display_name"
    entities = [dict(r) for r in con.execute(
        f"SELECT id, name, {dn_sql}, type, query, active FROM entities ORDER BY id")]
    followers = {r[0]: r[1] for r in con.execute(
        "SELECT entity_id, COUNT(*) FROM user_watchlist GROUP BY entity_id")}
    rows = []
    for e in entities:
        e["display_name"] = e["display_name"] or display_name_for(e["name"])
        e["followers"] = followers.get(e["id"], 0)
        langs = {}
        for lang in LANGS:
            r = con.execute(
                "SELECT created_at, headline_verdict, summary, ai_take, COUNT(*) OVER () AS n "
                "FROM entity_analyses WHERE entity_id = ? AND language = ? "
                "ORDER BY created_at DESC LIMIT 1", (e["id"], lang)).fetchone()
            if r is None:
                langs[lang] = {"status": "EKSİK", "at": None, "count": 0, "leaks": []}
                continue
            at = _parse_ts(r["created_at"])
            stale = at is None or (now - at).total_seconds() > stale_hours * 3600
            text = " ".join(str(r[k] or "") for k in ("headline_verdict", "summary", "ai_take"))
            langs[lang] = {"status": "ESKİ" if stale else "GÜNCEL", "at": at,
                           "count": r["n"], "leaks": language_leak_hits(text, lang)}
        e["langs"] = langs
        rows.append(e)
    return {"now": now, "stale_hours": stale_hours, "entities": rows,
            "duplicates": duplicate_groups(rows)}


def render(data: dict) -> str:
    now = data["now"]
    out = [f"NewsRadar içerik raporu — {now:%Y-%m-%d %H:%M} UTC "
           f"(ESKİ = son analiz {data['stale_hours']:g} saatten eski)", ""]
    out.append("== (a) Dil bazında analiz durumu ==")
    counts = {lang: {"GÜNCEL": 0, "ESKİ": 0, "EKSİK": 0} for lang in LANGS}
    for e in data["entities"]:
        label = e["name"] + (f" → {e['display_name']}" if e["display_name"] else "")
        state = "aktif" if e["active"] else "pasif"
        out.append(f"#{e['id']} {label} [{e['type']}:{e['query']}] {state}, "
                   f"{e['followers']} takipçi")
        for lang in LANGS:
            info = e["langs"][lang]
            counts[lang][info["status"]] += 1
            if info["at"] is None:
                line = f"    {lang}: EKSİK (hiç analiz yok)"
            else:
                line = (f"    {lang}: {info['status']:6} son={info['at']:%Y-%m-%d %H:%M} "
                        f"({_age(info['at'], now)}), {info['count']} kayıt")
            if info["leaks"]:
                line += f"  ⚠ dil sızıntısı: {', '.join(info['leaks'])}"
            out.append(line)
    out.append("")
    for lang in LANGS:
        c = counts[lang]
        out.append(f"Özet {lang}: güncel={c['GÜNCEL']} eski={c['ESKİ']} eksik={c['EKSİK']}")
    only = [e for e in data["entities"]
            if (e["langs"]["tr"]["at"] is None) != (e["langs"]["en"]["at"] is None)]
    if only:
        out.append("Tek dilde analizi olanlar (eski API diğer dile düşüyordu): " + ", ".join(
            f"#{e['id']} {e['display_name'] or e['name']} "
            f"(yalnızca {'tr' if e['langs']['tr']['at'] else 'en'})" for e in only))
    out.append("")
    out.append("== (b) Mükerrer entity grupları (aynı şirket) ==")
    if not data["duplicates"]:
        out.append("Mükerrer grup yok.")
    for i, g in enumerate(data["duplicates"], 1):
        members = "; ".join(
            f"#{e['id']} {e['name']} [{e['type']}:{e['query']}] {e['followers']} takipçi"
            for e in g)
        out.append(f"{i}. {members}")
    return "\n".join(out)
