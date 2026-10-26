// Ortak bileşen kütüphanesi — landing ve uygulama AYNI parçaları kullanır.
// Renk/ölçek/yarıçap/gölge token'ları: index.css (+ tailwind.config.js), hareket: src/motion.js.
// İlkeler: az çizgi, az kutu — ayrım yüzey tonu, boşluk ve tipografiyle. Tek vurgu (camgöbeği)
// yalnızca birincil aksiyon ve aktif durumda. Odak halkası global (:focus-visible, index.css).
// İkon seti: lucide-react, varsayılan çizgi kalınlığı (2).
import React, { forwardRef, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, CheckCircle2, ChevronDown, Info, RotateCcw, X, XCircle } from "lucide-react";
import { useI18n } from "../i18n.jsx";
import { DUR, EASE_CSS, prefersReducedMotion } from "../motion.js";
import { useVisualViewport } from "./ui.jsx";

const cx = (...parts) => parts.filter(Boolean).join(" ");

// ── Button ──────────────────────────────────────────────────────────────────────
// primary: camgöbeği dolgulu · secondary: sade, ince kenarlı · ghost: yalnızca metin.
// Köşe 6px (--r-control), gölge yok: hover yalnızca yüzey/kenar tonunu değiştirir.
// iconOnly: kare ikon butonu (aria-label zorunlu). Aynı boyutta aynı yükseklik/yarıçap/hover.
const BTN_BASE =
  "inline-flex shrink-0 select-none items-center justify-center gap-2 whitespace-nowrap rounded-control font-medium " +
  "transition duration-hover ease-std disabled:pointer-events-none disabled:opacity-50";
const BTN_SIZE = { sm: "h-9 px-3.5 text-meta", md: "h-10 px-4 text-sm", lg: "h-14 px-7 text-lg font-semibold" };
const BTN_SQUARE = { sm: "h-9 w-9", md: "h-10 w-10", lg: "h-14 w-14" };
const BTN_VARIANT = {
  primary: "bg-signal font-semibold text-signal-fg hover:bg-signal/85 active:bg-signal/80",
  secondary: "text-slate-200 ring-1 ring-inset ring-ink-500 hover:bg-ink-700 hover:text-slate-100 hover:ring-slate-700",
  ghost: "text-slate-300 hover:bg-ink-700 hover:text-slate-100",
};

export const Button = forwardRef(function Button(
  { as: Tag = "button", variant = "secondary", size = "md", icon: Icon, iconOnly = false, className = "", children, type, ...rest },
  ref
) {
  return (
    <Tag
      ref={ref}
      type={Tag === "button" ? type || "button" : undefined}
      className={cx(BTN_BASE, iconOnly ? BTN_SQUARE[size] : BTN_SIZE[size], BTN_VARIANT[variant], "tap-sq", className)}
      {...rest}
    >
      {Icon && <Icon className={size === "lg" ? "h-5 w-5" : "h-4 w-4"} aria-hidden="true" />}
      {children}
    </Tag>
  );
});

// ── Chip / Badge ────────────────────────────────────────────────────────────────
// tone: anlamsal (pos/neg/warn) soluk dolgu + renkli metin; neutral/muted ikincil bilgi çipi.
// Durum etiketi (dolgulu, 5 kademe) ui.jsx'te StatusChip — renkleri aynı token'lardan.
const CHIP_TONE = {
  neutral: "bg-ink-700 text-slate-300",
  muted: "bg-ink-700 text-slate-500",
  pos: "bg-emerald-500/10 text-emerald-600",
  neg: "bg-rose-500/10 text-rose-600",
  warn: "bg-amber-500/10 text-amber-600",
  accent: "bg-accent/10 text-accent",
};
const CHIP_SIZE = { sm: "px-2.5 py-1 text-micro", md: "px-3 py-1 text-meta" };

// wrap: uzun metin satır kırar (ör. ana etkenler); varsayılan tek satır.
export function Chip({ tone = "neutral", size = "sm", icon: Icon, wrap = false, className = "", children, ...rest }) {
  return (
    <span
      className={cx("inline-flex items-center gap-1.5 font-medium", wrap ? "rounded-control text-left" : "whitespace-nowrap rounded-control", CHIP_SIZE[size], CHIP_TONE[tone], className)}
      {...rest}
    >
      {Icon && <Icon className="h-3.5 w-3.5" aria-hidden="true" />}
      {children}
    </span>
  );
}

// Tıklanabilir ikincil çip (öneri, örnek soru): ince kenarlı, hover'da yüzey tonu.
export const ChipButton = forwardRef(function ChipButton({ icon: Icon, className = "", children, type, ...rest }, ref) {
  return (
    <button
      ref={ref}
      type={type || "button"}
      className={cx(
        "tap inline-flex min-h-9 items-center gap-1.5 rounded-control px-3 py-1.5 text-left text-meta font-medium text-slate-200 ring-1 ring-inset ring-ink-500",
        "transition duration-hover ease-std hover:bg-ink-700 hover:text-slate-100 hover:ring-slate-700 disabled:opacity-50",
        className
      )}
      {...rest}
    >
      {Icon && <Icon className="h-3.5 w-3.5 text-accent" aria-hidden="true" />}
      {children}
    </button>
  );
});

// Haber etiketleri (olumlu / olumsuz / nötr / alakasız) — uygulama ve landing aynı.
export const LABEL_TONE = { positive: "pos", negative: "neg", neutral: "muted", irrelevant: "muted" };
export function LabelChip({ label, t, size = "sm", className = "", style }) {
  return (
    <Chip tone={LABEL_TONE[label] || "muted"} size={size} className={cx("shrink-0", className)} style={style}>
      {t(`hiw.label.${label}`)}
    </Chip>
  );
}

// ── Card ────────────────────────────────────────────────────────────────────────
// Kart: 1px ince kenar + yüzey tonu, gölge yok. interactive: hover'da kenar koyulaşır (yükselme yok).
export const Card = forwardRef(function Card({ as: Tag = "div", interactive = false, className = "", children, ...rest }, ref) {
  return (
    <Tag
      ref={ref}
      className={cx(
        "rounded-card bg-ink-800 ring-1 ring-inset ring-ink-600",
        interactive && "cursor-pointer transition-colors duration-hover ease-std hover:ring-slate-700",
        className
      )}
      {...rest}
    >
      {children}
    </Tag>
  );
});

// ── Form denetimleri ────────────────────────────────────────────────────────────
const CONTROL =
  "w-full rounded-control bg-ink-900 text-body text-slate-100 ring-1 ring-inset ring-ink-500 placeholder:text-slate-600 " +
  "transition duration-hover ease-std hover:ring-slate-700 focus:outline-none focus:ring-2 focus:ring-accent disabled:opacity-60";

export const Input = forwardRef(function Input({ className = "", mono = false, ...rest }, ref) {
  return <input ref={ref} className={cx(CONTROL, "h-10 px-3", mono && "font-mono", className)} {...rest} />;
});

export const Textarea = forwardRef(function Textarea({ className = "", ...rest }, ref) {
  return <textarea ref={ref} className={cx(CONTROL, "px-3 py-2.5 leading-relaxed", className)} {...rest} />;
});

export const Select = forwardRef(function Select({ className = "", wrapClassName = "", children, ...rest }, ref) {
  return (
    <span className={cx("relative block", wrapClassName)}>
      <select ref={ref} className={cx(CONTROL, "h-10 cursor-pointer appearance-none pl-3 pr-9", className)} {...rest}>
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" aria-hidden="true" />
    </span>
  );
});

export function Field({ label, htmlFor, hint, className = "", children }) {
  return (
    <div className={className}>
      {label && (
        <label htmlFor={htmlFor} className="mb-1.5 block text-micro font-medium text-slate-500">
          {label}
        </label>
      )}
      {children}
      {hint && <p className="mt-1.5 text-micro text-slate-500">{hint}</p>}
    </div>
  );
}

// ── Tabs ────────────────────────────────────────────────────────────────────────
// underline: sayfa sekmeleri (aktifte vurgu renginde ince alt çizgi) · pill: küçük seçim (ör. sıralama).
// Klavye: ←/→ ile gezinme (roving tabindex).
export function Tabs({ items, value, onChange, variant = "underline", label, className = "" }) {
  const refs = useRef([]);
  function onKey(e, i) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    // Pasif (disabled) öğeler atlanır.
    let n = i;
    for (let k = 0; k < items.length; k++) {
      n = (n + (e.key === "ArrowRight" ? 1 : -1) + items.length) % items.length;
      if (!items[n].disabled) break;
    }
    onChange(items[n].key);
    refs.current[n]?.focus();
  }
  const underline = variant === "underline";
  return (
    <div role="tablist" aria-label={label} className={cx("flex", underline ? "gap-1 border-b border-ink-600" : "gap-0.5 rounded-control bg-ink-800 p-1 ring-1 ring-inset ring-ink-600", className)}>
      {items.map((it, i) => {
        const on = it.key === value;
        const Icon = it.icon;
        return (
          <button
            key={it.key}
            ref={(el) => (refs.current[i] = el)}
            type="button"
            role="tab"
            aria-selected={on}
            tabIndex={on ? 0 : -1}
            onClick={() => !it.disabled && onChange(it.key)}
            onKeyDown={(e) => onKey(e, i)}
            disabled={it.disabled}
            aria-disabled={it.disabled || undefined}
            className={
              underline
                ? cx(
                    "tap relative -mb-px inline-flex h-11 items-center gap-2 whitespace-nowrap px-2.5 text-sm font-medium transition-colors duration-hover ease-std sm:px-3",
                    "after:absolute after:inset-x-2.5 after:bottom-0 sm:after:inset-x-3 after:h-0.5 after:bg-accent after:transition-transform after:duration-hover",
                    on ? "text-slate-100 after:scale-x-100" : "text-slate-500 after:scale-x-0 hover:text-slate-200"
                  )
                : cx(
                    "tap inline-flex h-8 items-center whitespace-nowrap rounded-[4px] px-3 text-meta font-medium transition-colors duration-hover ease-std",
                    on ? "bg-ink-700 text-slate-100" : "text-slate-500 hover:text-slate-200",
                    "disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-slate-500"
                  )
            }
          >
            {Icon && <Icon className="hidden h-4 w-4 sm:block" aria-hidden="true" />}
            {it.label}
          </button>
        );
      })}
    </div>
  );
}

// ── Modal ───────────────────────────────────────────────────────────────────────
// Yükseltilmiş yüzey, ince kenar (gölge yok), düz karartma; açılış 200ms (ölçek + fade).
// Esc kapatır, odak modalda hapsolur, kapanınca odak açan öğeye döner. Mobilde alttan çıkar.
const MODAL_SIZE = { sm: "sm:max-w-sm", md: "sm:max-w-md", lg: "sm:max-w-lg", xl: "sm:max-w-2xl" };
const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

// drawer: sağdan kayan yan çekmece (mobil menü) — dışarı dokununca kapanır, güvenli alanlara uyar.
// Klavye: sarmalayıcı GÖRÜNÜR alana (visualViewport) oturur → iOS'ta klavye açılınca modal ve
// içindeki input klavyenin üstünde kalır; içerik --vvh ile kendi yüksekliğini sınırlayabilir.
export function Modal({ onClose, labelledBy, label, size = "md", drawer = false, dismissable = true, className = "", wrapperStyle, children }) {
  const panel = useRef(null);
  const vp = useVisualViewport();
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const prev = document.activeElement;
    const el = panel.current;
    const focusables = () => [...el.querySelectorAll(FOCUSABLE)].filter((n) => n.offsetParent !== null);
    (el.querySelector("[data-autofocus]") || focusables()[0] || el).focus({ preventScroll: true });
    const onKey = (e) => {
      if (e.key === "Escape" && dismissable) {
        e.stopPropagation();
        closeRef.current?.();
      } else if (e.key === "Tab") {
        const f = focusables();
        if (!f.length) return e.preventDefault();
        const first = f[0];
        const last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey, true);
    // Arka plan kaydırma kilidi (iOS Safari için <html> de).
    const overflow = document.body.style.overflow;
    const htmlOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.body.style.overflow = overflow;
      document.documentElement.style.overflow = htmlOverflow;
      if (prev && document.contains(prev)) prev.focus?.({ preventScroll: true });
    };
  }, [dismissable]);
  return createPortal(
    <div className={cx("fixed inset-0 z-50 flex", drawer ? "items-stretch justify-end" : "items-end justify-center sm:items-center sm:p-4")} style={drawer ? wrapperStyle : { top: vp.offsetTop, height: vp.height, "--vvh": `${vp.height}px`, ...wrapperStyle }}>
      <div className="fade-in absolute inset-0 bg-black/50" aria-hidden="true" onMouseDown={() => dismissable && closeRef.current?.()} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-label={labelledBy ? undefined : label}
        tabIndex={-1}
        className={cx(
          "relative overflow-y-auto overscroll-contain bg-raised focus:outline-none",
          drawer
            ? "drawer-in flex h-full w-80 max-w-[88vw] flex-col pl-6 pr-[max(1.5rem,env(safe-area-inset-right))] pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-[max(1.25rem,env(safe-area-inset-top))] border-l border-ink-600"
            : "modal-in max-h-full w-full rounded-t-panel p-6 pb-[max(1.5rem,env(safe-area-inset-bottom))] ring-1 ring-ink-600 sm:max-h-[92dvh] sm:rounded-panel sm:pb-6",
          !drawer && MODAL_SIZE[size],
          className
        )}
      >
        {children}
      </div>
    </div>,
    document.body
  );
}

export function ModalHeader({ id, title, icon: Icon, onClose, children }) {
  const { t } = useI18n();
  return (
    <div className="mb-4 flex items-start gap-3">
      <div className="min-w-0 flex-1">
        <h2 id={id} className="flex items-center gap-2 font-display text-title font-semibold text-slate-100">
          {Icon && <Icon className="h-5 w-5 shrink-0 text-accent" aria-hidden="true" />}
          {title}
        </h2>
        {children && <div className="mt-1.5 text-meta leading-relaxed text-slate-400">{children}</div>}
      </div>
      {onClose && <Button variant="ghost" size="sm" iconOnly icon={X} onClick={onClose} aria-label={t("common.close")} className="-mr-2 -mt-1" />}
    </div>
  );
}

// ── Toast / Banner ─────────────────────────────────────────────────────────────
// Anlamsal renkli ince sol kenar + ikon; yükseltilmiş yüzey. inline: sayfa içi banner.
const TOAST_TONE = {
  ok: { bar: "bg-emerald-500", Icon: CheckCircle2, icon: "text-emerald-600" },
  warn: { bar: "bg-amber-500", Icon: AlertTriangle, icon: "text-amber-600" },
  error: { bar: "bg-rose-500", Icon: XCircle, icon: "text-rose-600" },
  info: { bar: "bg-slate-500", Icon: Info, icon: "text-slate-400" },
};

export function Toast({ tone = "info", title, onClose, inline = false, className = "", children }) {
  const { t } = useI18n();
  const st = TOAST_TONE[tone] || TOAST_TONE.info;
  return (
    <div
      role={tone === "error" || tone === "warn" ? "alert" : "status"}
      className={cx(
        "relative flex w-full gap-3 overflow-hidden rounded-control py-3 pl-4 pr-3 text-meta text-slate-300",
        inline ? "bg-ink-800 ring-1 ring-ink-600" : "toast-in pointer-events-auto bg-raised ring-1 ring-ink-500",
        className
      )}
    >
      <span className={cx("absolute inset-y-0 left-0 w-0.5", st.bar)} aria-hidden="true" />
      <st.Icon className={cx("mt-0.5 h-4 w-4 shrink-0", st.icon)} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        {title && <div className="font-medium text-slate-100">{title}</div>}
        {children}
      </div>
      {onClose && <Button variant="ghost" size="sm" iconOnly icon={X} onClick={onClose} aria-label={t("common.close")} className="-my-1.5" />}
    </div>
  );
}

// Toast yığını. Masaüstü: SOL ALT — sağ sütun Ask AI paneli, sağ alt köşe Geri bildirim /
// Ask AI butonlarıyla dolu (sağ üstteyken panelin hazır sorularını kapatıyordu). Mobil: altta,
// güvenli alanın (ev çubuğu / Safari adres çubuğu) ve sağ alttaki yüzen butonların üstünde.
// flex-col-reverse: en yeni bildirim en altta, gözün ilk düştüğü yerde.
export function ToastStack({ children }) {
  return (
    <div className="pointer-events-none fixed inset-x-4 bottom-[calc(env(safe-area-inset-bottom)+8.5rem)] z-[60] flex flex-col-reverse gap-2 sm:bottom-6 sm:left-6 sm:right-auto sm:w-96">
      {children}
    </div>
  );
}

// ── Durumlar ────────────────────────────────────────────────────────────────────
export function Skeleton({ className = "" }) {
  return <div className={cx("skeleton", className)} aria-hidden="true" />;
}

export function EmptyState({ icon: Icon, title, body, className = "", children }) {
  return (
    <div className={cx("flex flex-col items-center px-6 py-12 text-center", className)}>
      {Icon && (
        <span className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-control bg-ink-800 text-accent ring-1 ring-ink-600">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
      )}
      <h2 className="font-display text-title font-semibold text-slate-100">{title}</h2>
      {body && <p className="mt-2 max-w-md text-body text-slate-400">{body}</p>}
      {children && <div className="mt-6 w-full">{children}</div>}
    </div>
  );
}

// Sakin hata kartı: tek cümle + "Tekrar dene". Teknik ayrıntı yalnızca verilirse (admin).
export function ErrorState({ message, detail, onRetry, className = "" }) {
  const { t } = useI18n();
  return (
    <Card className={cx("flex flex-col items-start gap-4 p-6 sm:flex-row sm:items-center", className)} role="alert">
      <AlertTriangle className="h-5 w-5 shrink-0 text-rose-600" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-body text-slate-200">{message || t("state.errorBody")}</p>
        {detail && <p className="mt-1 break-words font-mono text-micro text-slate-500">{detail}</p>}
      </div>
      {onRetry && (
        <Button icon={RotateCcw} onClick={onRetry}>
          {t("state.retry")}
        </Button>
      )}
    </Card>
  );
}

// ── Menü (açılır) ──────────────────────────────────────────────────────────────
// button({ open, toggle }) tetikleyiciyi çizer. Esc/dış tık kapatır; açılınca ilk öğeye odak.
export function Menu({ button, label, align = "right", className = "", children }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") {
        setOpen(false);
        wrap.current?.querySelector("[aria-haspopup]")?.focus();
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        const items = [...wrap.current.querySelectorAll('[role^="menuitem"]')];
        if (!items.length) return;
        e.preventDefault();
        const i = items.indexOf(document.activeElement);
        items[(i + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length].focus();
      }
    };
    const onDown = (e) => wrap.current && !wrap.current.contains(e.target) && setOpen(false);
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onDown);
    (wrap.current?.querySelector('[role^="menuitem"][aria-checked="true"]') || wrap.current?.querySelector('[role^="menuitem"]'))?.focus();
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onDown);
    };
  }, [open]);
  return (
    <div ref={wrap} className="relative">
      {button({ open, toggle: () => setOpen((o) => !o) })}
      {open && (
        <div
          role="menu"
          aria-label={label}
          onClick={(e) => e.target.closest("[data-close]") && setOpen(false)}
          className={cx(
            "fade-in absolute top-full z-40 mt-2 min-w-48 rounded-control bg-raised p-1.5 ring-1 ring-ink-500",
            align === "right" ? "right-0" : "left-0",
            className
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}

// tone="danger": yıkıcı aksiyon (çıkış) — soluk kırmızı, bağırmayan.
// plain: menü dışında (ör. mobil çekmece) düz düğme — role="menuitem" yalnızca role="menu" içinde geçerli.
export function MenuItem({ icon: Icon, tone, className = "", plain = false, children, ...rest }) {
  return (
    <button
      type="button"
      role={plain ? undefined : "menuitem"}
      data-close
      className={cx(
        "tap flex h-10 w-full items-center gap-2.5 rounded-lg px-3 text-left text-sm transition-colors duration-hover ease-std hover:bg-ink-700",
        tone === "danger" ? "text-rose-600/90 hover:text-rose-600" : "text-slate-300 hover:text-slate-100",
        className
      )}
      {...rest}
    >
      {Icon && <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />}
      {children}
    </button>
  );
}

// Onay penceresi (window.confirm yerine): ortak Modal + birincil/ikincil buton.
export function ConfirmDialog({ title, body, confirmLabel, cancelLabel, onConfirm, onCancel }) {
  return (
    <Modal onClose={onCancel} labelledBy="confirm-title" size="sm">
      <ModalHeader id="confirm-title" title={title} onClose={onCancel}>
        {body}
      </ModalHeader>
      <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button onClick={onCancel}>{cancelLabel}</Button>
        <Button variant="primary" onClick={onConfirm} data-autofocus>
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}

// Liste sırası değişince öğeler yumuşakça yer değiştirsin (FLIP). Çocuklar data-key taşır.
// Konumlar listeye göre (offsetTop) — sayfa kaydırması animasyon tetiklemez. reduced-motion: yok.
export function useFlip(ref, deps) {
  const prev = useRef(new Map());
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const items = [...el.children].filter((n) => n.dataset.key);
    const next = new Map(items.map((n) => [n.dataset.key, n.offsetTop]));
    if (!prefersReducedMotion() && prev.current.size) {
      items.forEach((n) => {
        const before = prev.current.get(n.dataset.key);
        const after = next.get(n.dataset.key);
        if (before != null && before !== after) {
          n.animate([{ transform: `translateY(${before - after}px)` }, { transform: "none" }], { duration: DUR.move * 1000, easing: EASE_CSS });
        }
      });
    }
    prev.current = next;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export { cx };
