"""frontend/src/locales/de.json → app/locales/email.de.json (yalnızca `email.*` anahtarları).

Kullanım (backend/ içinden): python -m app.locales.sync
"""

from __future__ import annotations

import json
from pathlib import Path

from . import EMAIL_DE

FRONTEND_DE = Path(__file__).resolve().parents[3] / "frontend" / "src" / "locales" / "de.json"


def email_keys(path: Path = FRONTEND_DE) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if k.startswith("email.")}


def main() -> None:
    keys = email_keys()
    EMAIL_DE.write_text(json.dumps(keys, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(keys)} anahtar → {EMAIL_DE}")


if __name__ == "__main__":
    main()
