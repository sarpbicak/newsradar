/** @type {import('tailwindcss').Config} */
// RENKLER TEK YERDEN: src/index.css'teki CSS değişkenleri (açık: :root, koyu: [data-theme="dark"]).
// Burada yalnızca adlar değişkenlere bağlanır; <alpha-value> sayesinde bg-rose-500/10 gibi
// saydamlık sınıfları iki temada da çalışır. Kontrast: iki temada WCAG AA (metin ≥4.5:1).
// TASARIM TOKEN'LARI landing ve uygulama için ORTAK. Hareket (eğri/süre) src/motion.js'te.
//  - ink-*   = yüzeyler/kenarlıklar (900 = zemin → 800 = kart → 700 hover → 600/500 ayırıcı);
//    raised = yükseltilmiş yüzey (modal, panel).
//  - slate-* = metin. DİKKAT: ölçek TERS — küçük numara = KOYU/önemli metin (açık temada),
//    büyük numara = soluk. Koyu temada da aynı anlam: 100 = en belirgin metin.
//  - accent  = TEK vurgu: camgöbeği (metin olarak AA tonu); accent-fg = üstündeki metin.
//    YALNIZCA birincil aksiyon, aktif durum ve marka anlarında — anlamsal renklerle karışmaz.
//  - signal / signal-fg = birincil buton dolgusu (canlı camgöbeği) ve üstündeki metin; glow = ışıma.
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
        // Birincil aksiyon dolgusu (canlı camgöbeği) + üstündeki metin + ışıma. Ayrıntı: index.css.
        signal: v("signal"),
        "signal-ink": v("signal-ink"),
        "signal-fg": v("signal-fg"),
        glow: v("glow"),
        raised: v("raised"),
        "chart-line": v("chart-line"),
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
        // Başlıklar ve hüküm cümleleri (landing + uygulama). Serif yok.
        display: ["Space Grotesk", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      // Uygulama yazı ölçeği (index.css --fs-*): sayfa 30 · hüküm 28 · kart 21 · gövde 15 · yardımcı 13 · etiket 12
      fontSize: {
        page: ["var(--fs-page)", { lineHeight: "1.15", letterSpacing: "-0.02em" }],
        verdict: ["var(--fs-verdict)", { lineHeight: "1.2", letterSpacing: "-0.02em" }],
        title: ["var(--fs-title)", { lineHeight: "1.3", letterSpacing: "-0.01em" }],
        body: ["var(--fs-body)", { lineHeight: "1.6" }],
        meta: ["var(--fs-meta)", { lineHeight: "1.45" }],
        micro: ["var(--fs-micro)", { lineHeight: "1.35" }],
      },
      borderRadius: {
        control: "var(--r-control)",
        card: "var(--r-card)",
        panel: "var(--r-panel)",
      },
      transitionDuration: { hover: "var(--dur-hover)", state: "var(--dur-state)", page: "var(--dur-page)" },
      transitionTimingFunction: { std: "var(--ease)" },
      boxShadow: {
        // Kağıt tema: çok yumuşak, dağınık, hafif gölge (üstte duran kart hissi).
        card: "var(--shadow-card)",
        "card-hover": "var(--shadow-card-hover)",
        raised: "var(--shadow-raised)",
        glow: "0 10px 28px -12px rgb(var(--glow) / 0.7)",
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
      },
      animation: {
        "card-in": "card-in var(--dur-page) var(--ease) both",
        scan: "scan var(--dur-shimmer) ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
