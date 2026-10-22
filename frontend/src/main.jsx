import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import { I18nProvider } from "./i18n.jsx";
import { ThemeProvider } from "./theme.js";
import "./index.css";

// Dil durumu en üstte tutulur (I18nProvider sağlar); App onu okur/değiştirir.
function Root() {
  const [lang, setLang] = useState(() => {
    const saved = localStorage.getItem("nr_lang");
    if (saved === "tr" || saved === "en") return saved;
    return (navigator.language || "").toLowerCase().startsWith("tr") ? "tr" : "en";
  });
  return (
    <ThemeProvider>
      <I18nProvider lang={lang} setLang={setLang}>
        <App lang={lang} setLang={setLang} />
      </I18nProvider>
    </ThemeProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
