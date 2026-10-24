// Hesap modalı: anonim oturumu KALICI hesaba çevir (upgrade: kullanıcı adı + e-posta + şifre),
// mevcut hesaba GİRİŞ (kullanıcı adı ya da e-posta) ya da eski hesaba E-POSTA EKLE ("email").
// Genel şifre kapısı YOK — site herkese açık.
import React, { useState } from "react";
import { LogIn, Mail, UserPlus } from "lucide-react";
import { setEmail, upgradeAccount, userLogin } from "../api.js";
import { useI18n } from "../i18n.jsx";
import { Button, Field, Input, Modal, ModalHeader } from "./kit.jsx";

// Sunucuyla aynı gevşek biçim denetimi (tek @, noktalı alan adı, boşluk yok).
const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]+\.[^@\s.]{2,}$/;

export default function AccountModal({ mode: initialMode, onClose, onDone }) {
  const { t } = useI18n();
  const [mode, setMode] = useState(["login", "email"].includes(initialMode) ? initialMode : "upgrade");
  const [username, setUsername] = useState("");
  const [email, setEmailValue] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const isUpgrade = mode === "upgrade";
  const isEmail = mode === "email";

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
      // Sunucu e-posta hataları Türkçe gelir → kullanıcının diline çevir.
      const mailErr = /e-posta/i.test(e2.message);
      setErr(mailErr && e2.status === 409 ? t("acc.emailTaken") : mailErr && e2.status === 422 ? t("acc.emailInvalid") : e2.message);
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
