// NewsRadar kök bileşeni: durum yükleme, genel görünüm/detay yönlendirme,
// global yenileme, sağlayıcı uyarıları, footer.
import React, { useCallback, useEffect, useState } from "react";
import { api, getToken, logout, setUnauthorizedHandler } from "./api.js";
import Overview from "./components/Overview.jsx";
import EntityDetail from "./components/EntityDetail.jsx";
import Login from "./components/Login.jsx";

export default function App() {
  const [authed, setAuthed] = useState(() => !!getToken());
  const [cards, setCards] = useState([]);
  const [status, setStatus] = useState(null);
  const [selected, setSelected] = useState(null); // entity id | null
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [notice, setNotice] = useState(null);

  // Herhangi bir istek 401 dönerse (token süresi dolmuş/geçersiz) giriş ekranına dön.
  useEffect(() => {
    setUnauthorizedHandler(() => setAuthed(false));
  }, []);

  const loadCards = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([api.listEntities(), api.status()]);
      setCards(c);
      setStatus(s);
      setLoadError(null);
    } catch (e) {
      setLoadError(e.message);
    }
  }, []);

  useEffect(() => {
    if (authed) loadCards();
  }, [authed, loadCards]);

  function handleLogout() {
    logout();
    setAuthed(false);
    setSelected(null);
    setCards([]);
    setStatus(null);
  }

  // Giriş yapılmadıysa panoyu hiç yükleme — önce şifre ekranı.
  if (!authed) return <Login onSuccess={() => setAuthed(true)} />;

  async function handleRefresh() {
    setRefreshing(true);
    setNotice(null);
    try {
      const r = await api.refresh();
      await loadCards();
      const parts = [`${r.fetched_new} yeni haber`, `${r.analyzed} analiz`];
      if (r.discarded) parts.push(`${r.discarded} elenen`);
      setNotice({
        type: r.warnings.length ? "warn" : "ok",
        text: `Yenilendi: ${parts.join(" · ")}.` +
          (r.warnings.length ? ` ${r.warnings.length} uyarı.` : ""),
        details: r.warnings,
      });
    } catch (e) {
      setNotice({ type: "warn", text: `Yenileme hatası: ${e.message}`, details: [] });
    } finally {
      setRefreshing(false);
    }
  }

  async function handleCreate(payload) {
    await api.createEntity(payload);
    await loadCards();
  }
  async function handleDelete(id) {
    await api.deleteEntity(id);
    if (selected === id) setSelected(null);
    await loadCards();
  }

  // Eksik anahtar uyarıları (status'tan).
  const missingKeys = [];
  if (status) {
    if (!status.providers.finnhub) missingKeys.push("FINNHUB_API_KEY (ticker haberleri)");
    if (!status.providers.newsapi) missingKeys.push("NEWSAPI_KEY (keyword haberleri)");
    if (!status.claude) missingKeys.push("ANTHROPIC_API_KEY (analiz)");
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-ink-600 bg-ink-900/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold text-slate-100">📡 NewsRadar</span>
            <span className="hidden text-xs text-slate-500 sm:inline">
              haber akışı bazlı hisse risk analizi
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-2 rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {refreshing ? (
                <>
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                  Yenileniyor…
                </>
              ) : (
                <>↻ Yenile</>
              )}
            </button>
            <button
              onClick={handleLogout}
              className="rounded-md border border-ink-500 px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200"
            >
              Çıkış
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-6">
        {loadError && (
          <div className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
            API'ye bağlanılamadı: {loadError}. Backend çalışıyor mu? (uvicorn app.api.main:app)
          </div>
        )}

        {missingKeys.length > 0 && (
          <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
            ⚠ Eksik anahtar: {missingKeys.join(", ")}. Bu kaynaklar atlanır (uygulama çalışmaya devam eder).
          </div>
        )}

        {notice && (
          <div
            className={`mb-4 rounded-lg border px-4 py-3 text-sm ${
              notice.type === "ok"
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                : "border-amber-500/30 bg-amber-500/10 text-amber-200"
            }`}
          >
            {notice.text}
            {notice.details?.length > 0 && (
              <ul className="mt-1 list-disc pl-5 text-xs opacity-80">
                {notice.details.slice(0, 6).map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {selected == null ? (
          <Overview
            cards={cards}
            onOpen={setSelected}
            onCreate={handleCreate}
            onDelete={handleDelete}
          />
        ) : (
          <EntityDetail entityId={selected} onBack={() => setSelected(null)} />
        )}
      </main>

      <footer className="mx-auto max-w-7xl px-6 py-6 text-center text-xs text-slate-600">
        Haber akışı bazlı sinyal — fiyat tahmini değil, önce doğrula.
      </footer>
    </div>
  );
}
