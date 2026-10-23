// NewsRadar kök bileşeni: durum yükleme, genel görünüm/detay yönlendirme,
// global yenileme, sağlayıcı uyarıları, footer.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, bootstrapSession, getUserToken, logout, setUnauthorizedHandler } from "./api.js";
import Overview, { OverviewSkeleton } from "./components/Overview.jsx";
import EntityDetail from "./components/EntityDetail.jsx";
import AccountModal from "./components/AccountModal.jsx";
import PrivacyModal from "./components/PrivacyModal.jsx";
import AdminPanel from "./components/AdminPanel.jsx";
import HowItWorks from "./components/HowItWorks.jsx";
import FeedbackWidget from "./components/FeedbackWidget.jsx";
import AppHeader from "./components/AppHeader.jsx";
import { LanguageModal } from "./components/LanguageBits.jsx";
import { useIsMobile } from "./components/ui.jsx";
import { WRAP } from "./components/NavBar.jsx";
import { fmtMsg, refreshParts, useI18n } from "./i18n.jsx";
import { ArrowDown } from "lucide-react";
import { navigate, usePath } from "./router.js";

// Mobil aşağı-çekip-yenile eşiği (px). Bu mesafeyi geçince bırakınca yenilenir.
const PULL_THRESHOLD = 70;

// Tarama sürerken durum yoklama aralığı — adım metni ("X için haberler çekiliyor…") ve
// entity içi çubuk akıcı görünsün diye kısa.
const POLL_MS = 1500;

export default function App({ setLang }) {
  const { t, lang } = useI18n();
  // İlk ziyarette dil sorulur (localStorage'da seçim yoksa).
  const [showLangModal, setShowLangModal] = useState(() => !localStorage.getItem("nr_lang"));
  const [switchingLang, setSwitchingLang] = useState(false); // dil değişiminde kısa fade
  const [user, setUser] = useState(null);            // kişisel kullanıcı (anon ya da kayıtlı)
  const [checkingSession, setCheckingSession] = useState(true);
  const [account, setAccount] = useState(null);      // "upgrade" | "login" | null (modal)
  const [showPrivacy, setShowPrivacy] = useState(false);
  const [view, setView] = useState("dashboard");     // "dashboard" | "admin"
  const [showHow, setShowHow] = useState(false); // "Nasıl çalışır?" anlatımı
  const [focusAdd, setFocusAdd] = useState(0); // "Kendi şirketlerinle dene" → ekleme alanı
  const isMobile = useIsMobile();
  const [pull, setPull] = useState(0);          // mobil aşağı-çek mesafesi (px)
  const pullStart = useRef(null);
  const authed = !!user;
  const [cards, setCards] = useState([]);
  const [status, setStatus] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  // Detay sayfası URL'de: /app/e/<id> (paylaşılabilir; tarayıcının geri tuşu çalışır).
  const path = usePath();
  const selected = (() => {
    const m = path.match(/^\/app\/e\/(\d+)/);
    return m ? Number(m[1]) : null;
  })();
  const setSelected = useCallback((id) => navigate(id == null ? "/app" : `/app/e/${id}`), []);
  const [starting, setStarting] = useState(false); // 'Yenile'ye basıldı, sunucu henüz onaylamadı
  const [loaded, setLoaded] = useState(false); // ilk yükleme tamamlandı mı (skeleton için)
  const [loadError, setLoadError] = useState(null);
  const [notice, setNotice] = useState(null);
  // Tarama tamamlanınca kısa süre gösterilen bitiş kartı ({news, analyses}) + sönme.
  const [scanDone, setScanDone] = useState(null);
  const [scanFading, setScanFading] = useState(false);
  // "Yenile"ye kısa süre dikkat çek (ör. yeni eklenen şirketin henüz analizi yok).
  const [refreshAttn, setRefreshAttn] = useState(false);

  // Tarama sürüyor mu: sunucu durumu VEYA iyimser 'başlatılıyor' bayrağı.
  const running = !!status?.is_running;
  const isRefreshing = starting || running;
  // Kişisel yenileme kotası etiketi (admin/limitsiz → gösterme). Örn "(3/5)".
  const refreshQuotaLabel =
    status && !status.refresh_is_admin && status.refresh_limit > 0
      ? `(${Math.max(0, status.refresh_limit - status.refresh_used)}/${status.refresh_limit})`
      : "";

  // Herhangi bir istek 401 dönerse (token süresi doldu) YENİ anon oturum başlat
  // (cihaz cookie'si varsa aynı kullanıcıya döner; yoksa yeni misafir).
  useEffect(() => {
    setUnauthorizedHandler(async () => {
      try {
        setUser(await bootstrapSession());
      } catch {
        setUser(null);
      }
    });
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = `NewsRadar — ${t("app.subtitle")}`;
  }, [lang, t]);

  // "Nasıl çalışır?" ilk girişte OTOMATİK açılmaz — header'daki buton ya da boş ekrandaki
  // "Nasıl çalışır? (30 sn)" bağlantısıyla açılır.
  const closeHow = useCallback(() => setShowHow(false), []);
  // Son adım: modalı kapat, genel görünüme dön, şirket ekleme alanına odaklan.
  const tryOwnCompanies = useCallback(() => {
    setShowHow(false);
    setSelected(null);
    setFocusAdd((n) => n + 1);
  }, []);

  // Açılış: token varsa doğrula; yoksa/geçersizse ANONİM cihaz oturumu başlat.
  // Site herkese açık — kullanıcı şifre girmeden misafir olarak kullanır.
  useEffect(() => {
    let alive = true;
    (async () => {
      let u = null;
      if (getUserToken()) {
        try {
          u = await api.me();
        } catch {
          /* token geçersiz → anon oturum */
        }
      }
      if (!u) {
        try {
          u = await bootstrapSession();
        } catch (e) {
          if (alive) setLoadError(`Oturum başlatılamadı: ${e.message}`);
        }
      }
      if (alive) {
        setUser(u);
        // Kullanıcı bir seçim yapmadıysa (localStorage boş), backend'in dilini benimse
        // (anon: tarayıcı dili; kayıtlı: kayıtlı dil). Modal yine de bir kez onay ister.
        if (u && !localStorage.getItem("nr_lang") && u.language) setLang(u.language);
        setCheckingSession(false);
      }
    })();
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

  // Dili uygula: ÖNCE backend'e kaydet (bekle) → sonra UI dilini çevir + veriyi yeni
  // dilde YENİDEN ÇEK. Backend AI içeriğini user.language'e göre döndürdüğü için, önce
  // POST /users/me/language tamamlanmadan çekersek eski dil gelir. Detay sayfası da
  // `lang` prop'u değişince kendini yeniler (EntityDetail). Geçişte kısa fade.
  const applyLang = useCallback(async (l) => {
    if (l === lang) return;
    setSwitchingLang(true);            // içerik kısaca soluklaşsın (kullanıcı değişimi görsün)
    try {
      await api.setLanguage(l);        // KALICI: get_current_user artık yeni dili okur
    } catch {
      /* token yoksa/hatalıysa yoksay — UI dili yine de değişsin */
    }
    localStorage.setItem("nr_lang", l);
    setLang(l);                        // i18n stringleri + provider (detay refetch tetikler)
    if (authed) {
      try {
        await loadCards();            // kartlar/durum/öneriler yeni dilde
      } catch {
        /* loadCards kendi hatasını setLoadError ile yönetir */
      }
    }
    setSwitchingLang(false);           // fade geri
  }, [lang, setLang, authed, loadCards]);

  // Kullanıcı yüklendiğinde cihazdaki seçili dil (localStorage) backend'le eşleşmiyorsa
  // senkronla — ilk ziyaret yarışını (modal seçimi POST'tan önce) ve cihaz-başı tercihi
  // garanti eder ki AI içeriği doğru dilde gelsin. (user kimliği başına bir kez.)
  useEffect(() => {
    if (!user) return;
    const saved = localStorage.getItem("nr_lang");
    if (saved && (saved === "tr" || saved === "en") && saved !== user.language) {
      api.setLanguage(saved)
        .then(() => setUser((u) => (u ? { ...u, language: saved } : u)))
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

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
          timer = setTimeout(tick, POLL_MS);
        } else {
          // Tamamlandı → çubuğun kendi içinde "Tamamlandı · N haber · N analiz" göster,
          // birkaç saniye sonra yumuşakça söndür. Uyarı/atlama varsa ayrıca not kutusu.
          setStarting(false);
          const sm = s.last_summary;
          if (sm) {
            setScanDone(sm);
            const warns = sm.warnings || [];
            const infos = sm.infos || [];
            // GERÇEK uyarılar (ya da atlama notları) varsa ayrı kalıcı-ish kutu göster;
            // sade başarı durumunda çubuğun bitiş satırı yeterli (ikinci mesaj yok).
            if (warns.length || infos.length) {
              // Mesajlar backend'den KOD + parametre olarak gelir; ham halleri saklanır ve
              // render'da çevrilir → kullanıcı dil değiştirirse not da o dile döner.
              setNotice({
                type: warns.length ? "warn" : "ok",
                summary: sm,
                details: warns,              // yalnızca GERÇEK uyarılar (amber kutu)
                infos,                       // normal atlamalar (soluk, küçük not)
              });
            }
          }
          // isRefreshing artık false → efekt temizlenir, döngü durur.
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e.message);
          timer = setTimeout(tick, POLL_MS);
        }
      }
    }
    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [authed, isRefreshing]);

  // Tamamlanma bildirimi ("Yenilendi: …") birkaç saniye sonra kendiliğinden kaybolsun.
  useEffect(() => {
    if (notice?.type !== "ok") return;
    const id = setTimeout(() => setNotice(null), 7000);
    return () => clearTimeout(id);
  }, [notice]);

  // Bitiş çubuğu: birkaç saniye "Tamamlandı" göster, sonra yumuşakça söndürüp kaldır.
  useEffect(() => {
    if (!scanDone) return;
    setScanFading(false);
    const fadeAt = setTimeout(() => setScanFading(true), 3500);   // gösterim süresi
    const clearAt = setTimeout(() => {                            // fade (0.5s) sonrası kaldır
      setScanDone(null);
      setScanFading(false);
    }, 4000);
    return () => {
      clearTimeout(fadeAt);
      clearTimeout(clearAt);
    };
  }, [scanDone]);

  // Yeni bir tarama başlarsa önceki bitiş çubuğu görünmesin.
  useEffect(() => {
    if (isRefreshing) setScanDone(null);
  }, [isRefreshing]);

  // Logo → ana sayfa (pano). Detay/admin'den döner; zaten anasayfadaysa en üste kaydırır.
  function goHome() {
    setView("dashboard");
    setSelected(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function handleLogout() {
    // Kayıtlı hesaptan çık → MİSAFİR (anon) oturuma dön (cihaz cookie'si varsa o misafir).
    logout();
    setView("dashboard");
    setSelected(null);
    setCards([]);
    setStatus(null);
    setSuggestions([]);
    try {
      setUser(await bootstrapSession());
    } catch {
      setUser(null);
    }
  }

  // Oturum hazırlanıyor (token doğrulama / anon bootstrap) — flaş önlemek için boş bekle.
  if (checkingSession) return <main className="min-h-screen" aria-busy="true" />;
  // Bootstrap tümden başarısız olduysa (nadir) küçük bir hata göster.
  if (!authed)
    return (
      <div className="flex min-h-screen items-center justify-center p-6 text-center text-sm text-slate-400">
        {loadError || t("notice.sessionFailShort")}
      </div>
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
      // Kota mesajı zaten kendini açıklıyor → olduğu gibi göster; değilse önekle.
      const isQuota = /limit/i.test(e.message);
      setNotice({
        type: "warn",
        text: isQuota ? e.message : t("notice.refreshFail", { msg: e.message }),
        details: [],
      });
    }
  }

  // ── Mobil aşağı-çekip-yenile (pull-to-refresh) ──
  // Yalnızca mobilde, pano en üstteyken (scrollY=0) ve tarama yokken.
  const refreshExhausted =
    status && !status.refresh_is_admin && status.refresh_limit > 0 &&
    status.refresh_used >= status.refresh_limit;
  const canPull = isMobile && view === "dashboard" && selected == null && !isRefreshing;

  function onTouchStart(e) {
    if (!canPull || window.scrollY > 0) {
      pullStart.current = null;
      return;
    }
    pullStart.current = e.touches[0].clientY;
  }
  function onTouchMove(e) {
    if (pullStart.current == null) return;
    const dy = e.touches[0].clientY - pullStart.current;
    // Sönümle (0.5×) ve tavanla; yalnızca en üstteyken aşağı çekişte.
    setPull(dy > 0 && window.scrollY === 0 ? Math.min(dy * 0.5, 90) : 0);
  }
  function onTouchEnd() {
    if (pullStart.current == null) return;
    const triggered = pull >= PULL_THRESHOLD;
    pullStart.current = null;
    setPull(0);
    if (!triggered) return;
    // Kota dolmuşsa boşuna istek atma — net mesaj göster (spec 2f).
    if (refreshExhausted) {
      setNotice({
        type: "warn",
        text: t("notice.refreshQuotaFull", { label: refreshQuotaLabel }),
        details: [],
      });
      return;
    }
    handleRefresh();
  }

  // Yeni şirketin henüz analizi yoksa "Yenile" kısa süre vurgulanır.
  function pulseRefresh() {
    setRefreshAttn(true);
    setTimeout(() => setRefreshAttn(false), 2600);
  }
  async function handleCreate(payload) {
    const created = await api.createEntity(payload);
    await loadCards();
    if (created && !created.analysis) pulseRefresh();
  }
  async function handleDelete(id) {
    await api.deleteEntity(id);
    if (selected === id) setSelected(null);
    await loadCards();
  }

  async function handleAddSuggestion(id) {
    const entity = await api.addSuggestion(id);
    await loadCards(); // entity listesi + öneriler otomatik güncellensin
    if (entity && !entity.analysis) pulseRefresh();
    setNotice({
      type: "ok",
      text: t("notice.entityAdded", { name: entity.name }),
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
    if (!status.claude) missingKeys.push("LLM API anahtarı (analiz motoru)");
    // FMP opsiyonel: yoksa yalnızca hedef fiyat gösterilmez (tavsiye/haber çalışır).
    if (status.providers["fmp-target"] === false)
      missingKeys.push("FMP_API_KEY (analist hedef fiyatı — opsiyonel)");
  }

  return (
    <div
      className="min-h-screen"
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
    >
      {/* Mobil pull-to-refresh göstergesi (yalnızca çekerken görünür) */}
      {pull > 0 && (
        <div
          className="pointer-events-none fixed inset-x-0 top-0 z-40 flex justify-center pt-2 md:hidden"
          style={{ transform: `translateY(${pull}px)`, opacity: Math.min(pull / PULL_THRESHOLD, 1) }}
        >
          <div className="flex items-center gap-2 rounded-full border border-ink-500 bg-ink-800 px-3 py-1.5 text-xs text-slate-400 shadow-card">
            <ArrowDown className={`h-4 w-4 transition-transform ${pull >= PULL_THRESHOLD ? "rotate-180 text-accent" : ""}`} />
            {pull >= PULL_THRESHOLD ? t("pull.release") : t("pull.pull")}
          </div>
        </div>
      )}
      <AppHeader
        user={user}
        view={view}
        lang={lang}
        onLang={applyLang}
        onHome={goHome}
        onAccount={setAccount}
        onAdmin={() => setView((v) => (v === "admin" ? "dashboard" : "admin"))}
        onLogout={handleLogout}
        refresh={{ isRefreshing, running, status, quotaLabel: refreshQuotaLabel, onRefresh: handleRefresh, attn: refreshAttn }}
        scan={
          isRefreshing || scanDone
            ? {
                phase: scanDone ? "done" : running ? "running" : "starting",
                currentEntity: running ? status.current_entity : null,
                step: running ? status.step : null,
                stepEntity: running ? status.step_entity : null,
                stepCount: running ? status.step_count : null,
                fraction: running ? status.progress_fraction : null,
                skippedEntity: running ? status.skipped_entity : null,
                done: running ? status.progress_done : 0,
                total: running ? status.progress_total : 0,
                summary: scanDone,
                fading: scanFading,
              }
            : null
        }
      />

      {/* min-h: içerik yüklenirken footer görünür alanda başlayıp sonra aşağı itilmesin (CLS). */}
      <main className={`${WRAP} min-h-[calc(100vh-7rem)] py-8 transition-opacity duration-page ease-std md:py-10 ${switchingLang ? "opacity-40" : "opacity-100"}`}>
        {/* Görünüm geçişi (pano ↔ detay ↔ admin): kısa fade — key değişince yeniden oynar. */}
        <div key={view === "admin" ? "admin" : selected == null ? "overview" : `detail-${selected}`} className="page-in">
        {view === "admin" && user?.is_admin ? (
          <AdminPanel currentUserId={user?.id} />
        ) : (
        <>
        {loadError && (
          <div className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
            {t("notice.apiFail", { msg: loadError })}
          </div>
        )}


        {status?.last_summary?.quota_error && (
          <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
            {t("notice.analysisUnavailable")}
          </div>
        )}

        {status?.budget_exceeded && (
          <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
            {t("notice.budgetExceeded")}
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
            {notice.summary
              ? t("notice.refreshed", { parts: refreshParts(notice.summary, t).join(" · ") }) +
                (notice.details?.length ? t("notice.warnings", { n: notice.details.length }) : "")
              : notice.text}
            {notice.details?.length > 0 && (
              <ul className="mt-1 list-disc pl-5 text-xs">
                {notice.details.slice(0, 6).map((d, i) => (
                  <li key={i}>{fmtMsg(d, t)}</li>
                ))}
              </ul>
            )}
            {/* Normal atlamalar (tazelik/kota) — çok soluk, küçük not (hata değil) */}
            {notice.infos?.length > 0 && (
              <div className="mt-1.5 text-[11px] text-slate-500">
                {t("notice.infos", { n: notice.infos.length })}:{" "}
                {notice.infos.slice(0, 2).map((m) => fmtMsg(m, t)).join(" · ")}
                {notice.infos.length > 2 ? " …" : ""}
              </div>
            )}
          </div>
        )}

        {!loaded && selected == null ? (
          /* İlk yükleme — pano düzenini taklit eden iskelet (layout zıplamasın) */
          <OverviewSkeleton />
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
            onHowItWorks={() => setShowHow(true)}
            focusAdd={focusAdd}
          />
        ) : (
          <EntityDetail entityId={selected} lang={lang} isAdmin={!!user?.is_admin} onBack={() => setSelected(null)} />
        )}
        </>
        )}
        </div>
      </main>

      {showHow && <HowItWorks onClose={closeHow} onTry={tryOwnCompanies} />}
      {account && (
        <AccountModal
          mode={account}
          onClose={() => setAccount(null)}
          onDone={(u) => {
            setUser(u);
            setAccount(null);
          }}
        />
      )}
      {showPrivacy && <PrivacyModal onClose={() => setShowPrivacy(false)} />}

      <footer className="mx-auto max-w-7xl px-6 pb-10 pt-6 text-center text-xs leading-relaxed text-slate-500">
        {t("footer.disclaimer")}
        <button onClick={() => setShowPrivacy(true)} className="ml-1 underline hover:text-slate-300">
          {t("footer.privacy")}
        </button>
        {" · "}
        <a
          href="/?welcome"
          onClick={(e) => { e.preventDefault(); navigate("/?welcome"); }}
          className="underline hover:text-slate-300"
        >
          {t("app.about")}
        </a>
      </footer>

      {/* Sağ altta sabit geri bildirim butonu (kurucu imzası panel içinde).
          Mobilde detay sayfasının alt sekme çubuğuyla çakışmasın diye yükseltilir. */}
      {/* Geri bildirim: panoda sağ altta küçük buton; detay sayfasında (Ask AI ile çakışmasın) yalnızca footer'dan. */}
      <FeedbackWidget showButton={selected == null} />

      {/* İlk giriş dil seçimi (localStorage'da seçim yoksa) */}
      {showLangModal && (
        <LanguageModal onSelect={(l) => { applyLang(l); setShowLangModal(false); }} />
      )}
    </div>
  );
}
