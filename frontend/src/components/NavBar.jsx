// Ortak navigasyon — landing ve uygulama AYNI bileşen; yalnızca içerik bağlama göre değişir.
// Solda logo + "NewsRadar", sağda bağlama özel öğeler (hepsi aynı yükseklikte, hizalı).
// En üstte saydam; kaydırınca yarı saydam + bulanık zemin (index.css .nav-bar).
// `below`: header'ın alt kenarına yapışan katman (ör. yenileme ilerleme çizgisi) — içeriği itmez.
import React, { useEffect, useState } from "react";
import Logo from "./Logo.jsx";

export const WRAP = "mx-auto w-full max-w-[1360px] px-5 sm:px-8 lg:px-10";

export function useScrolled(threshold = 8) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > threshold);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, [threshold]);
  return scrolled;
}

export function Brand({ href, onClick, label }) {
  return (
    <a
      href={href}
      onClick={onClick}
      aria-label={label}
      className="tap inline-flex h-10 items-center gap-2 rounded-lg font-display text-lg font-semibold tracking-tight text-slate-100"
    >
      <Logo className="h-5 w-5 text-accent" />
      NewsRadar
    </a>
  );
}

// Metin bağlantısı (alt çizgisi hover'da soldan çizilir).
export function NavLink({ href, onClick, className = "", children }) {
  return (
    <a
      href={href}
      onClick={onClick}
      className={`link-u nav-text tap hidden h-10 items-center px-1 text-slate-300 transition-colors duration-hover ease-std hover:text-slate-100 md:inline-flex ${className}`}
    >
      {children}
    </a>
  );
}

export default function NavBar({ brand, fixed = false, below = null, children }) {
  const scrolled = useScrolled();
  return (
    <header data-nav-bar data-scrolled={scrolled} className={`nav-bar ${fixed ? "fixed inset-x-0" : "sticky"} top-0 z-40`}>
      <div className={`${WRAP} flex h-16 items-center justify-between gap-3`}>
        {brand}
        {/* Tüm öğeler 40px; aralık tutarlı (8px, geniş ekranda 10px). */}
        <nav className="flex items-center gap-2 lg:gap-2.5" aria-label="NewsRadar">
          {children}
        </nav>
      </div>
      {below}
    </header>
  );
}
