import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { trackView } from "./api.js";
import ReactDOM from "react-dom/client";
import Landing from "./components/landing/Landing.jsx";
import { I18nProvider, initialLang, loadLang } from "./i18n.jsx";
import { ThemeProvider } from "./theme.js";
import { isAppPath, shouldSkipLanding, usePath } from "./router.js";
import { applyMotionVars } from "./motion.js";
import "./index.css";

// Hareket token'ları (eğri, süreler) — landing ve uygulama aynı değerleri okur.
applyMotionVars();

// Pano (Recharts dahil) AYRI pakette: landing'in ilk yüklemesi küçük kalsın.
const App = lazy(() => import("./App.jsx"));
// E-postadaki doğrulama / şifre sıfırlama bağlantılarının sayfası (nadiren açılır → ayrı paket).
const EmailLinkPage = lazy(() => import("./components/EmailLinkPage.jsx"));
const LINK_PAGES = { "/verify-email": "verify", "/reset-password": "reset" };

// Daha önce gelmiş ziyaretçi "/"'ı açarsa ilk render'dan ÖNCE panoya (landing flaşı yok).
if (shouldSkipLanding()) window.history.replaceState(null, "", "/app");

// Dil durumu en üstte tutulur (I18nProvider sağlar); landing ve App onu okur/değiştirir.
// Seçim (localStorage) her zaman önce; yoksa tarayıcı dili (de → DE, tr → TR, diğerleri → EN).
// Almanca sözlük ayrı pakette: dil ona çevrilmeden önce yüklenir (setLang bekler).
const FIRST_LANG = initialLang();

function Root() {
  const [lang, setLangState] = useState(FIRST_LANG);
  const setLang = useCallback(async (l) => {
    await loadLang(l).catch(() => {}); // yüklenemezse DE arayüz İngilizce metinlerle açılır
    setLangState(l);
  }, []);
  const path = usePath();
  const inApp = isAppPath(path);
  const linkKind = LINK_PAGES[path];
  // Çerezsiz sayaç: landing, /app, detay (bağlantı sayfaları sayılmaz). Aynı yol tekrar sayılmaz
  // (StrictMode çift efekti ve yeniden render).
  const lastTracked = useRef(null);
  useEffect(() => {
    if (linkKind || lastTracked.current === path) return;
    lastTracked.current = path;
    trackView(!inApp ? "landing" : /^\/app\/e\/\d+/.test(path) ? "detail" : "app");
  }, [path, inApp, linkKind]);
  return (
    <ThemeProvider>
      <I18nProvider lang={lang} setLang={setLang}>
        {/* Sayfa geçişi: kısa (≤250ms) fade/slide — key değişince yeniden oynar. */}
        <div key={inApp ? "app" : linkKind || "landing"} className="page-in">
          {linkKind ? (
            <Suspense fallback={<main className="min-h-dvh" aria-busy="true" />}>
              <EmailLinkPage kind={linkKind} />
            </Suspense>
          ) : inApp ? (
            <Suspense fallback={<main className="min-h-dvh" aria-busy="true" />}>
              <App lang={lang} setLang={setLang} />
            </Suspense>
          ) : (
            <Landing lang={lang} setLang={setLang} />
          )}
        </div>
      </I18nProvider>
    </ThemeProvider>
  );
}

function mount() {
  ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
      <Root />
    </React.StrictMode>
  );
}
// TR/EN beklemeden; DE sözlüğü yüklenince (hata olursa yine de, EN metinlerle).
if (FIRST_LANG === "de") loadLang("de").catch(() => {}).finally(mount);
else mount();
