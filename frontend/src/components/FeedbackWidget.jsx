// "Geri bildirim": sağ altta küçük ikincil buton + ortak Modal. Herkese açık (anon da gönderebilir).
// Panel altında kurucu imzası + sosyal hesaplar.
import React, { useState } from "react";
import { MessageSquare, Send } from "lucide-react";
import { api } from "../api.js";
import { useVisualViewport } from "./ui.jsx";
import { useI18n } from "../i18n.jsx";
import { Button, Field, Input, Modal, ModalHeader, Textarea } from "./kit.jsx";
import { INSTAGRAM_URL, InstagramIcon, LINKEDIN_URL, LinkedInIcon, SocialIcon } from "./Social.jsx";

// Odaklanınca alanı görünür alanın ortasına kaydır (klavye açılınca kaybolmasın).
function scrollFocusIntoView(e) {
  const el = e.target;
  setTimeout(() => el.scrollIntoView({ block: "center", behavior: "smooth" }), 100);
}

// Kurucu imzası + sosyal hesaplar (panel altında ve boş butonun temsili).
function FounderSignature() {
  const { t } = useI18n();
  return (
    <div className="mt-6 flex items-center justify-between gap-3 border-t border-ink-600 pt-4">
      <div className="text-micro text-slate-500">
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

// open/onOpenChange: footer'daki "Geri bildirim" bağlantısı da açar. showButton: sağ alttaki
// küçük buton (detay sayfasında gizli — Ask AI ile çakışmasın).
export default function FeedbackWidget({ open, onOpenChange, showButton = true }) {
  const [message, setMessage] = useState("");
  const [contact, setContact] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(false);
  const { t } = useI18n();
  const vp = useVisualViewport(); // iOS klavyesi açılınca panel klavyenin üstünde kalsın

  function close() {
    onOpenChange(false);
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
      setTimeout(close, 1600); // teşekkürü göster, sonra kapat
    } catch (err) {
      setError(err.message || t("fb.fail"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {!open && showButton && (
        <Button
          size="sm"
          icon={MessageSquare}
          onClick={() => onOpenChange(true)}
          className="fixed bottom-4 right-4 z-40 bg-raised shadow-card md:bottom-6 md:right-6"
        >
          {t("fb.button")}
        </Button>
      )}

      {open && (
        <Modal onClose={close} labelledBy="fb-title" size="md" wrapperStyle={{ top: vp.offsetTop, height: vp.height }}>
          {sent ? (
            <div className="py-8 text-center" role="status">
              <span className="mx-auto mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-accent/10 text-accent">
                <MessageSquare className="h-5 w-5" aria-hidden="true" />
              </span>
              <p className="font-display text-title font-semibold text-slate-100">{t("fb.thanks")}</p>
            </div>
          ) : (
            <>
              <ModalHeader id="fb-title" title={t("fb.title")} onClose={close}>
                {t("fb.body")}
              </ModalHeader>
              <form onSubmit={submit} className="space-y-3">
                <Textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onFocus={scrollFocusIntoView}
                  rows={4}
                  maxLength={2000}
                  data-autofocus
                  placeholder={t("fb.placeholder")}
                  aria-label={t("fb.placeholder")}
                  className="resize-y"
                />
                <Field hint={t("fb.contactNote")}>
                  <Input
                    value={contact}
                    onChange={(e) => setContact(e.target.value)}
                    onFocus={scrollFocusIntoView}
                    maxLength={200}
                    placeholder={t("fb.contact")}
                    aria-label={t("fb.contact")}
                  />
                </Field>
                {error && <p className="text-meta text-rose-600" role="alert">{error}</p>}
                <Button type="submit" variant="primary" icon={Send} disabled={busy || !message.trim()} className="w-full">
                  {busy ? t("fb.sending") : t("fb.send")}
                </Button>
              </form>
            </>
          )}
          <FounderSignature />
        </Modal>
      )}
    </>
  );
}
