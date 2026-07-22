"""Sohbet ucu: POST /chat — SSE streaming.

Gövde: {entity_id, messages: [{role, content}, ...]}
Sunucu, o entity'nin son ~15 analiz edilmiş makalesini bağlam olarak ekler ve
aynı sistem prompt'unu kullanır; böylece kullanıcı haberleri ve pozisyonu Claude
ile tartışabilir. Yanıt token-token SSE olarak akar.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analysis.claude_client import ClaudeClient, ClaudeError, MissingAPIKeyError
from ..analysis.prompts import SYSTEM_PROMPT, utc_context_line
from ..db.database import get_db
from ..db.models import Article, Entity, EntityAnalysis
from .schemas import ChatRequest

router = APIRouter(tags=["chat"])

CONTEXT_ARTICLES = 15


def _sse(event: str, data: dict) -> str:
    """Bir SSE olayı biçimlendirir."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_context(db: Session, entity: Entity) -> str:
    """Entity'nin son analiz edilmiş makaleleri + son değerlendirmesinden bağlam metni."""
    articles = db.scalars(
        select(Article)
        .where(Article.entity_id == entity.id, Article.analyzed.is_(True))
        .order_by(Article.published_at.desc().nullslast())
        .limit(CONTEXT_ARTICLES)
    ).all()
    latest = db.scalar(
        select(EntityAnalysis)
        .where(EntityAnalysis.entity_id == entity.id)
        .order_by(EntityAnalysis.created_at.desc())
    )

    lines = [
        f"Tartışılan varlık: {entity.name} ({entity.type}:{entity.query}).",
        utc_context_line(),
    ]
    if latest:
        lines += [
            "",
            f"Son değerlendirme: yön={latest.stance}, kanaat={latest.conviction}, "
            f"risk={latest.risk_score}/100, trend={latest.sentiment_trend}.",
            f"Özet: {latest.summary}",
        ]
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
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    entity = db.get(Entity, payload.entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity bulunamadı.")

    # Mesajları doğrula/normalize et (role user/assistant, string content).
    messages: list[dict] = []
    for m in payload.messages:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content})
    if not messages or messages[0]["role"] != "user":
        raise HTTPException(status_code=400, detail="İlk mesaj 'user' olmalı ve boş olamaz.")

    context = _build_context(db, entity)
    system = f"{SYSTEM_PROMPT}\n\nBAĞLAM (bu varlığın haber akışı):\n{context}"

    def event_stream():
        try:
            client = ClaudeClient()
        except MissingAPIKeyError as exc:
            yield _sse("error", {"message": str(exc)})
            return
        try:
            for text in client.stream_chat(system=system, messages=messages, max_tokens=4096):
                yield _sse("delta", {"text": text})
            yield _sse("done", {})
        except ClaudeError as exc:
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
