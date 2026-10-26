"""DB modellerini API yanıt modellerine çeviren yardımcılar."""

from __future__ import annotations

import math
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..analyst import display_target
from ..config import get_settings
from ..markets import market_of
from ..analysis.schemas import apply_texts
from ..db.models import ALL_LANGUAGES, AnalystSnapshot, Article, Entity, EntityAnalysis, PriceSnapshot
from ..languages import UI_LANGUAGES
from .schemas import (
    AnalysisOut,
    AnalystOut,
    AnalystPeriodOut,
    ArticleOut,
    DeltaOut,
    EntityCardOut,
    HorizonDriverOut,
    HorizonOut,
    PreviousAnalysisOut,
    PricePointOut,
    RiskPointOut,
)


ANALYSIS_LANGUAGES = UI_LANGUAGES


def content_language(user, lang: str | None = None) -> str:
    """AI içeriğinin dili: istekte geçerli `?lang=tr|en|de` varsa o (arayüzün o anki dili —
    POST /users/me/language ile yarışmaz), yoksa kullanıcının kayıtlı dili."""
    v = (lang or "").strip().lower()
    if v in ANALYSIS_LANGUAGES:
        return v
    return (getattr(user, "language", None) or "tr")


def _for_language(q, language: str | None):
    """Bu dilde okunabilen kayıtlar: tek kaynak ("all") + eski dil başına kayıtlar."""
    if language:
        q = q.where(EntityAnalysis.language.in_((language, ALL_LANGUAGES)))
    return q


def _latest_analysis(session: Session, entity_id: int, language: str | None = None) -> EntityAnalysis | None:
    """Kullanıcı dilindeki EN SON değerlendirme. O dilde yoksa None — başka dile DÜŞMEZ.

    Yeni kayıtlar tek kaynak ("all"): TR ve EN aynı hükmü okur, metin `texts[dil]`'den gelir.
    En son tek kaynak kaydın bu dilde metni yoksa (çeviri başarısız) None: kart analizsiz döner
    + `analysis_missing_language=True` — eski dil kaydına düşüp FARKLI bir hüküm göstermez.
    Eksik çeviri bir sonraki yenilemede tamamlanır (pipeline._backfill_translations).
    language=None → dilden bağımsız en son kayıt (yalnızca dil-nötr iç kullanım)."""
    q = _for_language(select(EntityAnalysis).where(EntityAnalysis.entity_id == entity_id), language)
    row = session.scalar(q.order_by(EntityAnalysis.created_at.desc()))
    if row is not None and language and row.language == ALL_LANGUAGES and language not in (row.texts or {}):
        return None
    return row


def _has_other_language_analysis(session: Session, entity_id: int, language: str) -> bool:
    """Bu entity için BAŞKA bir dilde değerlendirme var mı (kullanıcının dilinde yokken)?"""
    return session.scalar(
        select(EntityAnalysis.id)
        .where(EntityAnalysis.entity_id == entity_id, EntityAnalysis.language != language)
        .limit(1)
    ) is not None


def _previous_analysis(session: Session, entity_id: int, language: str | None = None) -> EntityAnalysis | None:
    """Son değerlendirmeden bir öncekini döner — AYNI dilde (delta tr'yi en ile
    karşılaştırmasın). yoksa None → yeterli geçmiş yok."""
    q = _for_language(select(EntityAnalysis).where(EntityAnalysis.entity_id == entity_id), language)
    return session.scalar(q.order_by(EntityAnalysis.created_at.desc()).offset(1).limit(1))


def _previous_out(prev: EntityAnalysis | None) -> PreviousAnalysisOut | None:
    if prev is None:
        return None
    return PreviousAnalysisOut(
        risk_score=prev.risk_score,
        stance=prev.stance,
        sentiment_trend=prev.sentiment_trend,
        avg_sentiment=prev.avg_sentiment,
        created_at=prev.created_at,
    )


def _delta_out(
    latest: EntityAnalysis | None, prev: EntityAnalysis | None
) -> DeltaOut | None:
    """İki snapshot arasındaki değişim. Biri yoksa None (sessiz 'yeterli geçmiş yok')."""
    if latest is None or prev is None:
        return None
    sentiment_delta = None
    if latest.avg_sentiment is not None and prev.avg_sentiment is not None:
        sentiment_delta = round(latest.avg_sentiment - prev.avg_sentiment, 3)
    stance_changed = latest.stance != prev.stance
    return DeltaOut(
        risk_delta=latest.risk_score - prev.risk_score,
        stance_changed=stance_changed,
        previous_stance=prev.stance if stance_changed else None,
        sentiment_delta=sentiment_delta,
    )


def risk_history(session: Session, entity_id: int, limit: int = 30,
                 language: str | None = None) -> list[RiskPointOut]:
    """Son ~N değerlendirmenin risk skoru zaman serisi (eski → yeni). DİL FİLTRELİ:
    her taramada tr+en yazıldığı için filtrelenmezse noktalar İKİYE katlanırdı."""
    def _q(lang):
        q = _for_language(select(EntityAnalysis).where(EntityAnalysis.entity_id == entity_id), lang)
        return session.scalars(q.order_by(EntityAnalysis.created_at.desc()).limit(limit)).all()
    rows = _q(language)
    if not rows and language:  # o dilde kayıt yoksa herhangi bir dile düş
        rows = _q(None)
    return [
        RiskPointOut(created_at=r.created_at, risk_score=r.risk_score, stance=r.stance)
        for r in reversed(rows)  # kronolojik: eski → yeni
    ]


def price_history(session: Session, entity_id: int, limit: int = 30) -> list[PricePointOut]:
    """Son ~N fiyat snapshot'ı (eski → yeni). Ticker olmayan entity'de boş liste."""
    rows = session.scalars(
        select(PriceSnapshot)
        .where(PriceSnapshot.entity_id == entity_id)
        .order_by(PriceSnapshot.fetched_at.desc())
        .limit(limit)
    ).all()
    return [PricePointOut(fetched_at=r.fetched_at, price=r.price) for r in reversed(rows)]


def analyst_history(session: Session, entity_id: int, periods: int = 6) -> list[AnalystPeriodOut]:
    """Tavsiye dağılımının dönemlere göre geçmişi (eski → yeni): her dönemin (Finnhub period,
    aylık) EN SON snapshot'ı; tavsiyesi olmayan (toplam 0) snapshot'lar atlanır."""
    rows = session.scalars(
        select(AnalystSnapshot)
        .where(AnalystSnapshot.entity_id == entity_id, AnalystSnapshot.period.is_not(None))
        .order_by(AnalystSnapshot.fetched_at.desc())
    ).all()
    seen: dict[str, AnalystSnapshot] = {}
    for r in rows:
        total = r.strong_buy + r.buy + r.hold + r.sell + r.strong_sell
        if total and r.period not in seen:
            seen[r.period] = r
        if len(seen) >= periods:
            break
    return [
        AnalystPeriodOut(period=p, strong_buy=r.strong_buy, buy=r.buy, hold=r.hold, sell=r.sell,
                         strong_sell=r.strong_sell)
        for p, r in sorted(seen.items())
    ]


def _horizon_out(raw: dict | None) -> HorizonOut | None:
    if not isinstance(raw, dict) or not raw.get("verdict"):
        return None
    drivers = [HorizonDriverOut(text=str(d.get("text") or ""), direction=d.get("direction"))
               for d in (raw.get("drivers") or []) if isinstance(d, dict) and d.get("text")]
    return HorizonOut(verdict=raw["verdict"], drivers=drivers, summary=raw.get("summary") or "")


def localized_analysis(a: EntityAnalysis, language: str | None = None) -> dict:
    """Kaydın görünen alanları: dilden bağımsız alanlar kayıttan, metin (tek kaynak kayıtta)
    istenen dilin `texts` girdisinden. Eski dil başına kayıt olduğu gibi döner."""
    base = {
        "headline_verdict": a.headline_verdict, "ai_take": a.ai_take, "summary": a.summary,
        "invalidation": a.invalidation, "top_drivers": a.top_drivers or [],
        "what_to_verify": a.what_to_verify or [], "short_term": a.short_term, "long_term": a.long_term,
    }
    if a.language == ALL_LANGUAGES and language:
        return apply_texts(base, (a.texts or {}).get(language))
    return base


def analysis_out(a: EntityAnalysis | None, language: str | None = None) -> AnalysisOut | None:
    if a is None:
        return None
    t = localized_analysis(a, language)
    return AnalysisOut(
        headline_verdict=t["headline_verdict"],
        ai_take=t["ai_take"],
        risk_score=a.risk_score,
        sentiment_trend=a.sentiment_trend,
        top_drivers=t["top_drivers"],
        driver_directions=a.driver_directions,
        summary=t["summary"],
        stance=a.stance,
        conviction=a.conviction,
        what_to_verify=t["what_to_verify"],
        invalidation=t["invalidation"],
        short_term=_horizon_out(t["short_term"]),
        long_term=_horizon_out(t["long_term"]),
        articles_considered=a.articles_considered,
        created_at=a.created_at,
    )


def _analyst_out(snap: AnalystSnapshot | None, current_price: float | None = None) -> AnalystOut | None:
    if snap is None:
        return None
    total = snap.strong_buy + snap.buy + snap.hold + snap.sell + snap.strong_sell
    target, kind = display_target(snap)
    # Tavsiye ya da hedeften en az biri olmalı (yalnızca hedef varsa da göster).
    if total == 0 and target is None:
        return None
    # Upside % — GERÇEK hedef (medyan, yoksa konsensüs) ile güncel fiyat farkı (aritmetik).
    upside = None
    if target is not None and current_price:
        upside = round((target - current_price) / current_price * 100, 1)
    return AnalystOut(
        strong_buy=snap.strong_buy, buy=snap.buy, hold=snap.hold,
        sell=snap.sell, strong_sell=snap.strong_sell, total=total, period=snap.period,
        target=target, target_kind=kind,
        target_mean=snap.target_mean, target_high=snap.target_high, target_low=snap.target_low,
        target_median=snap.target_median, target_consensus=snap.target_consensus,
        current_price=current_price, upside_percent=upside,
        fetched_at=snap.fetched_at,
    )


def _horizon_and_evidence(
    session: Session, entity_id: int, analysis: EntityAnalysis | None
) -> tuple[str | None, str | None, int]:
    """Kart için çoğunluk vade + kanıt gücü (conviction + haber sayısı + tutarlılık)."""
    if analysis is None:
        return None, None, 0
    rows = session.execute(
        select(Article.impact_horizon, Article.sentiment).where(
            Article.entity_id == entity_id, Article.analyzed.is_(True)
        )
    ).all()
    horizons = [h for h, _ in rows if h]
    horizon = Counter(horizons).most_common(1)[0][0] if horizons else None

    # Karttaki "N haber": GERÇEK analiz edilmiş makale sayısı — sabit bir tavana
    # (ör. env'deki 40) kilitlenmez. Analiz-per-yenileme tavanı (max_articles_per_entity)
    # yalnızca tek yenilemede KAÇ YENİ makale işleneceğini sınırlar; birikmiş toplam
    # analiz edilmiş sayı kartta olduğu gibi gösterilir.
    count = len(rows)
    sentiments = [s for _, s in rows if s is not None]

    # Kanıt puanı: kanaat + haber sayısı + duygu tutarlılığı.
    score = {"high": 2, "medium": 1, "low": 0}.get(analysis.conviction, 0)
    if count >= 8:
        score += 1
    elif count < 3:
        score -= 1
    if sentiments:
        pos = sum(1 for s in sentiments if s > 0.1)
        neg = sum(1 for s in sentiments if s < -0.1)
        agree = max(pos, neg) / len(sentiments)
        if agree >= 0.7:
            score += 1
        elif agree < 0.4:
            score -= 1
    strength = "strong" if score >= 3 else "medium" if score >= 1 else "weak"
    return horizon, strength, count


def _priority(analysis, delta, change_percent, analyst) -> tuple[int, str | None]:
    """Kademeli düzen için öncelik skoru + baskın neden (Katman 1 seçimi).

    Tam tersine dönüş (bullish↔bearish) +3 · nötr↔yönlü gürültü +1 · |risk farkı|≥5 +2
    · |günlük %|≥2 +2 · haber↔analist ayrışması +1.

    NOT: eskiden HER stance_changed +3 alıyordu; ama LLM nötr↔yönlü arasında
    kararsızlık yaptığında (nötr-gürültü) bu sahte aciliyet üretiyordu (çoğu entity
    skor≥2 → seçim ayrımsız). Artık yalnızca GERÇEK tersine dönüş ağır puan alır.
    """
    # reason artık KANONİK ANAHTAR döner (dil-nötr); frontend kullanıcı diline çevirir
    # (eskiden sabit Türkçe string idi → İngilizce kartta "sert hareket" görünüyordu).
    reasons: list[tuple[str, int]] = []
    if delta is not None:
        if delta.stance_changed:
            prev = delta.previous_stance
            curr = analysis.stance if analysis is not None else None
            if prev in ("bullish", "bearish") and curr in ("bullish", "bearish") and prev != curr:
                reasons.append(("stance_reversed", 3))   # tam tersine dönüş — önemli
            else:
                reasons.append(("stance_clarified", 1))  # nötr↔yönlü — hafif sinyal
        if abs(delta.risk_delta) >= 5:
            reasons.append(("risk_jump", 2))
    if change_percent is not None and abs(change_percent) >= 2:
        reasons.append(("sharp_move", 2))
    if analysis is not None and analyst is not None:
        buyish = analyst.strong_buy + analyst.buy
        sellish = analyst.sell + analyst.strong_sell
        analyst_buy = buyish > sellish and buyish > analyst.hold
        analyst_sell = sellish > buyish and sellish > analyst.hold
        if (analysis.stance == "bearish" and analyst_buy) or (analysis.stance == "bullish" and analyst_sell):
            reasons.append(("divergence", 1))
    score = sum(w for _, w in reasons)
    reason = max(reasons, key=lambda r: r[1])[0] if reasons else None
    return score, reason


def _market_fields(entity: Entity, language: str) -> dict:
    if entity.type != "ticker":
        return {}
    m = market_of(entity.query)
    return {"market": m.code, "exchange": m.exchange, "country": m.country(language), "currency": m.currency,
            "us_market": m.is_us}


def _news_window_days(entity: Entity) -> int:
    """'Son N günde yeterli haber yok' notundaki N: geriye dönük doldurma yapıldıysa o süre."""
    s = get_settings()
    window = max(1, math.ceil(s.lookback_hours / 24))
    return max(window, s.backfill_days) if entity.backfilled_at else window


def entity_card(session: Session, entity: Entity, language: str = "tr") -> EntityCardOut:
    """Overview kartı için entity özetini toplar (kullanıcı diline göre değerlendirme)."""
    article_count = session.scalar(
        select(func.count()).select_from(Article).where(Article.entity_id == entity.id)
    ) or 0
    analyzed_count = session.scalar(
        select(func.count()).select_from(Article).where(
            Article.entity_id == entity.id, Article.analyzed.is_(True)
        )
    ) or 0
    avg_sentiment = session.scalar(
        select(func.avg(Article.sentiment)).where(
            Article.entity_id == entity.id, Article.analyzed.is_(True)
        )
    )

    # En sık risk bayrakları (analiz edilmiş makalelerden).
    flag_rows = session.scalars(
        select(Article.risk_flags).where(
            Article.entity_id == entity.id, Article.analyzed.is_(True)
        )
    ).all()
    counter: Counter[str] = Counter()
    for flags in flag_rows:
        for f in (flags or []):
            counter[f] += 1
    top_flags = [f for f, _ in counter.most_common(4)]

    latest = _latest_analysis(session, entity.id, language)
    # Kullanıcının dilinde analiz yok ama başka dilde var → başka dile DÜŞME; arayüz
    # "Bu dilde henüz analiz yok, bir sonraki yenilemede gelecek" der.
    missing_language = latest is None and _has_other_language_analysis(session, entity.id, language)
    no_reason = None
    if latest is None and not missing_language:
        pending = session.scalar(
            select(func.count()).select_from(Article).where(
                Article.entity_id == entity.id, Article.analyzed.is_(False),
                Article.prefiltered.is_(False), Article.expired.is_(False),
            )
        ) or 0
        no_reason = "pending" if pending else "few_news"
    previous = _previous_analysis(session, entity.id, language) if latest else None
    delta = _delta_out(latest, previous)
    horizon, evidence_strength, evidence_count = _horizon_and_evidence(session, entity.id, latest)

    # Fiyat + analist: yalnızca ticker entity'lerde (keyword'de None kalır).
    price_snap = None
    analyst = None
    if entity.type == "ticker":
        price_snap = session.scalar(
            select(PriceSnapshot)
            .where(PriceSnapshot.entity_id == entity.id)
            .order_by(PriceSnapshot.fetched_at.desc())
        )
        analyst = _analyst_out(
            session.scalar(
                select(AnalystSnapshot)
                .where(AnalystSnapshot.entity_id == entity.id)
                .order_by(AnalystSnapshot.fetched_at.desc())
            ),
            current_price=price_snap.price if price_snap else None,
        )

    change_percent = price_snap.change_percent if price_snap else None
    p_score, p_reason = _priority(latest, delta, change_percent, analyst)

    return EntityCardOut(
        id=entity.id,
        name=entity.name,
        display_name=entity.display_name,
        no_analysis_reason=no_reason,
        news_window_days=_news_window_days(entity),
        **_market_fields(entity, language),
        type=entity.type,
        query=entity.query,
        language=entity.language,
        active=entity.active,
        article_count=article_count,
        analyzed_count=analyzed_count,
        avg_sentiment=round(avg_sentiment, 3) if avg_sentiment is not None else None,
        top_flags=top_flags,
        last_updated=latest.created_at if latest else None,
        analysis=analysis_out(latest, language),
        # Tek kaynak kayıtta gösterilen metnin dili istenen dildir.
        analysis_language=(language if latest.language == ALL_LANGUAGES else latest.language) if latest else None,
        analysis_missing_language=missing_language,
        horizon=horizon,
        evidence_strength=evidence_strength,
        evidence_count=evidence_count,
        previous_analysis=_previous_out(previous),
        delta=delta,
        priority_score=p_score,
        priority_reason=p_reason,
        price=price_snap.price if price_snap else None,
        change_percent=change_percent,
        price_updated_at=price_snap.fetched_at if price_snap else None,
        analyst=analyst,
    )


def article_out(a: Article) -> ArticleOut:
    return ArticleOut(
        id=a.id,
        url=a.url,
        title=a.title,
        source=a.source,
        source_count=a.source_count,
        published_at=a.published_at,
        provider=a.provider,
        analyzed=a.analyzed,
        sentiment=a.sentiment,
        event_type=a.event_type,
        risk_flags=a.risk_flags,
        impact_horizon=a.impact_horizon,
        relevance=a.relevance,
        rationale=a.rationale,
    )
