"""Sohbet ucu: POST /chat — SSE streaming.

Gövde: {entity_id, messages: [{role, content}, ...]}
Sunucu, o entity'nin son ~15 analiz edilmiş makalesini bağlam olarak ekler ve
aynı sistem prompt'unu kullanır; böylece kullanıcı haberleri ve pozisyonu Claude
ile tartışabilir. Yanıt token-token SSE olarak akar.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..languages import user_language
from .errors import ApiError
from ..analysis.claude_client import ClaudeError, MissingAPIKeyError
from ..analysis.llm import get_llm_provider
from ..analysis.prompts import SYSTEM_PROMPT, output_language_directive, utc_context_line
from ..db.database import get_db
from ..db.models import Article, Entity, User
from ..watchlist import in_watchlist
from .routes_auth import get_current_user
from .schemas import ChatRequest
from .serializers import _latest_analysis, localized_analysis
from .usage import record_event

router = APIRouter(tags=["chat"])

CONTEXT_ARTICLES = 15


def _sse(event: str, data: dict) -> str:
    """Bir SSE olayı biçimlendirir."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_context(db: Session, entity: Entity, language: str = "tr") -> str:
    """Entity'nin son analiz edilmiş makaleleri + son değerlendirmesinden bağlam metni.

    Değerlendirme kartla AYNI kaynaktan: kullanıcının dilinde okunan son kayıt (tek kaynak
    kayıtta hüküm/risk/vade yönleri dilden bağımsız, metin bu dilde). Sohbet ile kart asla
    farklı yön söylemez."""
    articles = db.scalars(
        select(Article)
        .where(Article.entity_id == entity.id, Article.analyzed.is_(True))
        .order_by(Article.published_at.desc().nullslast())
        .limit(CONTEXT_ARTICLES)
    ).all()
    latest = _latest_analysis(db, entity.id, language)

    lines = [
        f"Tartışılan varlık: {entity.name} ({entity.type}:{entity.query}).",
        utc_context_line(),
    ]
    if latest:
        t = localized_analysis(latest, language)
        lines += [
            "",
            f"Son değerlendirme (kartta gösterilen; bununla çelişme): yön={latest.stance}, "
            f"kanaat={latest.conviction}, risk={latest.risk_score}/100, trend={latest.sentiment_trend}.",
        ]
        for key, label in (("short_term", "Kısa vade (~7 gün)"), ("long_term", "Uzun vade (30-90 gün)")):
            h = t.get(key)
            if isinstance(h, dict) and h.get("verdict"):
                drivers = "; ".join(
                    f"{'↑' if d.get('direction') == 'up' else '↓' if d.get('direction') == 'down' else '·'} {d.get('text')}"
                    for d in (h.get("drivers") or []))
                lines.append(f"{label}: {h['verdict']}" + (f" — {h['summary']}" if h.get("summary") else "")
                             + (f" Etkenler: {drivers}" if drivers else ""))
        lines.append(f"Özet: {t['summary']}")
    lines.append("")
    lines.append(f"Son analiz edilmiş {len(articles)} haber:")
    for a in articles:
        flags = ", ".join(a.risk_flags or []) or "-"
        lines.append(
            f"• (duygu {a.sentiment:+.2f}, {a.event_type}, riskler: {flags}) {a.title}"
        )
        if a.rationale:
            lines.append(f"    {a.rationale}")
    return "\n".join(lines)


@router.post("/chat")
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    entity = db.get(Entity, payload.entity_id)
    # İZOLASYON (IDOR): kullanıcı yalnızca KENDİ listesindeki entity hakkında sohbet
    # edebilir. Aksi halde başkasının takip ettiği varlığın haber/analiz bağlamı
    # sohbete sızardı. dashboard ucuyla aynı davranış: yoksa/erişilemezse 404.
    if entity is None or not in_watchlist(db, user.id, entity.id):
        raise ApiError(code="entity_not_found", status_code=404, detail="Entity bulunamadı.")
    # Bu kayıt (ve get_current_user'ın last_active_at'i) get_db (scope="function")
    # tarafından StreamingResponse DÖNMEDEN, yani akış başlamadan commit edilir.
    record_event(db, user.id, "chat", {"entity_id": entity.id, "name": entity.name})

    # Mesajları doğrula/normalize et (role user/assistant, string content).
    messages: list[dict] = []
    for m in payload.messages:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content})
    if not messages or messages[0]["role"] != "user":
        raise ApiError(code="chat_bad_request", status_code=400, detail="İlk mesaj 'user' olmalı ve boş olamaz.")

    language = user_language(user)
    context = _build_context(db, entity, language)
    # Sohbet çıktısı kullanıcının arayüz diline uysun (SYSTEM_PROMPT artık dil-nötr).
    system = (
        f"{SYSTEM_PROMPT}\n\n{output_language_directive(language)}"
        f"\n\nBAĞLAM (bu varlığın haber akışı):\n{context}"
    )

    # ÖNEMLİ: istek oturumu (db) bu fonksiyon döndüğünde commit edilip KAPATILIR;
    # akış ondan SONRA başlar. Bu yüzden DB'den gereken her şey (bağlam, dil, mesajlar)
    # yukarıda düz değerlere çevrildi; event_stream db'yi ya da ORM nesnelerini
    # (entity/user) KULLANMAZ. Akış sırasında yazma gerekirse kendi session_scope()'unu
    # açmalı (LLM kullanım/maliyet kaydı zaten budget içinde ayrı oturumla yazılıyor).
    def event_stream():
        # GÜVENLİK: kullanıcıya GENEL mesaj (model adı/config/iç ayrıntı sızdırma);
        # gerçek hatayı sunucuda logla.
        _log = logging.getLogger("newsradar.chat")
        try:
            client = get_llm_provider("chat")
        except MissingAPIKeyError as exc:
            _log.warning("chat: sağlayıcı yok: %s", exc)
            yield _sse("error", {"message": "Sohbet şu an kullanılamıyor.", "code": "chat_unavailable"})
            return
        try:
            for text in client.stream_chat(system=system, messages=messages, max_tokens=4096):
                yield _sse("delta", {"text": text})
            yield _sse("done", {})
        except ClaudeError as exc:
            _log.warning("chat: LLM hatası: %s", exc)
            yield _sse("error", {"message": "Sohbet yanıtı alınamadı, lütfen tekrar deneyin.", "code": "chat_failed"})
        except Exception as exc:  # noqa: BLE001 — beklenmedik hata sızdırma, logla
            _log.exception("chat: beklenmedik hata")
            yield _sse("error", {"message": "Beklenmedik bir hata oluştu.", "code": "unexpected"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
