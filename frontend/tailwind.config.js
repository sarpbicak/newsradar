/** @type {import('tailwindcss').Config} */
// AÇIK TEMA (HUD). Mevcut sınıf adları korunur; token'lar aydınlık palete remap edilir:
//  - ink-*  = yüzeyler/kenarlıklar (koyu→açık)
//  - slate-* = metin (ters çevrildi: yüksek numara = daha soluk, açık zeminde okunur)
//  - accent = elektrik mavi
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Yüzeyler: 900 = sayfa zemini (açık gri), 800 = kart (beyaz), 600/500 = kenarlık.
        ink: {
          900: "#EEF1F6", // sayfa zemini
          800: "#FFFFFF", // kart yüzeyi (saf beyaz)
          700: "#F1F4F8", // yükseltilmiş/hover/divide
          600: "#E4E8EF", // ince kenarlık
          500: "#D0D7E2", // güçlü kenarlık/input
        },
        accent: "#2563EB", // elektrik mavi
        // Metin (Tailwind slate override; ters: küçük=koyu/önemli, büyük=soluk).
        slate: {
          100: "#0B1220", // birincil metin (neredeyse siyah)
          200: "#1B2536",
          300: "#33415A",
          400: "#586074", // muted gövde metni
          500: "#7A8699", // etiket/zaman damgası
          600: "#98A2B3", // en soluk
          700: "#B4BCC9",
        },
        // Yön/durum tonları — açık zeminde okunacak kadar koyu.
        emerald: { 200: "#16A34A", 300: "#16A34A", 400: "#16A34A", 500: "#15803D", 600: "#15803D" },
        rose: { 200: "#DC2626", 300: "#DC2626", 400: "#DC2626", 500: "#B91C1C", 600: "#B91C1C" },
        amber: { 200: "#B45309", 300: "#B45309", 400: "#D97706", 500: "#D97706", 600: "#B45309" },
        sky: { 400: "#0284C7", 500: "#0369A1" },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        display: ["Space Grotesk", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,0.04), 0 4px 16px rgba(16,24,40,0.06)",
        "card-hover": "0 4px 8px rgba(16,24,40,0.06), 0 12px 32px rgba(37,99,235,0.12)",
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
          "0%": { background: "rgba(37,99,235,0.18)" },
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
