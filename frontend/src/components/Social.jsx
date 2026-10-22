// Kurucu bağlantıları + marka ikonları — TEK yer (geri bildirim paneli ve landing kullanır).
// lucide bu sürümde marka glifi içermiyor: küçük inline SVG'ler, AYNI stil (24'lük viewBox,
// fill="none" + 2px stroke). GitHub çizimi lucide'ın eski "github" ikonundan (ISC lisansı).
import React from "react";

// ── DEĞİŞTİR (Sarp): adresler yalnızca burada ──────────────────────────────
export const LINKEDIN_URL = "https://www.linkedin.com/in/sarp-b%C4%B1%C3%A7ak-b5607037b/";
export const INSTAGRAM_URL = "https://www.instagram.com/sarpbicak24/";
export const GITHUB_PROFILE_URL = "https://github.com/sarpbicak";
export const GITHUB_REPO_URL = "https://github.com/sarpbicak/newsradar";
// ────────────────────────────────────────────────────────────────────────────

const ICON_PROPS = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  className: "block h-4 w-4 shrink-0",
  "aria-hidden": true,
};

export function LinkedInIcon() {
  return (
    <svg {...ICON_PROPS}>
      <g transform="translate(0 0.5)">
        <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-4 0v7h-4v-7a6 6 0 0 1 6-6z" />
        <rect x="2" y="9" width="4" height="12" />
        <circle cx="4" cy="4" r="2" />
      </g>
    </svg>
  );
}

export function InstagramIcon() {
  return (
    <svg {...ICON_PROPS}>
      <rect x="2" y="2" width="20" height="20" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function GitHubIcon({ className = "block h-4 w-4 shrink-0" }) {
  return (
    <svg {...ICON_PROPS} className={className}>
      <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
      <path d="M9 18c-4.51 2-5-2-7-2" />
    </svg>
  );
}

export function SocialIcon({ href, label, children }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      aria-label={label}
      title={label}
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-ink-500 text-slate-500 transition hover:border-accent/60 hover:text-accent"
    >
      {children}
    </a>
  );
}
