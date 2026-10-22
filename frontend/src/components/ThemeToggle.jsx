// Tema seçici: Sistem / Açık / Koyu (varsayılan Sistem = prefers-color-scheme). Tercih
// theme.js'teki ThemeProvider'da; burada yalnızca arayüz.
//  - ThemeMenu: header'daki ikon butonu + küçük açılır menü (masaüstü).
//  - ThemeSegmented: mobil menü içindeki üç parçalı seçim.
import React, { useEffect, useRef, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { useI18n } from "../i18n.jsx";
import { useThemeCtx } from "../theme.js";

const OPTIONS = [
  { pref: "system", Icon: Monitor, tkey: "theme.system" },
  { pref: "light", Icon: Sun, tkey: "theme.light" },
  { pref: "dark", Icon: Moon, tkey: "theme.dark" },
];

export function ThemeMenu() {
  const { t } = useI18n();
  const { pref, setPref } = useThemeCtx();
  const [open, setOpen] = useState(false);
  const wrap = useRef(null);
  const current = OPTIONS.find((o) => o.pref === pref) || OPTIONS[0];

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    const onDown = (e) => wrap.current && !wrap.current.contains(e.target) && setOpen(false);
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onDown);
    // Açılınca seçili seçeneğe odaklan (klavye ile gezinme).
    wrap.current?.querySelector('[aria-checked="true"]')?.focus();
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onDown);
    };
  }, [open]);

  const label = t("theme.label", { name: t(current.tkey) });
  return (
    <div ref={wrap} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        title={label}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex min-h-[36px] min-w-[36px] items-center justify-center rounded-lg text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
      >
        <current.Icon className="h-4 w-4" />
      </button>
      {open && (
        <div
          role="menu"
          aria-label={t("theme.title")}
          className="absolute right-0 top-full z-30 mt-2 w-40 rounded-xl border border-ink-500 bg-ink-800 p-1 shadow-card-hover"
        >
          {OPTIONS.map(({ pref: p, Icon, tkey }) => (
            <button
              key={p}
              role="menuitemradio"
              aria-checked={pref === p}
              onClick={() => {
                setPref(p);
                setOpen(false);
              }}
              className={`flex min-h-[40px] w-full items-center gap-2 rounded-lg px-3 text-left text-sm transition hover:bg-ink-700 ${
                pref === p ? "font-semibold text-slate-100" : "text-slate-400"
              }`}
            >
              <Icon className="h-4 w-4" />
              <span className="flex-1">{t(tkey)}</span>
              {pref === p && <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function ThemeSegmented() {
  const { t } = useI18n();
  const { pref, setPref } = useThemeCtx();
  return (
    <div className="px-3 py-2">
      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">{t("theme.title")}</div>
      <div role="radiogroup" aria-label={t("theme.title")} className="grid grid-cols-3 gap-1 rounded-lg bg-ink-700 p-1">
        {OPTIONS.map(({ pref: p, Icon, tkey }) => (
          <button
            key={p}
            role="radio"
            aria-checked={pref === p}
            onClick={() => setPref(p)}
            className={`flex min-h-[40px] flex-col items-center justify-center gap-0.5 rounded-md text-[11px] transition ${
              pref === p ? "bg-ink-800 font-semibold text-slate-100 shadow-card" : "text-slate-500"
            }`}
          >
            <Icon className="h-4 w-4" />
            {t(tkey)}
          </button>
        ))}
      </div>
    </div>
  );
}
