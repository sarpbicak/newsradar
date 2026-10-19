// public/favicon.svg'yi logo kaynağından (src/brand/logo.js) üretir — header ile AYNI
// çizim, aynı renk; yalnızca 16px'te okunsun diye çizgi daha kalın (FAVICON_STROKE).
// Ardından raster dosyalar için: python3 scripts/render_icons.py
// Kullanım: npm run icons
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  FAVICON_STROKE, LOGO_COLOR, LOGO_COLOR_DARK, LOGO_ELEMENTS, LOGO_VIEWBOX,
} from "../src/brand/logo.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const el = ({ tag, ...attrs }) =>
  `    <${tag} ${Object.entries(attrs).map(([k, v]) => `${k}="${v}"`).join(" ")}/>`;

const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${LOGO_VIEWBOX}" fill="none" stroke-linecap="round" stroke-linejoin="round">
  <!-- ÜRETİLMİŞ DOSYA — elle düzenleme; kaynak: src/brand/logo.js (npm run icons).
       Header logosuyla aynı çizim; 16px okunabilirliği için çizgi ${FAVICON_STROKE}.
       Açık temada sitenin ana rengi, koyu sekme çubuğunda açık ton. -->
  <style>
    .r { stroke: ${LOGO_COLOR}; stroke-width: ${FAVICON_STROKE}; }
    @media (prefers-color-scheme: dark) { .r { stroke: ${LOGO_COLOR_DARK}; } }
  </style>
  <g class="r">
${LOGO_ELEMENTS.map(el).join("\n")}
  </g>
</svg>
`;
writeFileSync(join(root, "public", "favicon.svg"), svg);
console.log("public/favicon.svg yazıldı (stroke", FAVICON_STROKE + ")");
