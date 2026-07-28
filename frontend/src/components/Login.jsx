// İki aşamalı giriş: Katman 1 (genel şifre) → Katman 2 (kişisel giriş/kayıt).
// Genel şifre geçilince kişisel hesap ekranı gelir. onAuthed(user) ile pano açılır.
import React, { useState } from "react";
import { generalLogin, getGeneralToken, register, userLogin } from "../api.js";

function Field({ label, ...props }) {
  return (
    <>
      <label className="mb-1 block text-xs font-medium uppercase text-slate-500">{label}</label>
      <input
        className="mb-4 w-full rounded-lg border border-ink-500 bg-ink-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-accent"
        {...props}
      />
    </>
  );
}

function Card({ title, subtitle, children }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm rounded-2xl border border-ink-600 bg-ink-800 p-8 shadow-card">
        <div className="mb-1 text-center text-2xl font-bold text-slate-100">📡 NewsRadar</div>
        <p className="mb-6 text-center text-sm text-slate-500">{subtitle}</p>
        {children}
      </div>
    </div>
  );
}

export default function Login({ onAuthed }) {
  // Genel token varsa doğrudan kişisel aşamaya geç.
  const [stage, setStage] = useState(() => (getGeneralToken() ? "personal" : "general"));

  return stage === "general" ? (
    <GeneralGate onPass={() => setStage("personal")} />
  ) : (
    <PersonalAuth onAuthed={onAuthed} onBackToGeneral={() => setStage("general")} />
  );
}

// --- Katman 1: genel şifre ---
function GeneralGate({ onPass }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!password || busy) return;
    setBusy(true);
    setError(null);
    try {
      await generalLogin(password);
      onPass();
    } catch (err) {
      setError(err.message || "Giriş başarısız.");
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card subtitle="Devam etmek için genel şifreyi girin.">
      <form onSubmit={submit}>
        <Field
          label="Genel şifre"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
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
          {busy ? "Kontrol ediliyor…" : "Devam et"}
        </button>
      </form>
    </Card>
  );
}

// --- Katman 2: kişisel giriş / kayıt ---
function PersonalAuth({ onAuthed, onBackToGeneral }) {
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const isRegister = mode === "register";

  async function submit(e) {
    e.preventDefault();
    if (!username || !password || busy) return;
    setBusy(true);
    setError(null);
    try {
      const user = isRegister
        ? await register(username.trim(), password)
        : await userLogin(username.trim(), password);
      onAuthed(user);
    } catch (err) {
      const msg = err.message || "İşlem başarısız.";
      setError(msg);
      // Genel token düştüyse (401) Katman 1'e dön.
      if (!getGeneralToken()) onBackToGeneral();
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card subtitle={isRegister ? "Yeni hesap oluştur." : "Hesabınla giriş yap."}>
      <form onSubmit={submit}>
        <Field
          label="Kullanıcı adı"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
          autoComplete="username"
          placeholder="kullanıcı adınız"
        />
        <Field
          label={isRegister ? "Şifre (en az 8 karakter)" : "Şifre"}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete={isRegister ? "new-password" : "current-password"}
          placeholder="••••••••"
        />
        {error && (
          <div className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={busy || !username || !password}
          className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Lütfen bekleyin…" : isRegister ? "Kayıt ol" : "Giriş yap"}
        </button>
      </form>

      <div className="mt-4 text-center text-sm text-slate-500">
        {isRegister ? "Hesabın var mı? " : "Hesabın yok mu? "}
        <button
          onClick={() => {
            setMode(isRegister ? "login" : "register");
            setError(null);
          }}
          className="font-medium text-accent hover:underline"
        >
          {isRegister ? "Giriş yap" : "Kayıt ol"}
        </button>
      </div>
    </Card>
  );
}
