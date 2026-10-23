// Tema seçici: Sistem / Açık / Koyu (varsayılan Sistem = prefers-color-scheme). Tercih
// theme.js'teki ThemeProvider'da; burada yalnızca arayüz.
//  - ThemeMenu: nav'daki ikon butonu + açılır menü (ortak Menu; landing + uygulama).
//  - ThemeSegmented: mobil çekmecedeki üç parçalı seçim.
import React from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { useI18n } from "../i18n.jsx";
import { useThemeCtx } from "../theme.js";
import { Button, Menu, MenuItem } from "./kit.jsx";

const OPTIONS = [
  { pref: "system", Icon: Monitor, tkey: "theme.system" },
  { pref: "light", Icon: Sun, tkey: "theme.light" },
  { pref: "dark", Icon: Moon, tkey: "theme.dark" },
];

export function ThemeMenu() {
  const { t } = useI18n();
  const { pref, setPref } = useThemeCtx();
  const current = OPTIONS.find((o) => o.pref === pref) || OPTIONS[0];
  const label = t("theme.label", { name: t(current.tkey) });
  return (
    <Menu
      label={t("theme.title")}
      className="w-44"
      button={({ open, toggle }) => (
        <Button variant="ghost" iconOnly icon={current.Icon} onClick={toggle} title={label} aria-label={label} aria-haspopup="menu" aria-expanded={open} />
      )}
    >
      {OPTIONS.map(({ pref: p, Icon, tkey }) => (
        <MenuItem
          key={p}
          icon={Icon}
          role="menuitemradio"
          aria-checked={pref === p}
          onClick={() => setPref(p)}
          className={pref === p ? "font-semibold text-slate-100" : ""}
        >
          <span className="flex-1">{t(tkey)}</span>
          {pref === p && <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />}
        </MenuItem>
      ))}
    </Menu>
  );
}

export function ThemeSegmented() {
  const { t } = useI18n();
  const { pref, setPref } = useThemeCtx();
  return (
    <div>
      <div className="mb-2 text-micro font-medium text-slate-500">{t("theme.title")}</div>
      <div role="radiogroup" aria-label={t("theme.title")} className="grid grid-cols-3 gap-1 rounded-control bg-ink-900 p-1">
        {OPTIONS.map(({ pref: p, Icon, tkey }) => (
          <button
            key={p}
            role="radio"
            aria-checked={pref === p}
            onClick={() => setPref(p)}
            className={`tap flex h-12 flex-col items-center justify-center gap-0.5 rounded-lg text-micro transition-colors duration-hover ease-std ${
              pref === p ? "bg-raised font-semibold text-slate-100 shadow-card" : "text-slate-500 hover:text-slate-200"
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
