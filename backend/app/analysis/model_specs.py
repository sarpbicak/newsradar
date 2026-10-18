"""Claude model tablosu — model başına sınırlar ve API davranış farkları TEK yerde.

Kaynak: platform.claude.com/docs/en/about-models/overview (çıktı sınırı) ve model
geçiş notları. Tabloda olmayan bir model adı yine çalışır (temkinli varsayılanlarla),
ama bir uyarı loglanır — `python -m app.cli llm-check` bunu da raporlar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("newsradar.models")


@dataclass(frozen=True)
class ModelSpec:
    # Modelin izin verdiği en yüksek max_tokens (çıktı). İstenen değer buna kırpılır.
    max_output_tokens: int
    # tool_choice {"type": "tool"} (zorunlu tool) kabul ediliyor mu? Sonnet 5.5 400 verir;
    # orada tool_choice=auto + açık talimat kullanılır, tool_use yoksa yine hata fırlatılır.
    forced_tool_choice: bool
    # Yapılandırılmış (tool) çağrılarda output_config.effort; None = modelin varsayılanı.
    tool_effort: str | None = None


MODEL_SPECS: dict[str, ModelSpec] = {
    # Haiku 5.5: 128K çıktı; zorunlu tool_choice kabul (bu durumda thinking atlanır).
    "claude-haiku-5-5": ModelSpec(max_output_tokens=128_000, forced_tool_choice=True),
    # Sonnet 5.5: 128K çıktı; zorunlu tool_choice 400 → auto. Adaptive thinking açık,
    # varsayılan effort 'high' — maliyet için yapılandırılmış çağrılarda 'medium'.
    "claude-sonnet-5-5": ModelSpec(
        max_output_tokens=128_000, forced_tool_choice=False, tool_effort="medium",
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
