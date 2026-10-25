"""Çerezsiz ziyaretçi sayacı — kendi sunucumuzda, üçüncü parti yok.

Benzersiz ziyaretçi tahmini: sha256(günlük gizli tuz | IP | User-Agent). Tuz her UTC gününde
yenilenir ve eskisi silinir; ham IP ve UA hiçbir yere yazılmaz. Böylece kişi yalnızca AYNI GÜN
içinde tekilleşir, günler arası izlenemez (çerez banner'ı gerekmez). Ülke tutulmaz; kaynak
yalnızca yönlendiren alan adı (linkedin.com). Botlar (UA listesi, Lighthouse, Playwright,
headless) ve admin ziyaretleri sayılmaz.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db.models import PageView, VisitSalt

PAGES = ("landing", "app", "detail")
RETENTION_DAYS = 90
MAX_VIEWS_PER_VISITOR_DAY = 300   # kötüye kullanım: tek kişinin günlük kayıt tavanı

_BOT_RE = re.compile(
    r"bot|crawl|spider|slurp|preview|monitor|uptime|lighthouse|headless|playwright|puppeteer|"
    r"selenium|phantom|python-requests|httpx|aiohttp|curl|wget|go-http|java/|okhttp|axios|node-fetch|"
    r"facebookexternalhit|embedly|quora link|whatsapp|telegram|discord|skype|slack",
    re.IGNORECASE,
)


def is_bot(user_agent: str | None) -> bool:
    ua = (user_agent or "").strip()
    return not ua or bool(_BOT_RE.search(ua))


def _today(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).date().isoformat()


def salt_for(db: Session, day: str) -> str:
    """Günün tuzu; yoksa üretilir ve BAŞKA günlerin tuzları silinir (+ eski kayıt temizliği)."""
    row = db.get(VisitSalt, day)
    if row is not None:
        return row.salt
    db.execute(delete(VisitSalt).where(VisitSalt.day != day))
    cutoff = (date.fromisoformat(day) - timedelta(days=RETENTION_DAYS)).isoformat()
    db.execute(delete(PageView).where(PageView.day < cutoff))
    row = VisitSalt(day=day, salt=secrets.token_hex(32))
    db.add(row)
    db.flush()
    return row.salt


def visitor_hash(salt: str, ip: str, user_agent: str) -> str:
    return hashlib.sha256(f"{salt}|{ip}|{user_agent}".encode()).hexdigest()[:32]


def _own_hosts() -> set[str]:
    s = get_settings()
    hosts = {urlparse(o).hostname for o in [*s.cors_origins, s.public_url] if o and o != "*"}
    return {h.removeprefix("www.") for h in hosts if h}


def referrer_domain(referrer: str | None) -> str | None:
    """Yönlendiren alan adı (www. atılır); kendi sitemiz, boş ya da http(s) dışı → None."""
    try:
        u = urlparse((referrer or "").strip())
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or not u.hostname:
        return None
    host = u.hostname.lower().removeprefix("www.")
    return None if host in _own_hosts() else host[:100]


def record_view(db: Session, page: str, referrer: str | None, ip: str, user_agent: str,
                is_admin: bool = False, now: datetime | None = None) -> bool:
    """Görüntülemeyi kaydeder; sayılmadıysa (bot, admin, geçersiz sayfa, tavan) False."""
    if page not in PAGES or is_admin or is_bot(user_agent):
        return False
    day = _today(now)
    h = visitor_hash(salt_for(db, day), ip, user_agent)
    n = db.scalar(select(func.count()).select_from(PageView)
                  .where(PageView.day == day, PageView.visitor_hash == h)) or 0
    if n >= MAX_VIEWS_PER_VISITOR_DAY:
        return False
    db.add(PageView(day=day, page=page, visitor_hash=h, referrer=referrer_domain(referrer)))
    return True


def stats(db: Session, days: int = 30, now: datetime | None = None) -> dict:
    """Son `days` gün: günlük benzersiz ziyaretçi + görüntüleme, en çok gelen 5 kaynak,
    landing'den uygulamaya geçme oranı (aynı gün landing'i gören ziyaretçilerden uygulamayı da
    açanların payı — tuz günlük olduğu için oran gün içinde ölçülür)."""
    end = (now or datetime.now(timezone.utc)).date()
    start = end - timedelta(days=days - 1)
    rows = db.execute(select(PageView.day, PageView.page, PageView.visitor_hash, PageView.referrer)
                      .where(PageView.day >= start.isoformat())).all()
    visitors: dict[str, set] = defaultdict(set)
    views: Counter = Counter()
    landing: dict[str, set] = defaultdict(set)
    app: dict[str, set] = defaultdict(set)
    ref_visitors: dict[str, set] = defaultdict(set)
    for day, page, h, ref in rows:
        visitors[day].add(h)
        views[day] += 1
        (landing if page == "landing" else app)[day].add(h)
        if ref:
            ref_visitors[ref].add((day, h))
    series = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        series.append({"day": d, "visitors": len(visitors[d]), "views": views[d]})
    lv = sum(len(s) for s in landing.values())
    conv = sum(len(landing[d] & app[d]) for d in landing)
    top = sorted(ref_visitors.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:5]
    return {
        "days": series,
        "total_visitors": sum(x["visitors"] for x in series),
        "total_views": sum(x["views"] for x in series),
        "top_referrers": [{"domain": k, "visitors": len(v)} for k, v in top],
        "landing_visitors": lv,
        "landing_to_app": conv,
        "conversion_rate": round(conv / lv, 3) if lv else None,
    }
