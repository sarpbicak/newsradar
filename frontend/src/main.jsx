import React, { Suspense, lazy, useState } from "react";
import ReactDOM from "react-dom/client";
import Landing from "./components/landing/Landing.jsx";
import { I18nProvider } from "./i18n.jsx";
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
function Root() {
  const [lang, setLang] = useState(() => {
    const saved = localStorage.getItem("nr_lang");
    if (saved === "tr" || saved === "en") return saved;
    return (navigator.language || "").toLowerCase().startsWith("tr") ? "tr" : "en";
  });
  const path = usePath();
  const inApp = isAppPath(path);
  const linkKind = LINK_PAGES[path];
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

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
