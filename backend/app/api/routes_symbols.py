"""Sembol arama ucu: GET /symbol-search?q=... (ticker eklerken otomatik tamamlama)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..symbol_search import search_symbols
from .schemas import SymbolResultOut

router = APIRouter(tags=["symbols"])


@router.get("/symbol-search", response_model=list[SymbolResultOut])
def symbol_search(q: str = Query("", max_length=100, description="Şirket adı ya da sembol")) -> list[SymbolResultOut]:
    """Finnhub /search üzerinden sembol önerileri. Anahtar yoksa/hata olursa boş liste."""
    return [SymbolResultOut(**r) for r in search_symbols(q)]
