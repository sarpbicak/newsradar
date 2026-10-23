// NewsRadar logosu — TEK KAYNAK. Header (components/Logo.jsx) ve favicon dosyaları
// (scripts/build-icons.mjs → public/favicon.svg → scripts/render_icons.py → .ico/.png)
// bu çizimden üretilir. Şekli değiştirirsen ikonları yeniden üret: `npm run icons`.
// Çizim: lucide "radar" (ISC lisanslı) — 24'lük viewBox, stroke tabanlı.

export const LOGO_VIEWBOX = "0 0 24 24";

// detail: true → İÇ ayrıntı (iç yaylar + küçük noktalar). 16 px favicon'da çıkarılır; dış
// şekil (dış halka, merkez, tarama çizgisi) her boyutta aynı kalır.
export const LOGO_ELEMENTS = [
  { tag: "path", d: "M19.07 4.93A10 10 0 0 0 6.99 3.34" },          // dış halka (üst)
  { tag: "path", d: "M4 6h.01", detail: true },                    // nokta
  { tag: "path", d: "M2.29 9.62A10 10 0 1 0 21.31 8.35" },          // dış halka
  { tag: "path", d: "M16.24 7.76A6 6 0 1 0 8.23 16.67", detail: true }, // iç yay
  { tag: "path", d: "M12 18h.01", detail: true },                  // nokta
  { tag: "path", d: "M17.99 11.66A6 6 0 0 1 15.77 16.67", detail: true }, // iç yay
  { tag: "circle", cx: 12, cy: 12, r: 2 },                          // merkez
  { tag: "path", d: "m13.41 10.59 5.66-5.66" },                     // tarama çizgisi
];

// Renk: sitenin vurgu rengi — açık tema --accent, koyu tema --accent (src/index.css ile AYNI;
// header logosu currentColor ile bu değişkeni izler, favicon statik olduğu için değer burada).
export const LOGO_COLOR = "#0E7490";
export const LOGO_COLOR_DARK = "#22D3EE";
// Header'daki çizgi kalınlığı; favicon'da 16px'te okunsun diye daha kalın (şekil aynı).
export const LOGO_STROKE = 2;
export const FAVICON_STROKE = 2.75;
// 16 px sade favicon: iç ayrıntı yok, çizgi daha kalın (dış şekil aynı).
export const FAVICON_SMALL_STROKE = 3;
// SVG içindeki media query eşiği: bu genişliğin altında çizildiğinde sade sürüm.
export const FAVICON_SMALL_MAX = 24;
