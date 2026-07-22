// Basit şifre giriş ekranı: pano yüklenmeden önce paylaşılan parolayı sorar.
// Doğruysa token saklanır (api.login) ve onSuccess çağrılır; yanlışsa hata gösterilir.
import React, { useState } from "react";
import { login } from "../api.js";

export default function Login({ onSuccess }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!password || busy) return;
    setBusy(true);
    setError(null);
    try {
      await login(password);
      onSuccess?.();
    } catch (err) {
      setError(err.message || "Giriş başarısız.");
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-2xl border border-ink-600 bg-ink-800 p-8 shadow-xl"
      >
        <div className="mb-1 text-center text-2xl font-bold text-slate-100">📡 NewsRadar</div>
        <p className="mb-6 text-center text-sm text-slate-500">
          Devam etmek için şifreyi girin.
        </p>

        <label className="mb-1 block text-xs font-medium uppercase text-slate-500">
          Şifre
        </label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          className="mb-4 w-full rounded-lg border border-ink-500 bg-ink-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-accent"
          placeholder="••••••••"
        />

        {error && (
          <div className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={busy || !password}
          className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Kontrol ediliyor…" : "Giriş yap"}
        </button>
      </form>
    </div>
  );
}
