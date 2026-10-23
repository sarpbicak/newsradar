// Tema: Sistem / Açık / Koyu. Renkler TEK kaynaktan: src/index.css'teki CSS değişkenleri.
// Bu dosya (1) JS'te renk gereken yerler (SVG, Recharts) için değişken referansları verir,
// (2) kullanıcının tercihini localStorage'da tutup <html data-theme> uygular.
// İlk boyamadan ÖNCE aynı mantık index.html'deki satır içi betikte çalışır (flaş olmaz);
// ikisinin anahtarı ve çözümlemesi aynı olmalı: THEME_KEY, resolve().
import { createContext, createElement, useContext, useEffect, useState } from "react";

// rgb(var(--x)) — SVG/Recharts niteliklerinde (stroke, fill) ve inline style'da çalışır.
export const cssColor = (name, alpha) =>
  alpha == null ? `rgb(var(--${name}))` : `rgb(var(--${name}) / ${alpha})`;

export const C = {
  accent: cssColor("accent"),
  line: cssColor("chart-line"),      // grafik ana çizgisi (nötr; vurgu rengi grafikte kullanılmaz)
  pos: cssColor("pos"),
  posStrong: cssColor("pos-strong"),
  neg: cssColor("neg"),
  negStrong: cssColor("neg-strong"),
  warn: cssColor("warn"),
  neutral: cssColor("neutral"),
  onStrong: cssColor("on-strong"),
  muted: cssColor("slate-500"),     // eksen etiketi / soluk metin
  subtle: cssColor("ink-500"),      // açık şerit / sıfır çizgisi
  grid: cssColor("chart-grid"),
  brushStroke: cssColor("brush-stroke"),
  brushFill: cssColor("brush-fill"),
};

export const THEME_KEY = "nr_theme";
export const THEME_PREFS = ["system", "light", "dark"];
const media = () => window.matchMedia?.("(prefers-color-scheme: dark)");
// Tarayıcı arayüzü (adres çubuğu) rengi — sayfa zeminiyle uyumlu.
const THEME_COLOR = { light: "#F7F5F1", dark: "#0D0D0B" };

export function getPref() {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return THEME_PREFS.includes(v) ? v : "system";
  } catch {
    return "system";
  }
}

export function resolve(pref) {
  if (pref === "light" || pref === "dark") return pref;
  return media()?.matches ? "dark" : "light";
}

export function applyTheme(pref) {
  const theme = resolve(pref);
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLOR[theme]);
  return theme;
}

// { pref, theme, setPref } — pref "system" iken işletim sistemi değişikliğini canlı izler.
// Uygulamada TEK örnek: ThemeProvider (main.jsx); bileşenler useThemeCtx() ile okur.
function useThemeState() {
  const [pref, setPrefState] = useState(getPref);
  const [theme, setTheme] = useState(() => resolve(pref));

  useEffect(() => {
    setTheme(applyTheme(pref));
    if (pref !== "system") return undefined;
    const mq = media();
    const onChange = () => setTheme(applyTheme("system"));
    mq?.addEventListener?.("change", onChange);
    return () => mq?.removeEventListener?.("change", onChange);
  }, [pref]);

  function setPref(next) {
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      /* özel mod vb. — tercih yalnızca bu oturumda geçerli */
    }
    setPrefState(next);
  }

  return { pref, theme, setPref };
}

const ThemeCtx = createContext({ pref: "system", theme: "light", setPref: () => {} });

export function ThemeProvider({ children }) {
  return createElement(ThemeCtx.Provider, { value: useThemeState() }, children);
}

export function useThemeCtx() {
  return useContext(ThemeCtx);
}
