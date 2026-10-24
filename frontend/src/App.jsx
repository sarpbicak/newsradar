// NewsRadar kök bileşeni: durum yükleme, genel görünüm/detay yönlendirme,
// global yenileme, sağlayıcı uyarıları, footer.
import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { api, bootstrapSession, getUserToken, logout, setUnauthorizedHandler } from "./api.js";
import Overview, { OverviewSkeleton } from "./components/Overview.jsx";
import EntityDetail from "./components/EntityDetail.jsx";
import AccountModal from "./components/AccountModal.jsx";
import PrivacyModal from "./components/PrivacyModal.jsx";
import { Button, ErrorState, Toast, ToastStack } from "./components/kit.jsx";
import HowItWorks from "./components/HowItWorks.jsx";
import FeedbackWidget from "./components/FeedbackWidget.jsx";
import AppHeader, { refreshQuota, resetText } from "./components/AppHeader.jsx";
import { LanguageModal } from "./components/LanguageBits.jsx";
import { useIsMobile } from "./components/ui.jsx";
import { WRAP } from "./components/NavBar.jsx";
import { fmtMsg, refreshParts, useI18n } from "./i18n.jsx";
import { ArrowDown, RotateCcw } from "lucide-react";
import { navigate, usePath } from "./router.js";

// Admin paneli ayrı pakette — yalnızca admin açınca yüklenir.
const AdminPanel = lazy(() => import("./components/AdminPanel.jsx"));

// Mobil aşağı-çekip-yenile eşiği (px). Bu mesafeyi geçince bırakınca yenilenir.
const PULL_THRESHOLD = 70;

// Tarama sürerken durum yoklama aralığı — adım metni ("X için haberler çekiliyor…") ve
// entity içi çubuk akıcı görünsün diye kısa.
const POLL_MS = 1500;
// Onaylanan tarama /status'ta bu süre içinde görünmezse "başlatılamadı" denir (normalde anında görünür).
const START_GRACE_MS = 8000;

export default function App({ setLang }) {
  const { t, lang } = useI18n();
  // İlk ziyarette dil sorulur (localStorage'da seçim yoksa).
  const [showLangModal, setShowLangModal] = useState(() => !localStorage.getItem("nr_lang"));
  const [switchingLang, setSwitchingLang] = useState(false); // dil değişiminde kısa fade
  const [user, setUser] = useState(null);            // kişisel kullanıcı (anon ya da kayıtlı)
  const [checkingSession, setCheckingSession] = useState(true);
  const [account, setAccount] = useState(null);      // "upgrade" | "login" | null (modal)
  const [showPrivacy, setShowPrivacy] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
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
  // Sunucu taramayı onayladı → bitene kadar izle. Polling YALNIZCA onaydan sonra başlar:
  // onaydan önce giden bir /status "çalışmıyor" der ve göstergeyi söndürürdü.
  const [tracking, setTracking] = useState(false);
  const trackRef = useRef(null); // { prevCompleted, at } — bu tıklamanın taramasını tanımak için
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
  const queued = !running && !!status?.queued; // sırada bekliyor (başka bir yenileme sürüyor)
  const isRefreshing = starting || tracking || running || queued;
  // Kişisel yenileme hakkı (sayılar /status'tan; admin sınırsız).
  const quota = refreshQuota(status);

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
    document.title = `NewsRadar · ${t("app.subtitle")}`;
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
  // Kullanıcı DEĞİŞİNCE de (çıkış → yeni misafir) yeniden yükle; kimliksiz geçici durumda yükleme yok.
  useEffect(() => {
    if (authed && user?.id) loadCards();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authed, user?.id, loadCards]);

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
  const polling = tracking || running || queued;
  useEffect(() => {
    if (!authed || !polling) return;
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
        setSuggestions(sug);
        setLoadError(null);
        if (s.is_running || s.queued) {
          setStatus(s);
          timer = setTimeout(tick, POLL_MS);
        } else {
          // İzlenen tarama: bitişi, onay anındaki son SONUÇ zamanından farklı bir last_result_at
          // (eski backend'de last_completed_at) ile tanınır. Henüz görünmüyorsa kısa süre daha sor.
          const tr = trackRef.current;
          const resultAt = s.last_result_at ?? s.last_completed_at ?? null;
          const finished = !tr || (resultAt && resultAt !== tr.prevResult);
          if (!finished && Date.now() - tr.at < START_GRACE_MS) {
            timer = setTimeout(tick, 1000);
            return;
          }
          trackRef.current = null;
          setTracking(false);
          setStatus(s);
          if (!finished) {
            showRefreshError(t("notice.refreshNotStarted"), true);
            return;
          }
          // Kuyruk sonucu: birleşti (başka bir yenileme zaten güncelledi) · başarısız (hak iade) ·
          // bütçe doldu · vazgeçildi. "done" ya da sonuç alanı olmayan eski backend → özet akışı.
          const rs = s.last_result_status;
          if (rs === "merged") {
            setNotice({ type: "ok", text: t("notice.queueMerged"), details: [] });
            return;
          }
          if (rs === "failed") {
            showRefreshError(t("notice.refreshFailedRun"), true);
            return;
          }
          if (rs === "budget") {
            showRefreshError(t("notice.queueBudget"), false);
            return;
          }
          if (rs === "canceled") return;
          // Tamamlandı → çubuğun kendi içinde "Tamamlandı · N haber · N analiz" göster,
          // birkaç saniye sonra yumuşakça söndür. Uyarı/atlama varsa ayrıca not kutusu.
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authed, polling]);

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
    // Kayıtlı hesaptan çık → arayüz ANINDA misafir (ad/baş harf kalmaz), kullanıcıya ait tüm
    // durum (kartlar, durum, öneriler, bildirim, takip) sıfırlanır; cihaz cookie'si silinir
    // ve yeni misafir oturumu açılır.
    setUser({ id: null, username: null, is_anonymous: true, is_admin: false, language: user?.language });
    setView("dashboard");
    setSelected(null);
    setCards([]);
    setStatus(null);
    setSuggestions([]);
    setNotice(null);
    trackRef.current = null;
    setTracking(false);
    setStarting(false);
    await logout();
    try {
      setUser(await bootstrapSession());
    } catch {
      setUser(null);
    }
  }

  // Oturum hazırlanıyor (token doğrulama / anon bootstrap) — flaş önlemek için boş bekle.
  if (checkingSession) return <main className="min-h-dvh" aria-busy="true" />;
  // Bootstrap tümden başarısız olduysa (nadir) küçük bir hata göster.
  if (!authed)
    return (
      <main className="flex min-h-dvh items-center justify-center p-6">
        <ErrorState message={t("notice.sessionFailShort")} onRetry={() => window.location.reload()} className="w-full max-w-lg" />
      </main>
    );

  // Yenileme başlatılamadı → her zaman açık bir not (gerekirse "Tekrar dene"). Sessiz kalınmaz.
  function showRefreshError(msg, retry) {
    setNotice({ type: "warn", text: t("notice.refreshFail", { msg }), details: [], retry });
  }

  async function handleRefresh() {
    setNotice(null);
    setStarting(true); // buton hemen "Başlatılıyor…" der; polling onaydan sonra
    const prevResult = status?.last_result_at ?? status?.last_completed_at ?? null;
    let ack;
    try {
      ack = await api.refresh(); // anında döner; tarama arka planda
    } catch (e) {
      setStarting(false);
      if (e.status === 429) {
        // Kota doldu: sunucunun sayılarıyla göstergeyi tazele, ne zaman döneceğini söyle.
        const s = await api.status().catch(() => null);
        if (s) setStatus(s);
        showRefreshError(t("notice.refreshQuotaShort", { when: resetText(t, refreshQuota(s || status)) }), false);
      } else {
        showRefreshError(e instanceof TypeError ? t("notice.refreshNetwork") : e.message, true);
      }
      return;
    }
    setStarting(false);
    // accepted: yenileme başladı ya da sıraya alındı (ya da zaten sürüyor/sırada) → izle.
    if (ack.accepted ?? (ack.started || ack.reason === "running")) {
      trackRef.current = { prevResult, at: Date.now() };
      setTracking(true);
      if (ack.queued) setStatus((s) => (s ? { ...s, queued: true, queue_position: ack.queue_position } : s));
    } else if (ack.reason === "empty") {
      showRefreshError(t("notice.refreshEmpty"), false);
    } else if (ack.reason === "queue_full") {
      showRefreshError(t("notice.queueFull"), true);
    } else if (ack.reason === "budget") {
      showRefreshError(t("notice.queueBudget"), false);
    } else if (ack.reason === "busy") {
      showRefreshError(t("notice.refreshBusy"), true);
    } else {
      showRefreshError(ack.message, true);
    }
  }

  // Sıradaki yenilemeden vazgeç (hak zaten düşmemişti; başlayınca düşer).
  async function handleCancelQueue() {
    try {
      await api.cancelRefresh();
    } catch {
      /* 409: bu arada başladı · 404: sırada yok — durum yoklaması gerçeği gösterir */
    }
    trackRef.current = null;
    setTracking(false);
    const s = await api.status().catch(() => null);
    if (s) setStatus(s);
  }

  // ── Mobil aşağı-çekip-yenile (pull-to-refresh) ──
  // Yalnızca mobilde, pano en üstteyken (scrollY=0) ve tarama yokken.
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
    if (quota.exhausted) {
      setNotice({ type: "warn", text: t("notice.refreshQuotaFull", { when: resetText(t, quota) }), details: [] });
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

  // Teknik sistem uyarıları (eksik anahtar, NewsAPI kotası) — YALNIZCA admin görür.
  const missingKeys = [];
  if (status && user?.is_admin) {
    if (!status.providers.finnhub) missingKeys.push("FINNHUB_API_KEY");
    if (!status.providers.newsapi) missingKeys.push("NEWSAPI_KEY");
    if (!status.claude) missingKeys.push("LLM API");
    // FMP opsiyonel: yoksa yalnızca hedef fiyat gösterilmez (tavsiye/haber çalışır).
    if (status.providers["fmp-target"] === false) missingKeys.push("FMP_API_KEY");
  }
  const nq = user?.is_admin ? status?.newsapi_quota : null;

  return (
    <div
      className="min-h-dvh"
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
          <div className="flex items-center gap-2 rounded-control bg-raised px-3 py-1.5 text-micro text-slate-400 ring-1 ring-ink-500">
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
        onFeedback={() => setFeedbackOpen(true)}
        refresh={{ isRefreshing, running, queued, status, onRefresh: handleRefresh, attn: refreshAttn, anonymous: !!user?.is_anonymous }}
        scan={
          isRefreshing || scanDone
            ? {
                phase: scanDone ? "done" : running ? "running" : queued ? "queued" : "starting",
                queuePos: queued ? status.queue_position : null,
                onCancel: queued ? handleCancelQueue : null,
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
      <main className={`${WRAP} min-h-[calc(100dvh-7rem)] pb-24 pt-8 transition-opacity duration-page ease-std md:py-10 ${switchingLang ? "opacity-40" : "opacity-100"}`}>
        {/* Görünüm geçişi (pano ↔ detay ↔ admin): kısa fade — key değişince yeniden oynar. */}
        <div key={view === "admin" ? "admin" : selected == null ? "overview" : `detail-${selected}`} className="page-in">
        {view === "admin" && user?.is_admin ? (
          <Suspense fallback={<OverviewSkeleton />}>
            <AdminPanel currentUserId={user?.id} />
          </Suspense>
        ) : (
        <>
        {/* Sistem bannerları (sayfa içi, ortak Toast): analiz/bütçe herkese; teknikler admin'e. */}
        {(status?.last_summary?.quota_error || status?.budget_exceeded || nq?.warn || missingKeys.length > 0) && (
          <div className="mb-8 space-y-2">
            {status?.last_summary?.quota_error && <Toast tone="warn" inline>{t("notice.analysisUnavailable")}</Toast>}
            {status?.budget_exceeded && <Toast tone="warn" inline>{t("notice.budgetExceeded")}</Toast>}
            {nq?.warn && (
              <Toast tone={nq.exhausted ? "error" : "warn"} inline>
                {nq.exhausted
                  ? t("sys.newsapiExhausted", { used: nq.used, limit: nq.limit, hours: nq.reset_in_hours })
                  : t("sys.newsapiLow", { used: nq.used, limit: nq.limit, left: nq.remaining })}
              </Toast>
            )}
            {missingKeys.length > 0 && <Toast tone="warn" inline>{t("sys.missingKeys", { keys: missingKeys.join(", ") })}</Toast>}
          </div>
        )}

        {!loaded && selected == null ? (
          /* İlk yükleme — pano düzenini taklit eden iskelet (layout zıplamasın) */
          <OverviewSkeleton />
        ) : loadError && selected == null && cards.length === 0 ? (
          <ErrorState message={t("state.loadFail")} detail={user?.is_admin ? loadError : null} onRetry={loadCards} />
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
            onAccount={setAccount}
            isAnonymous={!!user?.is_anonymous}
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

      {/* Footer — landing footer'ının sade hali. */}
      <footer className="border-t border-ink-600">
        <div className={`${WRAP} flex flex-col gap-3 py-8 text-micro text-slate-500 sm:flex-row sm:items-center sm:justify-between`}>
          <div>
            <span className="font-display text-sm font-medium text-slate-300">{t("land.footer.built", { name: "Sarp Bıçak" })}</span>
            <span className="ml-2 text-micro text-slate-500">{t("land.footer.place")}</span>
            <p className="mt-1 max-w-2xl">{t("footer.disclaimer")}</p>
          </div>
          <nav className="flex flex-wrap gap-x-5 gap-y-2" aria-label={t("footer.nav")}>
            <a href="/?welcome" onClick={(e) => { e.preventDefault(); navigate("/?welcome"); }} className="link-u -mx-1 -my-3.5 inline-block px-1 py-3.5 text-slate-400 hover:text-slate-200">
              {t("app.about")}
            </a>
            <button type="button" onClick={() => setShowPrivacy(true)} className="link-u -mx-1 -my-3.5 inline-block px-1 py-3.5 text-slate-400 hover:text-slate-200">
              {t("footer.privacy")}
            </button>
            <button type="button" onClick={() => setFeedbackOpen(true)} className="link-u -mx-1 -my-3.5 inline-block px-1 py-3.5 text-slate-400 hover:text-slate-200">
              {t("fb.button")}
            </button>
          </nav>
        </div>
      </footer>

      {/* Toast'lar: yenileme özeti ve işlem uyarıları (sağ üst, header'ın altında). */}
      <ToastStack>
        {notice && (
          <Toast tone={notice.type === "ok" ? "ok" : "warn"} onClose={() => setNotice(null)}>
            {notice.summary
              ? t("notice.refreshed", { parts: refreshParts(notice.summary, t).join(" · ") }) +
                (notice.details?.length ? t("notice.warnings", { n: notice.details.length }) : "")
              : notice.text}
            {notice.retry && (
              <Button size="sm" variant="secondary" icon={RotateCcw} onClick={handleRefresh} className="mt-2">
                {t("state.retry")}
              </Button>
            )}
            {notice.details?.length > 0 && (
              <ul className="mt-1 list-disc pl-4 text-micro">
                {notice.details.slice(0, 6).map((d, i) => (
                  <li key={i}>{fmtMsg(d, t)}</li>
                ))}
              </ul>
            )}
            {notice.infos?.length > 0 && (
              <p className="mt-1 text-micro text-slate-500">
                {t("notice.infos", { n: notice.infos.length })}: {notice.infos.slice(0, 2).map((m) => fmtMsg(m, t)).join(" · ")}
                {notice.infos.length > 2 ? " …" : ""}
              </p>
            )}
          </Toast>
        )}
        {loadError && (selected != null || cards.length > 0) && (
          <Toast tone="warn" onClose={() => setLoadError(null)}>
            {t("state.syncFail")}
            {user?.is_admin && <span className="mt-1 block font-mono text-micro text-slate-500">{loadError}</span>}
          </Toast>
        )}
      </ToastStack>

      {/* Geri bildirim: panoda sağ altta küçük buton; detay sayfasında (Ask AI ile çakışmasın) footer'dan. */}
      <FeedbackWidget open={feedbackOpen} onOpenChange={setFeedbackOpen} showButton={selected == null && view === "dashboard"} />

      {/* İlk giriş dil seçimi (localStorage'da seçim yoksa) */}
      {showLangModal && (
        <LanguageModal onSelect={(l) => { applyLang(l); setShowLangModal(false); }} />
      )}
    </div>
  );
}
