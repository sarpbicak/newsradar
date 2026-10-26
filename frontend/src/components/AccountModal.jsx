// Hesap modalı: anonim oturumu KALICI hesaba çevir (upgrade: kullanıcı adı + e-posta + şifre),
// mevcut hesaba GİRİŞ (kullanıcı adı ya da e-posta), eski hesaba E-POSTA EKLE ("email"),
// ŞİFREMİ UNUTTUM ("forgot") ya da e-postayı DOĞRULA / tekrar gönder ("verify").
// "forgot" ve "verify" yalnızca e-posta gönderimi açıkken (emailEnabled) sunulur.
// Genel şifre kapısı YOK — site herkese açık.
import React, { useEffect, useState } from "react";
import { KeyRound, LogIn, Mail, MailCheck, UserPlus } from "lucide-react";
import { forgotPassword, resendVerification, setEmail, upgradeAccount, userLogin } from "../api.js";
import { addStrings, useI18n } from "../i18n.jsx";
import { Button, Field, Input, Modal, ModalHeader } from "./kit.jsx";

// Şifremi unuttum / doğrulama metinleri — uygulama paketinde (landing'de değil).
addStrings({
  "acc.forgot": { tr: "Şifremi unuttum", en: "Forgot password?" },
  "acc.forgotTitle": { tr: "Şifreni sıfırla", en: "Reset your password" },
  "acc.forgotBody": { tr: "Hesabındaki e-posta adresini yaz; şifre sıfırlama bağlantısı gönderelim.", en: "Enter your account's email address and we'll send a password reset link." },
  "acc.forgotSubmit": { tr: "Bağlantı gönder", en: "Send link" },
  "acc.forgotSent": { tr: "Bu adres kayıtlıysa şifre sıfırlama bağlantısı gönderdik. Gelen kutunu (ve gereksiz klasörünü) kontrol et; bağlantı 1 saat geçerli.", en: "If this address is registered, we've sent a password reset link. Check your inbox (and spam folder); the link is valid for 1 hour." },
  "acc.backToLogin": { tr: "Girişe dön", en: "Back to sign in" },
  "acc.tooMany": { tr: "Çok fazla istek. Biraz sonra tekrar dene.", en: "Too many requests. Try again a bit later." },
  "acc.verifyTitle": { tr: "E-postanı doğrula", en: "Verify your email" },
  "acc.verifyBody": { tr: "{email} adresine bir doğrulama bağlantısı gönderdik. Hesabını kullanmaya devam edebilirsin; doğrulama şifreni unutursan sıfırlayabilmen için.", en: "We sent a verification link to {email}. You can keep using your account; verifying lets you reset your password if you forget it." },
  "acc.verifySent": { tr: "Yeni bağlantı gönderildi.", en: "A new link is on its way." },
  "acc.resend": { tr: "Tekrar gönder", en: "Send again" },
  "acc.resendIn": { tr: "Tekrar gönder ({s} sn)", en: "Send again ({s}s)" },
});

// Sunucuyla aynı gevşek biçim denetimi (tek @, noktalı alan adı, boşluk yok).
const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]+\.[^@\s.]{2,}$/;

// "Tekrar gönder" bekleme süresi (sn): sunucu 429 + Retry-After ile de söyler.
const RESEND_COOLDOWN = 60;

export default function AccountModal({ mode: initialMode, onClose, onDone, user, emailEnabled = false }) {
  const { t } = useI18n();
  const [mode, setMode] = useState(["login", "email", "forgot", "verify"].includes(initialMode) ? initialMode : "upgrade");
  const [username, setUsername] = useState("");
  const [email, setEmailValue] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const isUpgrade = mode === "upgrade";
  const isEmail = mode === "email";
  const [sent, setSent] = useState(false); // forgot: genel "gönderdik" mesajı
  const [cooldown, setCooldown] = useState(0);
  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const id = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(id);
  }, [cooldown]);

  async function resend() {
    if (busy || cooldown > 0) return;
    setBusy(true);
    setErr(null);
    try {
      await resendVerification();
      setSent(true);
      setCooldown(RESEND_COOLDOWN);
    } catch (e2) {
      if (e2.status === 429) setCooldown(e2.retryAfter || RESEND_COOLDOWN);
      else setErr(e2.message);
    } finally {
      setBusy(false);
    }
  }

  if (mode === "verify") {
    return (
      <Modal onClose={onClose} labelledBy="acc-title" size="sm">
        <ModalHeader id="acc-title" title={t("acc.verifyTitle")} icon={MailCheck} onClose={onClose}>
          {t("acc.verifyBody", { email: user?.email || "" })}
        </ModalHeader>
        {sent && <p className="mb-3 text-meta text-emerald-600" role="status">{t("acc.verifySent")}</p>}
        {err && <p className="mb-3 text-meta text-rose-600" role="alert">{err}</p>}
        <Button variant="primary" onClick={resend} disabled={busy || cooldown > 0} className="w-full">
          {cooldown > 0 ? t("acc.resendIn", { s: cooldown }) : t("acc.resend")}
        </Button>
      </Modal>
    );
  }

  if (mode === "forgot") {
    const submitForgot = async (e) => {
      e.preventDefault();
      if (busy) return;
      if (!EMAIL_RE.test(email.trim())) {
        setErr(t("acc.emailInvalid"));
        return;
      }
      setBusy(true);
      setErr(null);
      try {
        await forgotPassword(email.trim());
        setSent(true); // adres kayıtlı olsun olmasın aynı mesaj (hesap varlığı sızmaz)
      } catch (e2) {
        setErr(e2.status === 429 ? t("acc.tooMany") : e2.message);
      } finally {
        setBusy(false);
      }
    };
    return (
      <Modal onClose={onClose} labelledBy="acc-title" size="sm">
        <ModalHeader id="acc-title" title={t("acc.forgotTitle")} icon={KeyRound} onClose={onClose}>
          {sent ? t("acc.forgotSent") : t("acc.forgotBody")}
        </ModalHeader>
        {!sent && (
          <form onSubmit={submitForgot} className="space-y-3" noValidate>
            <Field label={t("acc.email")} htmlFor="acc-email">
              <Input id="acc-email" type="email" inputMode="email" value={email} onChange={(e) => setEmailValue(e.target.value)} autoComplete="email" data-autofocus required />
            </Field>
            {err && <p className="text-meta text-rose-600" role="alert">{err}</p>}
            <Button type="submit" variant="primary" disabled={busy} className="w-full">
              {busy ? t("acc.working") : t("acc.forgotSubmit")}
            </Button>
          </form>
        )}
        <div className="mt-4 text-center">
          <Button variant="ghost" size="sm" onClick={() => { setErr(null); setSent(false); setMode("login"); }}>
            {t("acc.backToLogin")}
          </Button>
        </div>
      </Modal>
    );
  }

  async function submit(e) {
    e.preventDefault();
    if (busy) return;
    if (!isEmail && (!username.trim() || !password)) return;
    if ((isUpgrade || isEmail) && !EMAIL_RE.test(email.trim())) {
      setErr(t("acc.emailInvalid"));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const u = isEmail
        ? await setEmail(email.trim())
        : isUpgrade
        ? await upgradeAccount(username.trim(), password, email.trim())
        : await userLogin(username.trim(), password);
      onDone(u);
    } catch (e2) {
      // Sunucu hataları kodlu gelir; api.js mesajı zaten kullanıcının dilinde verir.
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  }

  const title = isEmail ? t("acc.emailTitle") : isUpgrade ? t("acc.upgradeTitle") : t("acc.loginTitle");
  const icon = isEmail ? Mail : isUpgrade ? UserPlus : LogIn;

  return (
    <Modal onClose={onClose} labelledBy="acc-title" size="sm">
      <ModalHeader id="acc-title" title={title} icon={icon} onClose={onClose}>
        {isEmail ? t("acc.emailBody") : isUpgrade ? t("acc.upgradeBody") : t("acc.loginBody")}
      </ModalHeader>
      <form onSubmit={submit} className="space-y-3" noValidate>
        {!isEmail && (
          <Field label={isUpgrade ? t("acc.username") : t("acc.usernameOrEmail")} htmlFor="acc-user">
            <Input id="acc-user" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" data-autofocus required />
          </Field>
        )}
        {(isUpgrade || isEmail) && (
          <Field label={t("acc.email")} htmlFor="acc-email" hint={t("acc.emailHint")}>
            <Input
              id="acc-email"
              type="email"
              inputMode="email"
              value={email}
              onChange={(e) => setEmailValue(e.target.value)}
              autoComplete="email"
              required
              {...(isEmail ? { "data-autofocus": true } : {})}
            />
          </Field>
        )}
        {!isEmail && (
        <Field label={t("acc.password")} htmlFor="acc-pass">
          <Input
            id="acc-pass"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            autoComplete={isUpgrade ? "new-password" : "current-password"}
          />
        </Field>
        )}
        {mode === "login" && emailEnabled && (
          <div className="-mt-1 text-right">
            <button type="button" onClick={() => { setErr(null); setMode("forgot"); }} className="text-micro text-slate-400 underline-offset-2 hover:text-slate-200 hover:underline">
              {t("acc.forgot")}
            </button>
          </div>
        )}
        {err && <p className="text-meta text-rose-600" role="alert">{err}</p>}
        <Button type="submit" variant="primary" disabled={busy} className="w-full">
          {busy ? t("acc.working") : isEmail ? t("acc.emailSave") : isUpgrade ? t("acc.submitUpgrade") : t("acc.submitLogin")}
        </Button>
      </form>
      {!isEmail && (
      <div className="mt-4 text-center">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setErr(null);
            setMode(isUpgrade ? "login" : "upgrade");
          }}
        >
          {isUpgrade ? t("acc.toLogin") : t("acc.toUpgrade")}
        </Button>
      </div>
      )}
    </Modal>
  );
}
