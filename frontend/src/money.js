// Fiyatı kendi para biriminde, arayüz diline uygun biçimde yazar (dönüşüm YOK).
// tr: "$311,21", "€1.234,56", "₺1.234,56", "¥3.120" · en: "$311.21", "€1,234.56", "₺1,234.56"
// · de: "311,21 $", "1.234,56 €" (sembol sonda, Almanca yazım).
// Yen ve won ondalıksız. Saf modül (React/JSX yok) — e2e/money.spec.js doğrudan içe aktarır.
const NO_DECIMALS = new Set(["JPY", "KRW"]);
const LOCALES = { tr: "tr-TR", en: "en-US", de: "de-DE" };

export function fmtMoney(value, currency = "USD", lang = "tr", { digits } = {}) {
  if (value == null || Number.isNaN(value)) return "—";
  const cur = (currency || "USD").toUpperCase();
  const d = digits ?? (NO_DECIMALS.has(cur) ? 0 : 2);
  try {
    return new Intl.NumberFormat(LOCALES[lang] || "tr-TR", {
      style: "currency",
      currency: cur,
      currencyDisplay: "narrowSymbol",
      minimumFractionDigits: d,
      maximumFractionDigits: d,
    }).format(value);
  } catch {
    return `${value.toFixed(d)} ${cur}`; // bilinmeyen para birimi kodu
  }
}
