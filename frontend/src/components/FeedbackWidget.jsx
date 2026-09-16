// Sağ altta sabit "Geri bildirim" butonu + panel. Herkese açık (anon da gönderebilir).
// Panel altında kurucu imzası + sosyal hesaplar. Sıcak kağıt teması, lacivert vurgu, sans.
import React, { useState } from "react";
import { MessageSquare, X, Send } from "lucide-react";
import { api } from "../api.js";
import { useVisualViewport } from "./ui.jsx";
import { useI18n } from "../i18n.jsx";

// Odaklanınca alanı görünür alanın ortasına kaydır (klavye açılınca kaybolmasın).
function scrollFocusIntoView(e) {
  const el = e.target;
  setTimeout(() => el.scrollIntoView({ block: "center", behavior: "smooth" }), 100);
}

// Marka ikonları (lucide bu sürümde brand glyph'lerini içermiyor) — küçük inline SVG.
function LinkedInIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4" aria-hidden="true">
      <path d="M4.98 3.5C4.98 4.88 3.87 6 2.5 6S0 4.88 0 3.5 1.12 1 2.5 1s2.48 1.12 2.48 2.5zM.24 8h4.52v14.5H.24V8zM8.24 8h4.33v1.98h.06c.6-1.14 2.07-2.34 4.26-2.34 4.56 0 5.4 3 5.4 6.9v8.96h-4.52v-7.94c0-1.9-.03-4.34-2.64-4.34-2.64 0-3.05 2.06-3.05 4.2v8.08H8.24V8z" />
    </svg>
  );
}
function InstagramIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4" aria-hidden="true">
      <rect x="2" y="2" width="20" height="20" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

// ── DEĞİŞTİR (Sarp): kendi hesap adreslerinle güncelle ──────────────────────
// Bu iki sabit tek düzenleme noktasıdır; başka yeri değiştirmen gerekmez.
const LINKEDIN_URL = "https://www.linkedin.com/in/sarp-b%C4%B1%C3%A7ak-b5607037b/";
const INSTAGRAM_URL = "https://www.instagram.com/sarpbicak24/";
// ────────────────────────────────────────────────────────────────────────────

function SocialIcon({ href, label, children }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      aria-label={label}
      title={label}
      className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-ink-500 text-slate-500 transition hover:border-accent/60 hover:text-accent"
    >
      {children}
    </a>
  );
}

// Kurucu imzası + sosyal hesaplar (panel altında ve boş butonun temsili).
function FounderSignature() {
  const { t } = useI18n();
  return (
    <div className="mt-5 flex items-center justify-between gap-3 border-t border-ink-600 pt-4">
      <div className="text-xs text-slate-500">
        {t("fb.builtBy", { name: "Sarp Bıçak" })}
      </div>
      <div className="flex items-center gap-2">
        <SocialIcon href={LINKEDIN_URL} label="LinkedIn">
          <LinkedInIcon />
        </SocialIcon>
        <SocialIcon href={INSTAGRAM_URL} label="Instagram">
          <InstagramIcon />
        </SocialIcon>
      </div>
    </div>
  );
}

export default function FeedbackWidget({ raised = false }) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [contact, setContact] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(false);
  const { t } = useI18n();
  const vp = useVisualViewport(); // iOS klavyesi açılınca panel klavyenin üstünde kalsın

  function close() {
    setOpen(false);
    // Kapanış animasyonu yok; durumu bir sonraki açılış için sıfırla.
    setTimeout(() => {
      setSent(false);
      setError(null);
    }, 200);
  }

  async function submit(e) {
    e.preventDefault();
    const msg = message.trim();
    if (!msg || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.sendFeedback(msg, contact.trim() || null);
      setSent(true);
      setMessage("");
      setContact("");
      // Teşekkür mesajını göster, sonra paneli kapat.
      setTimeout(close, 1600);
    } catch (err) {
      setError(err.message || t("fb.fail"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {/* Sağ altta sabit buton — mobilde alt sekme çubuğu varken yukarı kalkar */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className={`fixed right-4 z-40 inline-flex min-h-[44px] items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-4 text-sm font-medium text-accent shadow-card backdrop-blur-sm transition hover:bg-accent/20 md:right-6 ${
            raised ? "bottom-[68px] md:bottom-6" : "bottom-4 md:bottom-6"
          }`}
          aria-label={t("fb.button")}
        >
          <MessageSquare className="h-4 w-4" />
          {t("fb.button")}
        </button>
      )}

      {open && (
        <div
          className="fixed inset-x-0 z-50 flex items-end justify-center bg-black/30 p-4 backdrop-blur-sm sm:items-center"
          style={{ top: vp.offsetTop, height: vp.height }}
          onClick={close}
        >
          <div
            className="relative flex max-h-full w-full max-w-md flex-col overflow-y-auto overscroll-contain rounded-2xl border border-ink-600 bg-ink-800 p-6 pb-[max(1.5rem,env(safe-area-inset-bottom))] shadow-card-hover"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={close}
              aria-label={t("common.close")}
              className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
            >
              <X className="h-4 w-4" />
            </button>

            {sent ? (
              <div className="py-6 text-center">
                <div className="mx-auto mb-3 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-accent/15 text-accent">
                  <MessageSquare className="h-6 w-6" />
                </div>
                <p className="font-display text-lg font-semibold text-slate-100">
                  {t("fb.thanks")}
                </p>
              </div>
            ) : (
              <>
                <h2 className="mb-1.5 pr-8 font-display text-lg font-bold text-slate-100">
                  {t("fb.title")}
                </h2>
                <p className="text-[13px] leading-relaxed text-slate-400">
                  {t("fb.body")}
                </p>

                <form onSubmit={submit} className="mt-4 space-y-3">
                  {/* text-base (16px) → iOS odak-zoom'unu engeller (font <16 zoom yapar) */}
                  <textarea
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onFocus={scrollFocusIntoView}
                    rows={4}
                    maxLength={2000}
                    autoFocus
                    placeholder={t("fb.placeholder")}
                    className="w-full resize-y rounded-lg border border-ink-500 bg-ink-900 px-3 py-2 text-base leading-relaxed text-slate-200 outline-none transition focus:border-accent"
                  />
                  <div>
                    <input
                      value={contact}
                      onChange={(e) => setContact(e.target.value)}
                      onFocus={scrollFocusIntoView}
                      maxLength={200}
                      placeholder={t("fb.contact")}
                      className="min-h-[44px] w-full rounded-lg border border-ink-500 bg-ink-900 px-3 py-2 text-base text-slate-200 outline-none transition focus:border-accent"
                    />
                    <p className="mt-1 text-[11px] text-slate-500">
                      {t("fb.contactNote")}
                    </p>
                  </div>

                  {error && <p className="text-xs text-rose-400">{error}</p>}

                  <button
                    type="submit"
                    disabled={busy || !message.trim()}
                    className="inline-flex min-h-[44px] w-full items-center justify-center gap-2 rounded-lg bg-accent px-4 text-sm font-medium text-white transition hover:brightness-105 disabled:opacity-50"
                  >
                    <Send className="h-4 w-4" />
                    {busy ? t("fb.sending") : t("fb.send")}
                  </button>
                </form>
              </>
            )}

            <FounderSignature />
          </div>
        </div>
      )}
    </>
  );
}
