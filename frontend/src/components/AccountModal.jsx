// Hesap modalı: anonim oturumu KALICI hesaba çevir (upgrade) ya da mevcut hesaba GİRİŞ.
// Genel şifre kapısı YOK — site herkese açık.
import React, { useState } from "react";
import { UserPlus, LogIn } from "lucide-react";
import { upgradeAccount, userLogin } from "../api.js";
import { useI18n } from "../i18n.jsx";
import { Button, Field, Input, Modal, ModalHeader } from "./kit.jsx";

export default function AccountModal({ mode: initialMode, onClose, onDone }) {
  const { t } = useI18n();
  const [mode, setMode] = useState(initialMode === "login" ? "login" : "upgrade");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const isUpgrade = mode === "upgrade";

  async function submit(e) {
    e.preventDefault();
    if (!username.trim() || !password || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const u = isUpgrade
        ? await upgradeAccount(username.trim(), password)
        : await userLogin(username.trim(), password);
      onDone(u);
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} labelledBy="acc-title" size="sm">
      <ModalHeader id="acc-title" title={isUpgrade ? t("acc.upgradeTitle") : t("acc.loginTitle")} icon={isUpgrade ? UserPlus : LogIn} onClose={onClose}>
        {isUpgrade ? t("acc.upgradeBody") : t("acc.loginBody")}
      </ModalHeader>
      <form onSubmit={submit} className="space-y-3">
        <Field label={t("acc.username")} htmlFor="acc-user">
          <Input id="acc-user" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" data-autofocus />
        </Field>
        <Field label={t("acc.password")} htmlFor="acc-pass">
          <Input
            id="acc-pass"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            autoComplete={isUpgrade ? "new-password" : "current-password"}
          />
        </Field>
        {err && <p className="text-meta text-rose-600" role="alert">{err}</p>}
        <Button type="submit" variant="primary" disabled={busy} className="w-full">
          {busy ? t("acc.working") : isUpgrade ? t("acc.submitUpgrade") : t("acc.submitLogin")}
        </Button>
      </form>
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
    </Modal>
  );
}
