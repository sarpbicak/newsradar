"""public/favicon.svg → favicon.ico (32×32 + 16×16) ve apple-touch-icon.png (180×180, opak).

favicon.svg logo kaynağından (src/brand/logo.js) `node scripts/build-icons.mjs` ile üretilir;
bu betik raster dosyaları AYNI SVG'den üretir (tek çizim). `npm run icons` ikisini sırayla
çalıştırır. Gereksinim: Google Chrome (headless --screenshot) + Pillow.

Render 512 px'te yapılır, PIL ile küçültülür (16/32 px'te temiz kenar yumuşatma).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
SVG = PUBLIC / "favicon.svg"
CREAM = (0xF7, 0xF5, 0xF1)  # sayfa zemini (tailwind ink-900) — apple-touch-icon opak arka plan
MASTER = 512

CHROME_CANDIDATES = [
    os.environ.get("CHROME", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
    shutil.which("chromium-browser") or "",
]


def chrome() -> str:
    for c in CHROME_CANDIDATES:
        if c and Path(c).exists():
            return c
    sys.exit("Chrome bulunamadı — CHROME ortam değişkeniyle yolu verin.")


def render_master(tmp: Path) -> Image.Image:
    html = tmp / "icon.html"
    html.write_text(
        f"<html><body style='margin:0;background:transparent'>"
        f"<img src='{SVG.as_uri()}' style='width:{MASTER}px;height:{MASTER}px;display:block'>"
        f"</body></html>",
        encoding="utf-8",
    )
    out = tmp / "master.png"
    subprocess.run(
        [chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--allow-file-access-from-files", "--default-background-color=00000000",
         f"--window-size={MASTER},{MASTER}", f"--screenshot={out}", html.as_uri()],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return Image.open(out).convert("RGBA").crop((0, 0, MASTER, MASTER))


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        master = render_master(Path(d))
    if master.getbbox() is None:
        sys.exit("Render boş çıktı — SVG yolu/Chrome sürümünü kontrol edin.")
    i32 = master.resize((32, 32), Image.LANCZOS)
    i16 = master.resize((16, 16), Image.LANCZOS)
    i32.save(PUBLIC / "favicon.ico", format="ICO", sizes=[(32, 32), (16, 16)], append_images=[i16])
    # apple-touch-icon: 180×180 OPAK krem zemin, ~%16 kenar boşluğu (iOS köşeleri kendisi yuvarlar).
    inner = 124
    apple = Image.new("RGBA", (180, 180), CREAM + (255,))
    glyph = master.resize((inner, inner), Image.LANCZOS)
    apple.alpha_composite(glyph, ((180 - inner) // 2, (180 - inner) // 2))
    apple.convert("RGB").save(PUBLIC / "apple-touch-icon.png")
    # Önizleme için (repoya girmez): 16/32 px PNG
    for size, img in ((16, i16), (32, i32)):
        img.save(Path(tempfile.gettempdir()) / f"nr_favicon_{size}.png")
    print("favicon.ico (32+16) ve apple-touch-icon.png (180, opak) yazıldı.")


if __name__ == "__main__":
    main()
