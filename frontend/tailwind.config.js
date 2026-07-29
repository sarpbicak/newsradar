/** @type {import('tailwindcss').Config} */
// YUMUŞAK KOYU TEMA + MOR VURGU (Linear/Vercel tarzı). Saf siyah/beyaz YOK.
//  - ink-*  = yüzeyler/kenarlıklar (koyu taban → bir tık açık kart → ince açık kenarlık)
//  - slate-* = metin (küçük numara = açık/önemli, büyük numara = soluk)
//  - accent = MOR (yalnızca vurgu). Sinyal renkleri (emerald/rose) MOR DEĞİL — sabit.
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Yüzeyler: 900 = sayfa zemini (yumuşak koyu), 800 = kart (bir tık açık),
        // 700 = yükseltilmiş/hover/divide, 600/500 = ince/güçlü açık kenarlık.
        ink: {
          900: "#1A1D26", // sayfa zemini (yumuşak gri-lacivert — kömür karası değil)
          800: "#272C3A", // kart yüzeyi (tabandan belirgin ayrışır)
          700: "#313747", // yükseltilmiş/hover/divide
          600: "#3A4152", // ince kenarlık (~rgba(255,255,255,0.10))
          500: "#4A5164", // güçlü kenarlık/input
        },
        accent: "#7C5CFF", // MOR vurgu (marka; yalnızca aksan)
        // Metin (koyu zeminde): küçük numara = açık/önemli, büyük = soluk.
        slate: {
          100: "#E8E9ED", // birincil metin (kırık beyaz)
          200: "#D3D5DD",
          300: "#B4B8C4", // ikincil
          400: "#8B8F9E", // muted gövde metni
          500: "#6B6F7E", // etiket/zaman damgası
          600: "#565A68", // en soluk
          700: "#474B58",
        },
        // Yön/durum tonları — koyu zeminde okunaklı, PARLAK tonlar. (Mor DEĞİL.)
        emerald: { 200: "#3FD68C", 300: "#3FD68C", 400: "#3FD68C", 500: "#34C77E", 600: "#2FB873" },
        rose: { 200: "#FF6B6B", 300: "#FF6B6B", 400: "#FF6B6B", 500: "#F55A5A", 600: "#E84C4C" },
        amber: { 200: "#FBBF24", 300: "#FBBF24", 400: "#F59E0B", 500: "#F59E0B", 600: "#FBBF24" },
        sky: { 400: "#60A5FA", 500: "#3B82F6" },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        display: ["Space Grotesk", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        // Koyu tema: derinlik ince ton farkı + yumuşak siyah gölge; hover'da mor glow.
        card: "0 1px 2px rgba(0,0,0,0.35), 0 4px 16px rgba(0,0,0,0.28)",
        "card-hover": "0 4px 12px rgba(0,0,0,0.35), 0 12px 32px rgba(124,92,255,0.22)",
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
          "0%": { background: "rgba(124,92,255,0.22)" },
          "100%": { background: "transparent" },
        },
      },
      animation: {
        "card-in": "card-in 0.4s ease-out both",
        scan: "scan 1.4s ease-in-out infinite",
        flash: "flash 0.9s ease-out",
      },
    },
  },
  plugins: [],
};
