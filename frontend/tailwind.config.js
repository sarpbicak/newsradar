/** @type {import('tailwindcss').Config} */
// SICAK KAĞIT TEMA + LACİVERT VURGU. Saf siyah/beyaz YOK; zemin krem, metin sıcak siyah.
//  - ink-*  = yüzeyler/kenarlıklar (900 = krem sayfa → 800 = beyaz kart → açık kenarlık)
//  - slate-* = metin. DİKKAT: ölçek TERS ÇEVRİLİ. Tailwind'de normalde slate küçük
//    numara = açık renktir; burada kağıt zemine göre küçük numara = KOYU/önemli metin,
//    büyük numara = SOLUK metin. (900→100'e geçerken kod aynı kalsın diye ölçek
//    yeniden eşlendi; yani text-slate-100 = en koyu, text-slate-700 = en soluk.)
//  - accent = KOYU MÜREKKEP LACİVERT (yalnızca vurgu; editöryel/finans hissi, sıcak
//    kağıtla uyumlu). Sinyal renkleri (emerald/rose) sabit — vurgu rengiyle karışmaz.
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // SICAK KAĞIT: 900 = kağıt zemini (krem), 800 = kart (beyaz), 700 = hover,
        // 600/500 = sıcak açık kenarlıklar.
        ink: {
          900: "#F7F5F1", // sayfa zemini (sıcak kağıt tonu)
          800: "#FFFFFF", // kart yüzeyi (saf beyaz)
          700: "#F1EEE8", // yükseltilmiş/hover/divide (sıcak açık)
          600: "#E7E3DA", // ince kenarlık (~rgba(0,0,0,0.08) sıcak)
          500: "#D8D3C7", // güçlü kenarlık/input
        },
        accent: "#1E3A5F",          // koyu mürekkep lacivert (birincil vurgu)
        "accent-hover": "#2C5282",  // hover/aktif için biraz açığı
        // Metin (kağıt zeminde): küçük numara = koyu/önemli, büyük = soluk.
        slate: {
          100: "#1A1A18", // birincil metin (sıcak siyah — tam siyah değil)
          200: "#2A2A26",
          300: "#45423C", // ikincil koyu
          400: "#6B6862", // muted gövde metni (sıcak gri)
          500: "#8A867E", // etiket/zaman damgası
          600: "#A8A49B", // daha soluk
          700: "#C4C0B6", // en soluk
        },
        // Yön/durum tonları — kağıt zeminde okunaklı, DOYGUN. (Lacivert vurguyla karışmaz.)
        emerald: { 200: "#0F8A4C", 300: "#0F8A4C", 400: "#0F8A4C", 500: "#0B7A42", 600: "#0B7A42" },
        rose: { 200: "#C62828", 300: "#C62828", 400: "#C62828", 500: "#A81E1E", 600: "#A81E1E" },
        amber: { 200: "#B45309", 300: "#B45309", 400: "#C77700", 500: "#B45309", 600: "#B45309" },
        sky: { 400: "#2563EB", 500: "#1D4ED8" },
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
        card: "0 1px 3px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.04)",
        "card-hover": "0 2px 6px rgba(0,0,0,0.06), 0 14px 32px rgba(30,58,95,0.10)",
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
          "0%": { background: "rgba(30,58,95,0.14)" },
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
