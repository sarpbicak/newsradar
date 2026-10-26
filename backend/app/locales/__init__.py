"""Backend'in Almanca metinleri (e-postalar).

Tek kaynak frontend/src/locales/de.json (Almanca metinlerin tamamı, anahtar → metin).
Backend image'ı yalnızca backend/ klasöründen build edildiği için `email.*` anahtarları
buraya kopyalanır: `python -m app.locales.sync`. test_email_de.py ikisinin eşitliğini denetler.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

EMAIL_DE = Path(__file__).with_name("email.de.json")


@lru_cache(maxsize=1)
def email_de() -> dict[str, str]:
    return json.loads(EMAIL_DE.read_text(encoding="utf-8"))
