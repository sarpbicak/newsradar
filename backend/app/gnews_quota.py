"""GNews kota koruması (ücretsiz plan: günde 100 istek, sıfırlanma 00:00 UTC).

- Günlük sayaç: gerçek her GNews isteği api_calls'a yazılır (provider="gnews"); o UTC gününün
  istekleri sayılır. NEWSRADAR_GNEWS_DAILY_LIMIT (varsayılan 80, payı bırakılmış güvenli sınır)
  dolunca GNews'e istek atılmaz (GDELT yedeği), ertesi gün UTC 00:00'da sayaç sıfırlanır.
  Zamanlayıcı ve kullanıcı yenilemeleri aynı DB sayacını paylaşır.
- Şirket başına aralık: son NEWSRADAR_GNEWS_ENTITY_INTERVAL_HOURS (varsayılan 2) içinde o şirket
  için başarılı bir GNews isteği varsa yeni istek atılmaz; DB'deki (önceki çekmenin) haberleri
  kullanılır. Başarısız istek aralığı başlatmaz.
- GNews'in kendi günlük kota hatası (HTTP 403): o gün sonuna kadar GNews kullanılmaz.
- Son hata (durum + zaman) admin panelinde: provider_skips "gnews:*" satırı.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .config import get_settings
from .db.database import session_scope
from .db.models import ApiCall, ProviderSkip

PROVIDER = "gnews"
STATE_KEY = "gnews:*"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day_start(now: datetime) -> datetime:
    return datetime.combine(now.date(), time.min, tzinfo=timezone.utc)


def next_reset(now: datetime | None = None) -> datetime:
    return _day_start(now or _now()) + timedelta(days=1)


def used_today(session: Session) -> int:
    return int(session.scalar(
        select(func.count()).select_from(ApiCall)
        .where(ApiCall.provider == PROVIDER, ApiCall.called_at >= _day_start(_now()))
    ) or 0)


def _blocked(session: Session) -> bool:
    row = session.get(ProviderSkip, STATE_KEY)
    return row is not None and row.until > _now()


def exhausted(session: Session) -> bool:
    """Bugün GNews'e istek atılmaz mı (güvenli sınır doldu ya da GNews 403 günlük kota)?"""
    return used_today(session) >= get_settings().gnews_daily_limit or _blocked(session)


def recent(session: Session, entity_id: int) -> bool:
    """Bu şirket için aralık içinde başarılı bir GNews isteği var mı (DB'deki haberler yeter)?"""
    since = _now() - timedelta(hours=max(0.0, get_settings().gnews_entity_interval_hours))
    return session.scalar(
        select(ApiCall.id).where(ApiCall.provider == PROVIDER, ApiCall.entity_id == entity_id,
                                 ApiCall.called_at >= since).limit(1)
    ) is not None


def record(session: Session, entity_id: int) -> ApiCall:
    """İstekten ÖNCE kaydet (kotadan düşer); başarısızsa failed() aralığı geri alır."""
    row = ApiCall(provider=PROVIDER, called_at=_now(), entity_id=entity_id)
    session.add(row)
    session.flush()
    return row


def failed(session: Session, call: ApiCall, warning: dict) -> None:
    """Başarısız istek: kotada kalır, aralık başlatmaz; son hata yazılır. 403 → gün sonuna kadar dur."""
    session.execute(update(ApiCall).where(ApiCall.id == call.id).values(entity_id=None))
    status = (warning or {}).get("params", {}).get("status")
    row = session.get(ProviderSkip, STATE_KEY)
    if row is None:
        row = ProviderSkip(key=STATE_KEY)
        session.add(row)
    now = _now()
    row.code = (warning or {}).get("code", "gnews_error")
    row.status = status
    row.updated_at = now
    row.until = next_reset(now) if status == 403 else now


def snapshot() -> dict:
    """Admin paneli: anahtar var mı, bugün kullanılan/kalan, sıfırlanma, son hata."""
    s = get_settings()
    with session_scope() as session:
        used = used_today(session)
        row = session.get(ProviderSkip, STATE_KEY)
        return {
            "configured": bool(s.gnews_api_key),
            "used_today": used,
            "limit": s.gnews_daily_limit,
            "remaining": max(0, s.gnews_daily_limit - used),
            "resets_at": next_reset(),
            "blocked": row is not None and row.until > _now(),
            "last_error_status": row.status if row is not None else None,
            "last_error_at": row.updated_at if row is not None else None,
        }
