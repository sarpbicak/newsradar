"""Claude model tablosu — model başına sınırlar, API davranış farkları ve FİYATLAR TEK yerde.

Kaynaklar:
- Fiyatlar: platform.claude.com/docs/en/about-claude/pricing (Ekim 2026 itibarıyla)
- Çıktı sınırları: platform.claude.com/docs/en/about-claude/models/overview

Tabloda olmayan bir model adı yine çalışır (temkinli varsayılanlarla), ama bir uyarı
loglanır — `python -m app.cli llm-check` bunu da raporlar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("newsradar.models")


@dataclass(frozen=True)
class Price:
    """USD / 1M token. cache_write = 5 dk ephemeral yazma (1.25× girdi)."""

    input: float
    output: float
    cache_write: float
    cache_read: float


@dataclass(frozen=True)
class ModelSpec:
    # Modelin izin verdiği en yüksek max_tokens (çıktı). İstenen değer buna kırpılır.
    max_output_tokens: int
    # tool_choice {"type": "tool"} (zorunlu tool) kabul ediliyor mu? Sonnet 5.5 400 verir;
    # orada tool_choice=auto + açık talimat kullanılır, tool_use yoksa yine hata fırlatılır.
    forced_tool_choice: bool
    # Yapılandırılmış (tool) çağrılarda output_config.effort; None = modelin varsayılanı.
    tool_effort: str | None = None
    # Tool tanımlarına strict: true (grammar-constrained sampling): tool input'u şemaya
    # BİREBİR uyar — dizi yerine string gibi tip hataları kökten kesilir. Şemalar strict
    # kısıtlarına uygun olmalı (additionalProperties: false, minimum/maxLength vb. yok).
    strict_tools: bool = False
    price: Price | None = None
    # Uzun prompt fiyat kademesi: prompt (input + cache write + cache read) bu eşiği
    # AŞARSA isteğin TÜM kalemleri long_price ile faturalanır (Haiku 5.5: 100k → 5×).
    long_prompt_threshold: int | None = None
    long_price: Price | None = None


MODEL_SPECS: dict[str, ModelSpec] = {
    # Haiku 5.5: 128K çıktı; zorunlu tool_choice kabul (bu durumda thinking atlanır);
    # strict + zorunlu tool_choice birlikte canlı doğrulandı (2026-10-18).
    # Fiyat iki kademeli: prompt ≤100k → $0.10/$0.50; >100k → $0.50/$2.50 (cache dahil).
    "claude-haiku-5-5": ModelSpec(
        max_output_tokens=128_000, forced_tool_choice=True, strict_tools=True,
        price=Price(input=0.10, output=0.50, cache_write=0.125, cache_read=0.01),
        long_prompt_threshold=100_000,
        long_price=Price(input=0.50, output=2.50, cache_write=0.625, cache_read=0.05),
    ),
    # Sonnet 5.5: 128K çıktı; zorunlu tool_choice 400 → auto. Adaptive thinking açık,
    # varsayılan effort 'high' — maliyet için yapılandırılmış çağrılarda 'medium'.
    # Cache okuma 0.05× girdi ($0.10). strict + auto: docs'un forced tool_choice yerine
    # önerdiği desen (şema garantisini korur).
    "claude-sonnet-5-5": ModelSpec(
        max_output_tokens=128_000, forced_tool_choice=False, tool_effort="medium",
        strict_tools=True,
        price=Price(input=2.00, output=10.00, cache_write=2.50, cache_read=0.10),
    ),
}

# Tabloda olmayan model için temkinli varsayılan: auto tool_choice her modelde çalışır.
_FALLBACK = ModelSpec(max_output_tokens=8_192, forced_tool_choice=False)
_warned: set[str] = set()


def spec_for(model: str) -> ModelSpec:
    spec = MODEL_SPECS.get(model)
    if spec is None:
        if model not in _warned:
            _warned.add(model)
            logger.warning("Model '%s' model_specs tablosunda yok — temkinli varsayılanlar "
                           "(max_tokens≤%d, tool_choice=auto) ve maliyet hesabı YOK.",
                           model, _FALLBACK.max_output_tokens)
        return _FALLBACK
    return spec


def is_known(model: str) -> bool:
    return model in MODEL_SPECS


def cost_usd(model: str, input_tokens: int, output_tokens: int,
             cache_write_tokens: int = 0, cache_read_tokens: int = 0) -> float | None:
    """Tek çağrının USD maliyeti. input_tokens = önbelleksiz girdi (API usage.input_tokens).
    Fiyatı bilinmeyen model → None (çağıran 0 sayar ve uyarır)."""
    spec = MODEL_SPECS.get(model)
    if spec is None or spec.price is None:
        return None
    price = spec.price
    prompt = input_tokens + cache_write_tokens + cache_read_tokens
    if spec.long_prompt_threshold and spec.long_price and prompt > spec.long_prompt_threshold:
        price = spec.long_price
    return (input_tokens * price.input + output_tokens * price.output
            + cache_write_tokens * price.cache_write
            + cache_read_tokens * price.cache_read) / 1_000_000


def long_prompt_threshold(model: str) -> int | None:
    spec = MODEL_SPECS.get(model)
    return spec.long_prompt_threshold if spec else None
