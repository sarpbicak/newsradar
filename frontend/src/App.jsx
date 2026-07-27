// NewsRadar kök bileşeni: durum yükleme, genel görünüm/detay yönlendirme,
// global yenileme, sağlayıcı uyarıları, footer.
import React, { useCallback, useEffect, useState } from "react";
import { api, getToken, logout, setUnauthorizedHandler } from "./api.js";
import Overview from "./components/Overview.jsx";
import EntityDetail from "./components/EntityDetail.jsx";
import Login from "./components/Login.jsx";
import { Skeleton } from "./components/ui.jsx";

export default function App() {
  const [authed, setAuthed] = useState(() => !!getToken());
  const [cards, setCards] = useState([]);
  const [status, setStatus] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [selected, setSelected] = useState(null); // entity id | null
  const [starting, setStarting] = useState(false); // 'Yenile'ye basıldı, sunucu henüz onaylamadı
  const [loaded, setLoaded] = useState(false); // ilk yükleme tamamlandı mı (skeleton için)
  const [loadError, setLoadError] = useState(null);
  const [notice, setNotice] = useState(null);

  // Tarama sürüyor mu: sunucu durumu VEYA iyimser 'başlatılıyor' bayrağı.
  const running = !!status?.is_running;
  const isRefreshing = starting || running;

  // Herhangi bir istek 401 dönerse (token süresi dolmuş/geçersiz) giriş ekranına dön.
  useEffect(() => {
    setUnauthorizedHandler(() => setAuthed(false));
  }, []);

  const loadCards = useCallback(async () => {
    try {
      const [c, s, sug] = await Promise.all([
        api.listEntities(),
        api.status(),
        api.listSuggestions(),
      ]);
      setCards(c);
      setStatus(s);
      setSuggestions(sug);
      setLoadError(null);
    } catch (e) {
      setLoadError(e.message);
    } finally {
      setLoaded(true);
    }
  }, []);

  // Giriş yapılınca ilk yükleme. Devam eden bir tarama varsa status.is_running
  // ile yakalanır → aşağıdaki polling efekti otomatik devreye girer.
  useEffect(() => {
    if (authed) loadCards();
  }, [authed, loadCards]);

  // Bir tarama sürerken her 5 sn'de bir status + kartları yenile (canlı ilerleme).
  // Tarama bitince verileri son bir kez çekip tamamlanma bildirimini göster.
  useEffect(() => {
    if (!authed || !isRefreshing) return;
    let cancelled = false;
    let timer;
    async function tick() {
      try {
        const [c, s, sug] = await Promise.all([
          api.listEntities(),
          api.status(),
          api.listSuggestions(),
        ]);
        if (cancelled) return;
        setCards(c);
        setStatus(s);
        setSuggestions(sug);
        setLoadError(null);
        if (s.is_running) {
          setStarting(false); // sunucu çalıştığını doğruladı
          timer = setTimeout(tick, 5000);
        } else {
          // Tamamlandı → özet bildirimi (status.last_summary'den).
          setStarting(false);
          const sm = s.last_summary;
          if (sm) {
            const parts = [`${sm.fetched_new} yeni haber`, `${sm.analyzed} analiz`];
            if (sm.prefiltered) parts.push(`${sm.prefiltered} ön-filtre`);
            if (sm.discarded) parts.push(`${sm.discarded} elenen`);
            setNotice({
              type: sm.warnings.length ? "warn" : "ok",
              text: `Yenilendi: ${parts.join(" · ")}.` +
                (sm.warnings.length ? ` ${sm.warnings.length} uyarı.` : ""),
              details: sm.warnings,
            });
          }
          // isRefreshing artık false → efekt temizlenir, döngü durur.
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e.message);
          timer = setTimeout(tick, 5000);
        }
      }
    }
    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [authed, isRefreshing]);

  function handleLogout() {
    logout();
    setAuthed(false);
    setSelected(null);
    setCards([]);
    setStatus(null);
    setSuggestions([]);
  }

  // Giriş yapılmadıysa panoyu hiç yükleme — önce şifre ekranı.
  if (!authed) return <Login onSuccess={() => setAuthed(true)} />;

  async function handleRefresh() {
    setNotice(null);
    setStarting(true); // iyimser: polling hemen başlasın
    try {
      await api.refresh(); // anında döner; tarama arka planda
      const s = await api.status();
      setStatus(s);
    } catch (e) {
      setStarting(false);
      setNotice({ type: "warn", text: `Yenileme başlatılamadı: ${e.message}`, details: [] });
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

  async function handleAddSuggestion(id) {
    const entity = await api.addSuggestion(id);
    await loadCards(); // entity listesi + öneriler otomatik güncellensin
    setNotice({
      type: "ok",
      text: `${entity.name} izleme listesine eklendi — bir sonraki yenilemede analiz edilecek.`,
      details: [],
    });
  }

  async function handleDismissSuggestion(id) {
    await api.dismissSuggestion(id);
    setSuggestions((prev) => prev.filter((s) => s.id !== id));
  }

  // Eksik anahtar uyarıları (status'tan).
  const missingKeys = [];
  if (status) {
    if (!status.providers.finnhub) missingKeys.push("FINNHUB_API_KEY (ticker haberleri)");
    if (!status.providers.newsapi) missingKeys.push("NEWSAPI_KEY (keyword haberleri)");
    if (!status.claude) missingKeys.push("ANTHROPIC_API_KEY (analiz)");
    // FMP opsiyonel: yoksa yalnızca hedef fiyat gösterilmez (tavsiye/haber çalışır).
    if (status.providers["fmp-target"] === false)
      missingKeys.push("FMP_API_KEY (analist hedef fiyatı — opsiyonel)");
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-ink-600 bg-ink-900/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          <div className="flex items-baseline gap-2">
            <span className="font-display text-lg font-bold tracking-tight text-slate-100">
              📡 NewsRadar
            </span>
            <span className="hidden font-mono text-[11px] uppercase tracking-wide text-slate-500 sm:inline">
              haber akışı · risk paneli
            </span>
          </div>
          <div className="flex items-center gap-2">
            {/* NewsAPI kota göstergesi */}
            {status?.newsapi_quota && (
              <span
                className={`hidden font-mono text-[11px] sm:inline ${
                  status.newsapi_quota.exhausted
                    ? "text-rose-400"
                    : status.newsapi_quota.warn
                    ? "text-amber-400"
                    : "text-slate-500"
                }`}
                title="NewsAPI günlük kota (rolling 24s)"
              >
                NewsAPI: {status.newsapi_quota.used}/{status.newsapi_quota.limit}
              </span>
            )}
            <button
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="flex items-center gap-2 rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-white disabled:opacity-70"
            >
              {isRefreshing ? (
                <>
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                  {running
                    ? `Yenileniyor… (${status.progress_done}/${status.progress_total})`
                    : "Başlatılıyor…"}
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

        {isRefreshing && (
          <div className="mb-4 flex items-center gap-3 rounded-lg border border-accent/30 bg-accent/10 px-4 py-3 text-sm text-slate-200">
            <span className="inline-block h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-accent/40 border-t-accent" />
            {running ? (
              <span>
                Tarama sürüyor… <strong>{status.progress_done}/{status.progress_total}</strong> şirket işlendi.
                Bittiğinde pano otomatik güncellenecek — sayfayı kapatabilirsiniz.
              </span>
            ) : (
              <span>Yenileme başlatılıyor…</span>
            )}
          </div>
        )}

        {status?.newsapi_quota?.warn && (
          <div
            className={`mb-4 rounded-lg border px-4 py-3 text-sm ${
              status.newsapi_quota.exhausted
                ? "border-rose-500/30 bg-rose-500/10 text-rose-300"
                : "border-amber-500/30 bg-amber-500/10 text-amber-200"
            }`}
          >
            {status.newsapi_quota.exhausted ? (
              <>
                NewsAPI kotası doldu ({status.newsapi_quota.used}/{status.newsapi_quota.limit}),{" "}
                <strong>{status.newsapi_quota.reset_in_hours} saat</strong> sonra sıfırlanır —
                keyword (şirket/konu) haberleri bu süre boyunca güncellenmeyecek. Ticker'lar etkilenmez.
              </>
            ) : (
              <>
                NewsAPI kotası doluyor: {status.newsapi_quota.used}/{status.newsapi_quota.limit}{" "}
                kullanıldı. Kalan {status.newsapi_quota.remaining} istek — dikkatli kullanın.
              </>
            )}
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

        {!loaded && selected == null ? (
          /* İlk yükleme — layout zıplamasın diye iskelet kartlar */
          <div className="stagger grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="rounded-xl border border-ink-600 bg-ink-800 p-4 shadow-card">
                <Skeleton className="mb-3 h-4 w-24" />
                <Skeleton className="mb-3 h-8 w-full" />
                <Skeleton className="mb-3 h-12 w-full" />
                <Skeleton className="h-4 w-32" />
              </div>
            ))}
          </div>
        ) : selected == null ? (
          <Overview
            cards={cards}
            onOpen={setSelected}
            onCreate={handleCreate}
            onDelete={handleDelete}
            suggestions={suggestions}
            onAddSuggestion={handleAddSuggestion}
            onDismissSuggestion={handleDismissSuggestion}
            scanning={isRefreshing}
          />
        ) : (
          <EntityDetail entityId={selected} onBack={() => setSelected(null)} />
        )}
      </main>

      <footer className="mx-auto max-w-7xl px-6 pb-10 pt-6 text-center text-xs leading-relaxed text-slate-500">
        Haber akışı bazlı sinyal — değerleme veya fiyat tahmini değil. Analist hedefleri
        Finnhub konsensüs verisidir. Kararlar size aittir.
      </footer>

      <a
        className="signature"
        href="https://github.com/sarpbicak"
        target="_blank"
        rel="noreferrer"
      >
        built by Sarp Bıçak
      </a>
    </div>
  );
}
