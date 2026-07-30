// NewsRadar kök bileşeni: durum yükleme, genel görünüm/detay yönlendirme,
// global yenileme, sağlayıcı uyarıları, footer.
import React, { useCallback, useEffect, useState } from "react";
import { api, getUserToken, logout, setUnauthorizedHandler } from "./api.js";
import Overview from "./components/Overview.jsx";
import EntityDetail from "./components/EntityDetail.jsx";
import Login from "./components/Login.jsx";
import AdminPanel from "./components/AdminPanel.jsx";
import HowToModal from "./components/HowToModal.jsx";
import { Skeleton } from "./components/ui.jsx";
import { RefreshCw, Menu, X, LogOut, ShieldCheck, LayoutDashboard, Radar, HelpCircle } from "lucide-react";

export default function App() {
  const [user, setUser] = useState(null);            // kişisel kullanıcı (null = çıkış)
  const [checkingSession, setCheckingSession] = useState(!!getUserToken());
  const [view, setView] = useState("dashboard");     // "dashboard" | "admin"
  const [menuOpen, setMenuOpen] = useState(false);   // mobil header menüsü
  const [showHelp, setShowHelp] = useState(false);   // "nasıl okunur" modalı
  const authed = !!user;
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

  // Herhangi bir istek 401 dönerse (kişisel token geçersiz) kişisel girişe dön.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
  }, []);

  // Açılışta kişisel token varsa doğrula (kim olduğumuzu öğren). Geçersizse çıkış.
  useEffect(() => {
    if (!getUserToken()) return;
    let alive = true;
    api
      .me()
      .then((u) => alive && setUser(u))
      .catch(() => {})
      .finally(() => alive && setCheckingSession(false));
    return () => {
      alive = false;
    };
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
            const warns = sm.warnings || [];
            setNotice({
              type: warns.length ? "warn" : "ok",
              text: `Yenilendi: ${parts.join(" · ")}.` +
                (warns.length ? ` ${warns.length} uyarı.` : ""),
              details: warns,              // yalnızca GERÇEK uyarılar (amber kutu)
              infos: sm.infos || [],       // normal atlamalar (soluk, küçük not)
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
    logout(); // kişisel çıkış (genel katman korunur — sadece kişisel girişe döner)
    setUser(null);
    setView("dashboard");
    setSelected(null);
    setCards([]);
    setStatus(null);
    setSuggestions([]);
  }

  // Oturum doğrulanıyorsa (token var, me() bekleniyor) boş bekle — flaş önlemek için.
  if (!authed && checkingSession) return <div className="min-h-screen" />;
  // Giriş yapılmadıysa panoyu hiç yükleme — iki aşamalı giriş ekranı.
  if (!authed)
    return (
      <Login
        onAuthed={(u) => {
          setUser(u);
          setCheckingSession(false);
        }}
      />
    );

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
      {/* Soluk, yavaş hareket eden arka plan aurora (CSS; okunabilirliği bozmaz) */}
      <div className="aurora-bg" aria-hidden="true" />
      <header className="sticky top-0 z-10 border-b border-ink-600 bg-ink-900/70 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-2 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 font-display text-lg font-bold tracking-tight text-slate-100">
              <Radar className="h-5 w-5 text-accent" />
              NewsRadar
            </span>
            <span className="hidden font-mono text-[11px] uppercase tracking-wide text-slate-500 sm:inline">
              haber akışı · risk paneli
            </span>
          </div>
          <div className="flex items-center gap-2">
            {/* Yenile — her zaman görünür (mobilde ikon, masaüstünde metin) */}
            <button
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="inline-flex min-h-[40px] items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:brightness-105 disabled:opacity-70 sm:px-4"
            >
              <RefreshCw className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
              <span className="hidden sm:inline">
                {isRefreshing
                  ? running
                    ? `Yenileniyor… (${status.progress_done}/${status.progress_total})`
                    : "Başlatılıyor…"
                  : "Yenile"}
              </span>
            </button>

            {/* Nasıl okunur — her boyutta görünür ikon (modal açar) */}
            <button
              onClick={() => setShowHelp(true)}
              title="Nasıl okunur?"
              aria-label="Nasıl okunur?"
              className="inline-flex min-h-[40px] min-w-[40px] items-center justify-center rounded-lg text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
            >
              <HelpCircle className="h-5 w-5" />
            </button>

            {/* MASAÜSTÜ: kota + admin + kullanıcı + çıkış inline */}
            <div className="hidden items-center gap-2 sm:flex">
              {status?.newsapi_quota && (
                <span
                  className={`font-mono text-[11px] ${
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
              {user?.is_admin && (
                <button
                  onClick={() => setView((v) => (v === "admin" ? "dashboard" : "admin"))}
                  className={`inline-flex min-h-[40px] items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                    view === "admin"
                      ? "bg-accent/15 text-accent"
                      : "text-slate-500 hover:bg-ink-700 hover:text-slate-200"
                  }`}
                >
                  {view === "admin" ? <LayoutDashboard className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
                  {view === "admin" ? "Pano" : "Admin"}
                </button>
              )}
              <span className="inline-flex items-center gap-1.5 rounded-lg bg-ink-700 px-2.5 py-1.5 text-sm text-slate-300">
                <span className="font-medium">{user?.username}</span>
                {user?.is_admin && (
                  <span className="rounded bg-accent/15 px-1.5 text-[10px] font-semibold text-accent">admin</span>
                )}
              </span>
              <button
                onClick={handleLogout}
                title="Çıkış"
                className="inline-flex min-h-[40px] min-w-[40px] items-center justify-center rounded-lg border border-ink-500 text-slate-400 transition hover:bg-ink-700 hover:text-slate-200"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>

            {/* MOBİL: hamburger menü */}
            <div className="relative sm:hidden">
              <button
                onClick={() => setMenuOpen((o) => !o)}
                aria-label="menü"
                className="inline-flex min-h-[40px] min-w-[40px] items-center justify-center rounded-lg border border-ink-500 text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
              >
                {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
              </button>
              {menuOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                  <div className="absolute right-0 top-full z-20 mt-2 w-60 rounded-xl border border-ink-500 bg-ink-800 p-2 shadow-card-hover">
                    <div className="flex items-center justify-between gap-2 border-b border-ink-600 px-3 py-2">
                      <span className="font-medium text-slate-200">{user?.username}</span>
                      {user?.is_admin && (
                        <span className="rounded bg-accent/15 px-1.5 text-[10px] font-semibold text-accent">admin</span>
                      )}
                    </div>
                    {status?.newsapi_quota && (
                      <div className="px-3 py-2 font-mono text-[11px] text-slate-500">
                        NewsAPI: {status.newsapi_quota.used}/{status.newsapi_quota.limit}
                      </div>
                    )}
                    {user?.is_admin && (
                      <button
                        onClick={() => {
                          setView((v) => (v === "admin" ? "dashboard" : "admin"));
                          setMenuOpen(false);
                        }}
                        className="flex min-h-[44px] w-full items-center gap-2 rounded-lg px-3 text-left text-sm text-slate-300 hover:bg-ink-700"
                      >
                        {view === "admin" ? <LayoutDashboard className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
                        {view === "admin" ? "Panoya dön" : "Admin paneli"}
                      </button>
                    )}
                    <button
                      onClick={() => {
                        handleLogout();
                        setMenuOpen(false);
                      }}
                      className="flex min-h-[44px] w-full items-center gap-2 rounded-lg px-3 text-left text-sm text-slate-300 hover:bg-ink-700"
                    >
                      <LogOut className="h-4 w-4" /> Çıkış
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {view === "admin" && user?.is_admin ? (
          <AdminPanel />
        ) : (
        <>
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
            {/* Normal atlamalar (tazelik/kota) — çok soluk, küçük not (hata değil) */}
            {notice.infos?.length > 0 && (
              <div className="mt-1.5 text-[11px] opacity-50">
                {notice.infos.length} bilgi (kota koruması): {notice.infos.slice(0, 2).join(" · ")}
                {notice.infos.length > 2 ? " …" : ""}
              </div>
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
        </>
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

      <HowToModal open={showHelp} onClose={() => setShowHelp(false)} />
    </div>
  );
}
