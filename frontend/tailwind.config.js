/** @type {import('tailwindcss').Config} */
// RENKLER TEK YERDEN: src/index.css'teki CSS değişkenleri (açık: :root, koyu: [data-theme="dark"]).
// Burada yalnızca adlar değişkenlere bağlanır; <alpha-value> sayesinde bg-rose-500/10 gibi
// saydamlık sınıfları iki temada da çalışır. Kontrast: iki temada WCAG AA (metin ≥4.5:1).
//  - ink-*   = yüzeyler/kenarlıklar (900 = sayfa → 800 = kart → 700 hover → 600/500 kenarlık)
//  - slate-* = metin. DİKKAT: ölçek TERS — küçük numara = KOYU/önemli metin (açık temada),
//    büyük numara = soluk. Koyu temada da aynı anlam: 100 = en belirgin metin.
//  - accent  = vurgu (açıkta koyu lacivert, koyuda açık lacivert); accent-fg = vurgu üstü metin.
//  - signal/signal-ink/signal-fg/night = yalnızca landing ("/"): tek vurgu ve zemin.
//  - emerald/rose/amber/sky = sinyal tonları (pos/neg/warn/info); 500-600 "güçlü" tonlar.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 900: v("ink-900"), 800: v("ink-800"), 700: v("ink-700"), 600: v("ink-600"), 500: v("ink-500") },
        accent: v("accent"),
        "accent-hover": v("accent-hover"),
        "accent-fg": v("accent-fg"),
        "on-strong": v("on-strong"),
        // Landing: tek vurgu (sinyal yeşili) + zemin. Ayrıntı: index.css.
        signal: v("signal"),
        "signal-ink": v("signal-ink"),
        "signal-fg": v("signal-fg"),
        night: v("night"),
        slate: {
          100: v("slate-100"), 200: v("slate-200"), 300: v("slate-300"), 400: v("slate-400"),
          500: v("slate-500"), 600: v("slate-600"), 700: v("slate-700"),
        },
        emerald: { 200: v("pos"), 300: v("pos"), 400: v("pos"), 500: v("pos-strong"), 600: v("pos-strong") },
        rose: { 200: v("neg"), 300: v("neg"), 400: v("neg"), 500: v("neg-strong"), 600: v("neg-strong") },
        amber: { 200: v("warn"), 300: v("warn"), 400: v("warn"), 500: v("warn"), 600: v("warn") },
        sky: { 400: v("info"), 500: v("info-strong") },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        display: ["Space Grotesk", "Inter", "system-ui", "sans-serif"],
        // Editöryel hüküm cümlesi — gazete manşeti hissi.
        serif: ["Source Serif 4", "Georgia", "Cambria", "Times New Roman", "serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        // Kağıt tema: çok yumuşak, dağınık, hafif gölge (üstte duran kart hissi).
        card: "var(--shadow-card)",
        "card-hover": "var(--shadow-card-hover)",
      },
      keyframes: {
        "card-in": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        scan: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(300%)" },
        },
        flash: {
          "0%": { background: "rgb(var(--accent) / 0.14)" },
          "100%": { background: "transparent" },
        },
      },
      animation: {
        "card-in": "card-in 0.22s ease-out both",
        scan: "scan 1.4s ease-in-out infinite",
        flash: "flash 0.9s ease-out",
      },
    },
  },
  plugins: [],
};
