// Hesap modalı: anonim oturumu KALICI hesaba çevir (upgrade) ya da mevcut hesaba GİRİŞ.
// Genel şifre kapısı YOK — site herkese açık.
import React, { useState } from "react";
import { X, UserPlus, LogIn } from "lucide-react";
import { upgradeAccount, userLogin } from "../api.js";

export default function AccountModal({ mode: initialMode, onClose, onDone }) {
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-sm rounded-2xl border border-ink-600 bg-ink-800 p-6 shadow-card-hover">
        <button
          onClick={onClose}
          aria-label="Kapat"
          className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="mb-1 flex items-center gap-2 font-display text-lg font-bold text-slate-100">
          {isUpgrade ? <UserPlus className="h-5 w-5 text-accent" /> : <LogIn className="h-5 w-5 text-accent" />}
          {isUpgrade ? "Hesap oluştur" : "Giriş yap"}
        </div>
        <p className="mb-4 text-[13px] leading-relaxed text-slate-400">
          {isUpgrade
            ? "Başka cihazlardan da erişmek için kullanıcı adı ve şifre belirle. Mevcut listen ve geçmişin korunur."
            : "Kullanıcı adın ve şifrenle giriş yap."}
        </p>

        <form onSubmit={submit} className="space-y-2.5">
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Kullanıcı adı"
            autoComplete="username"
            className="w-full rounded-lg border border-ink-500 bg-ink-900 px-3 py-2 text-sm outline-none focus:border-accent"
          />
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            placeholder="Şifre"
            autoComplete={isUpgrade ? "new-password" : "current-password"}
            className="w-full rounded-lg border border-ink-500 bg-ink-900 px-3 py-2 text-sm outline-none focus:border-accent"
          />
          {err && <p className="text-xs text-rose-400">{err}</p>}
          <button
            disabled={busy}
            className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:brightness-105 disabled:opacity-60"
          >
            {busy ? "…" : isUpgrade ? "Hesabı oluştur" : "Giriş yap"}
          </button>
        </form>

        <div className="mt-3 text-center text-xs text-slate-500">
          {isUpgrade ? "Zaten hesabın var mı? " : "Hesabın yok mu? "}
          <button
            onClick={() => { setErr(null); setMode(isUpgrade ? "login" : "upgrade"); }}
            className="text-accent hover:underline"
          >
            {isUpgrade ? "Giriş yap" : "Hesap oluştur"}
          </button>
        </div>
      </div>
    </div>
  );
}
