// Dil seçimi öğeleri: inline SVG bayraklar (emoji DEĞİL), ilk-giriş modalı, header
// değiştirici. Bayraklar küçük, yuvarlatılmış, ince kenarlıklı (beyaz kısımlar kaybolmasın).
import React from "react";
import { LANGS, useI18n } from "../i18n.jsx";
import { Menu, MenuItem, Modal } from "./kit.jsx";

const flagWrap = "inline-block overflow-hidden rounded-[3px] ring-1 ring-slate-500/30";

// Türkiye bayrağı — kırmızı zemin + beyaz hilal + yıldız.
export function FlagTR({ className = "h-4 w-6" }) {
  return (
    <span className={`${flagWrap} ${className}`}>
      <svg viewBox="0 0 30 20" className="h-full w-full" preserveAspectRatio="xMidYMid slice">
        <rect width="30" height="20" fill="#E30A17" />
        <circle cx="11.5" cy="10" r="5" fill="#fff" />
        <circle cx="13" cy="10" r="4" fill="#E30A17" />
        <path fill="#fff" d="M17.6 10l-2.9-.95 1.8 2.45v-3l-1.8 2.45z" transform="translate(1.2,0) scale(1.15) translate(-2.3,-1.3)" />
      </svg>
    </span>
  );
}

// Birleşik Krallık bayrağı (İngilizce için nötr) — basitleştirilmiş Union Jack.
export function FlagGB({ className = "h-4 w-6" }) {
  return (
    <span className={`${flagWrap} ${className}`}>
      <svg viewBox="0 0 30 20" className="h-full w-full" preserveAspectRatio="xMidYMid slice">
        <clipPath id="ukc"><rect width="30" height="20" /></clipPath>
        <g clipPath="url(#ukc)">
          <rect width="30" height="20" fill="#012169" />
          <path d="M0,0 30,20 M30,0 0,20" stroke="#fff" strokeWidth="4" />
          <path d="M0,0 30,20" stroke="#C8102E" strokeWidth="2" clipPath="url(#ukc)" />
          <path d="M30,0 0,20" stroke="#C8102E" strokeWidth="2" />
          <rect x="12.5" width="5" height="20" fill="#fff" />
          <rect y="7.5" width="30" height="5" fill="#fff" />
          <rect x="13.5" width="3" height="20" fill="#C8102E" />
          <rect y="8.5" width="30" height="3" fill="#C8102E" />
        </g>
      </svg>
    </span>
  );
}

// Almanya bayrağı — siyah, kırmızı, altın yatay şeritler.
export function FlagDE({ className = "h-4 w-6" }) {
  return (
    <span className={`${flagWrap} ${className}`}>
      <svg viewBox="0 0 30 20" className="h-full w-full" preserveAspectRatio="xMidYMid slice">
        <rect width="30" height="20" fill="#000" />
        <rect y="6.67" width="30" height="6.67" fill="#DD0000" />
        <rect y="13.33" width="30" height="6.67" fill="#FFCE00" />
      </svg>
    </span>
  );
}

const FLAGS = { tr: FlagTR, en: FlagGB, de: FlagDE };
// Dil adları kendi dilinde (hangi arayüz dilinde olursa olsun aynı; çeviri gerekmez).
export const LANG_NAMES = { tr: "Türkçe", en: "English", de: "Deutsch" };

export function Flag({ lang, className }) {
  const F = FLAGS[lang] || FlagGB;
  return <F className={className} />;
}

// İlk giriş: sade dil seçim modalı (tek tıkla geçer; seçim yapılmadan kapanmaz).
export function LanguageModal({ onSelect }) {
  const { t } = useI18n();
  const opt = (lang, name) => (
    <button
      type="button"
      onClick={() => onSelect(lang)}
      className="tap flex h-14 w-full items-center gap-3 rounded-control bg-ink-800 px-4 text-left ring-1 ring-ink-600 transition duration-hover ease-std hover:bg-ink-700 hover:ring-accent/50"
    >
      <Flag lang={lang} className="h-6 w-9" />
      <span className="font-display text-base font-medium text-slate-100">{name}</span>
    </button>
  );
  return (
    <Modal labelledBy="lang-title" size="sm" dismissable={false}>
      <h2 id="lang-title" className="text-center font-display text-title font-semibold text-slate-100">
        {t("langmodal.title")}
      </h2>
      <p className="mb-6 mt-1.5 text-center text-meta text-slate-500">{t("langmodal.subtitle")}</p>
      <div className="space-y-2.5">
        {LANGS.map((l) => <React.Fragment key={l}>{opt(l, LANG_NAMES[l])}</React.Fragment>)}
      </div>
    </Modal>
  );
}

// Header'daki değiştirici — üç küçük bayrak butonu (tooltip'te dil adı).
// size="lg": mobil çekmecede tema kontrolüyle aynı ölçü (48px).
export function LanguageSwitcher({ lang, onChange, size = "md" }) {
  const lg = size === "lg";
  const btn = (l, label) => {
    const on = lang === l;
    return (
      <button
        type="button"
        onClick={() => onChange(l)}
        title={label}
        aria-label={label}
        aria-pressed={on}
        lang={l}
        className={`tap-sq inline-flex items-center justify-center rounded-control transition duration-hover ease-std ${lg ? "h-12 w-12" : "h-10 w-9 sm:w-10"} ${
          on ? "bg-ink-700" : "opacity-55 hover:bg-ink-700 hover:opacity-100"
        }`}
      >
        <Flag lang={l} className={lg ? "h-5 w-7" : "h-4 w-6"} />
      </button>
    );
  };
  return (
    <div className={`inline-flex items-center ${lg ? "gap-1" : "gap-0.5"}`}>
      {LANGS.map((l) => <React.Fragment key={l}>{btn(l, LANG_NAMES[l])}</React.Fragment>)}
    </div>
  );
}

// Dar ekran (landing nav, <640px): üç bayrak sığmaz → geçerli bayrak + açılır menü (klavye: Esc,
// ok tuşları; Menu bileşeni). Geniş ekranda LanguageSwitcher (üç bayrak) kullanılır.
export function LanguageMenu({ lang, onChange }) {
  const { t } = useI18n();
  const label = `${t("header.language")}: ${LANG_NAMES[lang]}`;
  return (
    <Menu
      label={t("header.language")}
      className="w-44"
      button={({ open, toggle }) => (
        <button
          type="button"
          onClick={toggle}
          title={label}
          aria-label={label}
          aria-haspopup="menu"
          aria-expanded={open}
          className="tap-sq inline-flex h-10 w-10 items-center justify-center rounded-control transition duration-hover ease-std hover:bg-ink-700"
        >
          <Flag lang={lang} className="h-4 w-6" />
        </button>
      )}
    >
      {LANGS.map((l) => (
        <MenuItem
          key={l}
          role="menuitemradio"
          aria-checked={lang === l}
          lang={l}
          onClick={() => onChange(l)}
          className={lang === l ? "font-semibold text-slate-100" : ""}
        >
          <Flag lang={l} className="h-3.5 w-5" />
          <span className="flex-1">{LANG_NAMES[l]}</span>
          {lang === l && <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />}
        </MenuItem>
      ))}
    </Menu>
  );
}
