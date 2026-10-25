// E-postadaki bağlantıların sayfası: /verify-email?token=… ve /reset-password?token=…
// Oturum gerekmez (bağlantı başka cihazda açılabilir). Token okununca adres çubuğundan silinir
// (geçmişe / Referer'a düşmesin). Doğrulama isteği tek sefer gider (StrictMode çift efekti token'ı
// harcayıp "geçersiz" göstermesin).
import React, { useEffect, useRef, useState } from "react";
import { CheckCircle2, LockKeyhole, XCircle } from "lucide-react"; // App ile paylaşılmayan simgeler
import { resetPassword, verifyEmail } from "../api.js";
import { addStrings, useI18n } from "../i18n.jsx";
import { navigate } from "../router.js";
import { Button, Card, Field, Input } from "./kit.jsx";

// Bağlantı sayfası metinleri — yalnızca bu (tembel) pakette.
addStrings({
  "link.toApp": { tr: "NewsRadar'a git", en: "Go to NewsRadar" },
  "link.checking": { tr: "Bağlantı kontrol ediliyor…", en: "Checking the link…" },
  "link.verifiedTitle": { tr: "E-postan doğrulandı", en: "Your email is verified" },
  "link.verifiedBody": { tr: "Şifreni unutursan bu adrese sıfırlama bağlantısı gönderebiliriz.", en: "If you forget your password, we can send a reset link to this address." },
  "link.badTitle": { tr: "Bağlantı çalışmadı", en: "This link didn't work" },
  "link.badVerify": { tr: "Bağlantı geçersiz, kullanılmış ya da süresi dolmuş. Menüdeki “E-postanı doğrula” ile yenisini isteyebilirsin.", en: "The link is invalid, used or expired. Request a new one from “Verify your email” in the menu." },
  "link.badReset": { tr: "Bağlantı geçersiz, kullanılmış ya da süresi dolmuş. Girişteki “Şifremi unuttum” ile yenisini isteyebilirsin.", en: "The link is invalid, used or expired. Request a new one with “Forgot password?” on the sign-in screen." },
  "link.resetTitle": { tr: "Yeni şifre belirle", en: "Set a new password" },
  "link.resetBody": { tr: "Şifren değişince diğer cihazlardaki oturumların kapanır.", en: "Changing your password signs you out on other devices." },
  "link.newPassword": { tr: "Yeni şifre", en: "New password" },
  "link.newPassword2": { tr: "Yeni şifre (tekrar)", en: "New password (again)" },
  "link.resetSubmit": { tr: "Şifreyi değiştir", en: "Change password" },
  "link.pwShort": { tr: "Şifre en az {n} karakter olmalı.", en: "The password must be at least {n} characters." },
  "link.pwMismatch": { tr: "İki şifre aynı değil.", en: "The two passwords don't match." },
  "link.resetDoneTitle": { tr: "Şifren değişti", en: "Your password has changed" },
  "link.resetDoneBody": { tr: "Bu cihazda oturumun açık. Diğer cihazlarda yeni şifrenle giriş yapman gerekecek.", en: "You're signed in on this device. On other devices, sign in with your new password." },
});

const MIN_PASSWORD_LEN = 8;

function readToken() {
  const token = new URLSearchParams(window.location.search).get("token") || "";
  if (token) window.history.replaceState(null, "", window.location.pathname);
  return token;
}

function Shell({ children }) {
  const { t } = useI18n();
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center bg-ink-900 px-4 py-10">
      <a href="/" className="mb-6 font-display text-lg font-semibold text-slate-100">
        News<span className="text-accent">Radar</span>
      </a>
      <Card className="w-full max-w-sm p-6">{children}</Card>
      <a href="/app" onClick={(e) => { e.preventDefault(); navigate("/app"); }} className="mt-5 text-meta text-slate-400 underline-offset-2 hover:text-slate-200 hover:underline">
        {t("link.toApp")}
      </a>
    </main>
  );
}

function Result({ ok, title, body }) {
  const Icon = ok ? CheckCircle2 : XCircle;
  return (
    <div className="text-center" role="status">
      <Icon className={`mx-auto mb-3 h-8 w-8 ${ok ? "text-emerald-600" : "text-rose-600"}`} aria-hidden="true" />
      <h1 className="font-display text-lg font-medium text-slate-100">{title}</h1>
      {body && <p className="mt-2 text-body text-slate-400">{body}</p>}
    </div>
  );
}

function VerifyEmail() {
  const { t } = useI18n();
  const [state, setState] = useState("busy");
  const once = useRef(false);
  useEffect(() => {
    if (once.current) return;
    once.current = true;
    const token = readToken();
    if (!token) return setState("bad");
    verifyEmail(token).then(() => setState("ok")).catch(() => setState("bad"));
  }, []);
  if (state === "busy") return <p className="text-center text-body text-slate-400" aria-busy="true">{t("link.checking")}</p>;
  return state === "ok"
    ? <Result ok title={t("link.verifiedTitle")} body={t("link.verifiedBody")} />
    : <Result title={t("link.badTitle")} body={t("link.badVerify")} />;
}

function ResetPassword() {
  const { t } = useI18n();
  const [token] = useState(readToken);
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [done, setDone] = useState(false);
  if (!token) return <Result title={t("link.badTitle")} body={t("link.badReset")} />;
  if (done) return <Result ok title={t("link.resetDoneTitle")} body={t("link.resetDoneBody")} />;
  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    if (pw.length < MIN_PASSWORD_LEN) return setErr(t("link.pwShort", { n: MIN_PASSWORD_LEN }));
    if (pw !== pw2) return setErr(t("link.pwMismatch"));
    setBusy(true);
    setErr(null);
    try {
      await resetPassword(token, pw);
      setDone(true);
    } catch (e2) {
      setErr(e2.status === 400 ? t("link.badReset") : e2.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <div className="mb-2 flex items-center gap-2">
        <LockKeyhole className="h-5 w-5 text-accent" aria-hidden="true" />
        <h1 className="font-display text-lg font-medium text-slate-100">{t("link.resetTitle")}</h1>
      </div>
      <p className="text-meta text-slate-400">{t("link.resetBody")}</p>
      <Field label={t("link.newPassword")} htmlFor="rp-1">
        <Input id="rp-1" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus />
      </Field>
      <Field label={t("link.newPassword2")} htmlFor="rp-2">
        <Input id="rp-2" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} />
      </Field>
      {err && <p className="text-meta text-rose-600" role="alert">{err}</p>}
      <Button type="submit" variant="primary" disabled={busy} className="w-full">
        {busy ? t("acc.working") : t("link.resetSubmit")}
      </Button>
    </form>
  );
}

export default function EmailLinkPage({ kind }) {
  return <Shell>{kind === "reset" ? <ResetPassword /> : <VerifyEmail />}</Shell>;
}
