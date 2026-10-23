// Uygulama header'ı — landing ile AYNI NavBar; içerik araç bağlamına göre.
// Masaüstü (soldan sağa): Nasıl çalışır? · dil · tema · kullanıcı menüsü (ya da Giriş yap /
// Hesap oluştur) · en sağda "Yenile" (birincil). Yenileme sırasında buton "Yenileniyor 3/12";
// ilerleme header'ın alt kenarında ince bir çizgi (içeriği itmez) + küçük durum metni.
// Mobil: logo · Yenile · menü → tam ekran çekmece (dil, tema, nasıl çalışır, hesap).
import React, { useEffect, useId, useRef, useState } from "react";
import { HelpCircle, LayoutDashboard, LogIn, LogOut, Menu as MenuIcon, RefreshCw, ShieldCheck, UserPlus, X } from "lucide-react";
import { fmtTime, parseUtc, refreshParts, useI18n } from "../i18n.jsx";
import { navigate } from "../router.js";
import { Button, Menu, MenuItem, Modal, cx } from "./kit.jsx";
import { LanguageSwitcher } from "./LanguageBits.jsx";
import NavBar, { Brand, NavLink } from "./NavBar.jsx";
import { ThemeMenu, ThemeSegmented } from "./ThemeToggle.jsx";

const STEP_KEYS = {
  fetch: "notice.stepFetch",
  filter: "notice.stepFilter",
  analyze: "notice.stepAnalyze",
  assess: "notice.stepAssess",
};

// Yenileme durumunun tek satırlık metni (backend adımı yayınlar; kullanıcının dilinde).
function scanLabel(t, scan) {
  const { phase, step, stepEntity, stepCount, currentEntity, skippedEntity, summary } = scan;
  if (phase === "done") return summary ? t("notice.scanDone", { parts: refreshParts(summary, t).slice(0, 2).join(" · ") }) : "";
  if (phase === "starting") return t("notice.scanStarting");
  if (skippedEntity) return t("notice.stepSkipped", { name: skippedEntity });
  if (step === "prices") return t("notice.stepPrices");
  if (step && stepEntity && STEP_KEYS[step]) return t(STEP_KEYS[step], { name: stepEntity, n: stepCount ?? 0 });
  if (currentEntity) return t("notice.analyzing", { name: currentEntity });
  return t("notice.scanWorking");
}

// Header'ın alt kenarındaki ince ilerleme çizgisi + sağda küçük durum metni (yer kaplamaz).
function ScanProgress({ scan }) {
  const { t } = useI18n();
  const { phase, fraction, done, total, fading } = scan;
  const pct = phase === "done" ? 1 : fraction > 0 ? fraction : total > 0 ? done / total : 0.04;
  const label = scanLabel(t, scan);
  return (
    <div className={cx("pointer-events-none absolute inset-x-0 top-full", fading && "nr-strip--fade")} role="status" aria-live="polite">
      <div className="h-0.5 overflow-hidden bg-accent/15">
        <div className={cx("nav-progress h-full bg-accent", phase !== "done" && (phase === "starting" || !fraction) && "animate-pulse")} style={{ transform: `scaleX(${pct})` }} />
      </div>
      {label && (
        <div className="mx-auto flex w-full max-w-[1360px] justify-end px-5 sm:px-8 lg:px-10">
          <span key={label} className="nr-name-in mt-2 hidden max-w-md truncate rounded-full bg-raised px-3 py-1 text-micro text-slate-400 shadow-card ring-1 ring-ink-600 md:inline-block">
            {label}
          </span>
        </div>
      )}
    </div>
  );
}

// Yenileme hakkı: sayılar backend'den (/status ← NEWSRADAR_MAX_REFRESH_ANON / _REGISTERED);
// frontend'de sabit sayı yok. Admin (limit 0) → sayı gösterilmez.
export function refreshQuota(status) {
  if (!status || status.refresh_is_admin || !(status.refresh_limit > 0)) return { admin: true, left: null, exhausted: false };
  const left = Math.max(0, status.refresh_limit - status.refresh_used);
  return { admin: false, left, exhausted: left === 0, resetsAt: status.refresh_resets_at ? parseUtc(status.refresh_resets_at) : null };
}

// Hak dolduysa ne zaman geri gelir: kayan 24 saat — bugünse saat, değilse "yarın".
export function resetText(t, q) {
  const d = q.resetsAt;
  if (!d || d.toDateString() !== new Date().toDateString()) return t("header.resetsTomorrow");
  return t("header.resetsAt", { time: fmtTime(d) });
}

function refreshTip(t, status, anonymous) {
  const a = status?.refresh_limit_anon;
  const r = status?.refresh_limit_registered;
  if (!a && !r) return null;
  return anonymous ? t("header.refreshTipAnon", { a, r, n: a }) : t("header.refreshTipReg", { r, n: r });
}

function RefreshButton({ refresh, compact = false }) {
  const { t } = useI18n();
  const { isRefreshing, running, status, onRefresh, attn, anonymous } = refresh;
  const q = refreshQuota(status);
  const [tip, setTip] = useState(false);
  const press = useRef({ timer: null, long: false });
  const tipId = useId();
  const tipText = q.admin ? null : refreshTip(t, status, anonymous);
  const counting = isRefreshing && running && status?.progress_total > 0;
  const text = isRefreshing
    ? running
      ? t("header.refreshing", { done: status.progress_done, total: status.progress_total })
      : t("header.starting")
    : q.admin
    ? t("header.refresh")
    : q.exhausted
    ? resetText(t, q)
    : t("header.refreshLeft", { n: q.left });

  // Dokunmatik: uzun basış açıklamayı gösterir (yenileme başlatmaz); hak yokken dokunuş da gösterir.
  function onPointerDown(e) {
    if (e.pointerType !== "touch" || !tipText) return;
    press.current.long = false;
    press.current.timer = setTimeout(() => {
      press.current.long = true;
      setTip(true);
    }, 450);
  }
  function onPointerEnd() {
    clearTimeout(press.current.timer);
  }
  function onClick(e) {
    if (press.current.long) {
      press.current.long = false;
      e.preventDefault();
      setTimeout(() => setTip(false), 2500);
      return;
    }
    if (q.exhausted) {
      setTip(true);
      setTimeout(() => setTip(false), 3000);
      return;
    }
    onRefresh();
  }

  return (
    <span className="relative inline-flex" onMouseEnter={() => tipText && setTip(true)} onMouseLeave={() => setTip(false)}>
      <Button
        variant="primary"
        onClick={onClick}
        onPointerDown={onPointerDown}
        onPointerUp={onPointerEnd}
        onPointerCancel={onPointerEnd}
        onFocus={() => tipText && setTip(true)}
        onBlur={() => setTip(false)}
        disabled={isRefreshing}
        aria-disabled={q.exhausted || undefined}
        aria-label={compact ? text : undefined}
        aria-describedby={tipText ? tipId : undefined}
        className={cx("nav-text disabled:opacity-80", q.exhausted && "cursor-not-allowed opacity-60 hover:translate-y-0 hover:shadow-none", attn && !q.exhausted && "attn", compact && "px-3")}
      >
        <RefreshCw className={cx("h-4 w-4", isRefreshing && "animate-spin")} aria-hidden="true" />
        {compact ? (
          counting ? (
            <span className="font-mono text-micro tabular-nums">{status.progress_done}/{status.progress_total}</span>
          ) : (
            !q.admin && !q.exhausted && <span className="font-mono text-micro tabular-nums">{q.left}</span>
          )
        ) : (
          <span className="tabular-nums">{text}</span>
        )}
      </Button>
      {tipText && (
        <span
          id={tipId}
          role="tooltip"
          className={cx(
            "pointer-events-none absolute right-0 top-full z-50 mt-2 w-64 rounded-control bg-raised px-3 py-2 text-micro text-slate-300 shadow-raised ring-1 ring-ink-600 transition-opacity duration-hover ease-std",
            tip ? "opacity-100" : "sr-only opacity-0"
          )}
        >
          {tipText}
          {q.exhausted && <span className="mt-1 block text-slate-500">{resetText(t, q)}</span>}
        </span>
      )}
    </span>
  );
}

function initials(name) {
  return (name || "?").trim().slice(0, 1).toUpperCase();
}

function UserMenu({ user, view, onAdmin, onLogout }) {
  const { t } = useI18n();
  return (
    <Menu
      label={t("header.userMenu", { name: user.username })}
      button={({ open, toggle }) => (
        <button
          type="button"
          onClick={toggle}
          aria-haspopup="menu"
          aria-expanded={open}
          className="tap inline-flex h-10 items-center gap-2 rounded-full pl-1 pr-3 text-sm text-slate-300 transition-colors duration-hover ease-std hover:bg-ink-700 hover:text-slate-100"
        >
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-ink-700 font-display text-sm font-semibold text-slate-100" aria-hidden="true">
            {initials(user.username)}
          </span>
          <span className="nav-text max-w-36 truncate">{user.username}</span>
          {/* Erişilebilir ad görünen metinle başlar (label-content-name-mismatch olmasın). */}
          <span className="sr-only"> — {t("header.accountMenu")}</span>
        </button>
      )}
    >
      <div className="px-3 pb-2 pt-1.5">
        <div className="truncate text-sm font-semibold text-slate-100">{user.username}</div>
        {user.is_admin && <span className="mt-1 inline-block rounded-full bg-accent/10 px-2 py-0.5 text-micro font-medium text-accent">{t("header.roleAdmin")}</span>}
      </div>
      <div className="my-1 h-px bg-ink-600" />
      {user.is_admin && (
        <MenuItem icon={view === "admin" ? LayoutDashboard : ShieldCheck} onClick={onAdmin}>
          {view === "admin" ? t("header.backToDashboard") : t("header.adminPanel")}
        </MenuItem>
      )}
      <MenuItem icon={LogOut} onClick={onLogout}>
        {t("header.logout")}
      </MenuItem>
    </Menu>
  );
}

// Mobil tam ekran çekmece.
function Drawer({ user, view, lang, onLang, onClose, onHow, onAccount, onAdmin, onLogout }) {
  const { t } = useI18n();
  const act = (fn) => () => {
    onClose();
    fn();
  };
  return (
    <Modal full onClose={onClose} label={t("header.menu")}>
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between">
          <span className="font-display text-lg font-semibold text-slate-100">{user.is_anonymous ? t("header.guest") : user.username}</span>
          <Button variant="ghost" iconOnly icon={X} onClick={onClose} aria-label={t("common.close")} />
        </div>
        {user.is_admin && <span className="mt-1 inline-block self-start rounded-full bg-accent/10 px-2 py-0.5 text-micro font-medium text-accent">{t("header.roleAdmin")}</span>}
        <div className="mt-8 space-y-6">
          <div>
            <div className="mb-2 text-micro font-medium text-slate-500">{t("header.language")}</div>
            <LanguageSwitcher lang={lang} onChange={(l) => { onLang(l); onClose(); }} />
          </div>
          <ThemeSegmented />
          <div className="space-y-1">
            <MenuItem icon={HelpCircle} onClick={act(onHow)}>{t("header.howItWorks")}</MenuItem>
            {user.is_anonymous ? (
              <>
                <MenuItem icon={UserPlus} onClick={act(() => onAccount("upgrade"))}>{t("header.createAccount")}</MenuItem>
                <MenuItem icon={LogIn} onClick={act(() => onAccount("login"))}>{t("header.login")}</MenuItem>
              </>
            ) : (
              <>
                {user.is_admin && (
                  <MenuItem icon={view === "admin" ? LayoutDashboard : ShieldCheck} onClick={act(onAdmin)}>
                    {view === "admin" ? t("header.backToDashboard") : t("header.adminPanel")}
                  </MenuItem>
                )}
                <MenuItem icon={LogOut} onClick={act(onLogout)}>{t("header.logout")}</MenuItem>
              </>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}

export default function AppHeader({ user, view, lang, onLang, onHome, onAccount, onAdmin, onLogout, refresh, scan }) {
  const { t } = useI18n();
  const [drawer, setDrawer] = useState(false);
  // Görünüm değişince çekmece açık kalmasın.
  useEffect(() => setDrawer(false), [view]);
  const goHow = () => navigate("/#how-it-works");
  return (
    <NavBar
      brand={
        <Brand
          href="/app"
          onClick={(e) => {
            e.preventDefault();
            onHome();
          }}
        />
      }
      below={scan && <ScanProgress scan={scan} />}
    >
      <NavLink href="/#how-it-works" onClick={(e) => { e.preventDefault(); goHow(); }}>
        {t("header.howItWorks")}
      </NavLink>
      <div className="hidden items-center gap-2 md:flex lg:gap-2.5">
        <LanguageSwitcher lang={lang} onChange={onLang} />
        <ThemeMenu />
        {user.is_anonymous ? (
          <>
            <Button variant="ghost" onClick={() => onAccount("login")} className="nav-text">{t("header.login")}</Button>
            <Button onClick={() => onAccount("upgrade")} className="nav-text">{t("header.createAccount")}</Button>
          </>
        ) : (
          <UserMenu user={user} view={view} onAdmin={onAdmin} onLogout={onLogout} />
        )}
      </div>
      <div className="hidden md:block">
        <RefreshButton refresh={refresh} />
      </div>
      {/* Mobil */}
      <div className="flex items-center gap-2 md:hidden">
        <RefreshButton refresh={refresh} compact />
        <Button variant="ghost" iconOnly icon={MenuIcon} onClick={() => setDrawer(true)} aria-label={t("header.menu")} aria-haspopup="dialog" />
      </div>
      {drawer && (
        <Drawer
          user={user}
          view={view}
          lang={lang}
          onLang={onLang}
          onClose={() => setDrawer(false)}
          onHow={goHow}
          onAccount={onAccount}
          onAdmin={onAdmin}
          onLogout={onLogout}
        />
      )}
    </NavBar>
  );
}
