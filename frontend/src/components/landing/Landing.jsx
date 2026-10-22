// Landing sayfası (/). Pano /app'te (ayrı pakette, lazy). Daha önce gelmiş ziyaretçi "/"'ta
// durmaz, doğrudan /app'e gider (router.shouldSkipLanding).
// Bölümler: hero (tek imza animasyonu: HeroLoop) · nasıl çalışır (4 adım, gerçek ekran
// görüntüleri) · gerçek rakamlar (API) · altında ne var (mimari + GitHub) · footer.
// Hareket yalnızca hero döngüsü + rakamlarda kısa sayma; reduced-motion'da hepsi kapalı.
import React, { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { api } from "../../api.js";
import { fmtInt, useI18n } from "../../i18n.jsx";
import { navigate } from "../../router.js";
import Logo from "../Logo.jsx";
import PrivacyModal from "../PrivacyModal.jsx";
import { AnimatedNumber } from "../ui.jsx";
import { LanguageSwitcher } from "../LanguageBits.jsx";
import { ThemeMenu } from "../ThemeToggle.jsx";
import { GITHUB_PROFILE_URL, GITHUB_REPO_URL, GitHubIcon, LINKEDIN_URL, LinkedInIcon, SocialIcon } from "../Social.jsx";
import ArchitectureDiagram from "./ArchitectureDiagram.jsx";
import HeroLoop from "./HeroLoop.jsx";
import ThemedShot from "./ThemedShot.jsx";

function goApp(e) {
  e?.preventDefault();
  navigate("/app");
}

function useInViewOnce(ref) {
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return undefined;
    if (!("IntersectionObserver" in window)) { setSeen(true); return undefined; }
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setSeen(true), { threshold: 0.3 });
    io.observe(el);
    return () => io.disconnect();
  }, [ref, seen]);
  return seen;
}

function Header({ lang, onLang }) {
  const { t } = useI18n();
  return (
    <header className="sticky top-0 z-20 border-b border-ink-600 bg-ink-900/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-2 px-4 py-3 sm:px-6">
        <a
          href="/?welcome"
          onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); }}
          className="inline-flex min-h-[44px] items-center gap-1.5 font-display text-lg font-bold tracking-tight text-slate-100"
        >
          <Logo className="h-5 w-5 text-accent" />
          NewsRadar
        </a>
        <nav className="flex items-center gap-0.5 sm:gap-2" aria-label="NewsRadar">
          <a href="#how-it-works" className="hidden min-h-[44px] items-center rounded-lg px-3 text-sm text-slate-400 transition hover:bg-ink-700 hover:text-slate-200 md:inline-flex">
            {t("land.nav.how")}
          </a>
          <a href="#stack" className="hidden min-h-[44px] items-center rounded-lg px-3 text-sm text-slate-400 transition hover:bg-ink-700 hover:text-slate-200 md:inline-flex">
            {t("land.nav.stack")}
          </a>
          <LanguageSwitcher lang={lang} onChange={onLang} />
          <ThemeMenu />
          <a
            href="/app"
            onClick={goApp}
            className="ml-1 inline-flex min-h-[40px] items-center whitespace-nowrap rounded-lg bg-accent px-3 text-sm font-medium text-accent-fg transition hover:brightness-105 sm:px-4"
          >
            <span className="sm:hidden">{t("land.openAppShort")}</span>
            <span className="hidden sm:inline">{t("land.openApp")}</span>
          </a>
        </nav>
      </div>
    </header>
  );
}

function Hero() {
  const { t } = useI18n();
  return (
    <section className="mx-auto grid max-w-6xl items-center gap-10 px-4 pb-16 pt-10 sm:px-6 md:pt-16 lg:grid-cols-[1.05fr_1fr] lg:gap-14">
      <div>
        <h1 className="font-serif text-[2.1rem] font-semibold leading-[1.12] text-slate-100 sm:text-5xl">
          {t("land.hero.title")}
        </h1>
        <p className="mt-5 max-w-xl text-[16px] leading-relaxed text-slate-400 sm:text-lg">{t("land.hero.sub")}</p>
        <div className="mt-7 flex flex-wrap items-center gap-3">
          <a
            href="/app"
            onClick={goApp}
            className="inline-flex min-h-[48px] items-center gap-2 rounded-xl bg-accent px-5 text-[15px] font-semibold text-accent-fg shadow-card transition hover:brightness-105"
          >
            {t("land.hero.cta")} <ArrowRight className="h-4 w-4" />
          </a>
          <a href="#how-it-works" className="inline-flex min-h-[48px] items-center rounded-xl px-4 text-[15px] font-medium text-accent underline-offset-4 hover:underline">
            {t("land.hero.how")}
          </a>
        </div>
      </div>
      <HeroLoop />
    </section>
  );
}

const STEPS = [1, 2, 3, 4];

function Steps({ lang }) {
  const { t } = useI18n();
  return (
    <section id="how-it-works" className="scroll-mt-20 border-t border-ink-600 bg-ink-800/40">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <h2 className="font-display text-2xl font-bold text-slate-100 sm:text-3xl">{t("land.how.title")}</h2>
        <p className="mt-2 text-slate-400">{t("land.how.sub")}</p>
        <ol className="mt-10 space-y-12">
          {STEPS.map((n) => {
            const title = t(`land.step${n}.title`);
            return (
              <li key={n} className="grid items-center gap-6 md:grid-cols-2 md:gap-10">
                <div className={n % 2 === 0 ? "md:order-2" : ""}>
                  <div className="font-mono text-sm font-semibold text-accent">0{n}</div>
                  <h3 className="mt-1 font-display text-xl font-bold text-slate-100">{title}</h3>
                  <p className="mt-2 max-w-md text-[15px] leading-relaxed text-slate-400">{t(`land.step${n}.body`)}</p>
                </div>
                <ThemedShot step={n} lang={lang} alt={t("land.stepImgAlt", { n, title })} />
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}

function Stats() {
  const { t } = useI18n();
  const [stats, setStats] = useState(null);
  const [failed, setFailed] = useState(false);
  const ref = useRef(null);
  const seen = useInViewOnce(ref);
  useEffect(() => {
    api.publicStats().then(setStats).catch(() => setFailed(true));
  }, []);
  if (failed) return null; // uydurma rakam yok — veri gelmezse bölüm görünmez
  const items = stats
    ? [
        { value: stats.articles_analyzed, label: t("land.stats.articles") },
        { value: stats.companies_tracked, label: t("land.stats.companies") },
        { value: stats.languages.length, label: t("land.stats.languages") },
      ]
    : [null, null, null];
  return (
    <section ref={ref} className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <h2 className="font-display text-2xl font-bold text-slate-100 sm:text-3xl">{t("land.stats.title")}</h2>
      <p className="mt-2 text-slate-400">{t("land.stats.sub")}</p>
      <dl className="mt-8 grid gap-4 sm:grid-cols-3">
        {items.map((it, i) => (
          <div key={i} className="rounded-xl border border-ink-600 bg-ink-800 p-5 shadow-card">
            {it ? (
              <>
                <dd className="font-display text-4xl font-bold text-slate-100">
                  <AnimatedNumber value={seen ? it.value : 0} from={0} format={(v) => fmtInt(Math.round(v))} />
                </dd>
                <dt className="mt-1 text-sm text-slate-400">{it.label}</dt>
              </>
            ) : (
              <div aria-hidden="true">
                <div className="skeleton h-9 w-24" />
                <div className="skeleton mt-2 h-4 w-36" />
              </div>
            )}
          </div>
        ))}
      </dl>
    </section>
  );
}

function Stack() {
  const { t } = useI18n();
  return (
    <section id="stack" className="scroll-mt-20 border-t border-ink-600 bg-ink-800/40">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <h2 className="font-display text-2xl font-bold text-slate-100 sm:text-3xl">{t("land.stack.title")}</h2>
        <p className="mt-2 text-slate-400">{t("land.stack.sub")}</p>
        <div className="mt-8">
          <ArchitectureDiagram />
        </div>
        <a
          href={GITHUB_REPO_URL}
          target="_blank"
          rel="noreferrer"
          className="mt-6 inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-ink-500 bg-ink-800 px-4 text-sm font-medium text-slate-200 transition hover:border-accent/60 hover:text-accent"
        >
          <GitHubIcon /> {t("land.stack.repo")}
        </a>
      </div>
    </section>
  );
}

function Footer({ onPrivacy }) {
  const { t } = useI18n();
  return (
    <footer className="border-t border-ink-600">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-8 text-sm sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <div className="font-medium text-slate-300">{t("land.footer.built", { name: "Sarp Bıçak" })}</div>
          <p className="mt-1 text-xs text-slate-500">
            {t("land.footer.note")}{" "}
            <button onClick={onPrivacy} className="underline underline-offset-2 hover:text-slate-300">
              {t("land.footer.privacy")}
            </button>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <SocialIcon href={LINKEDIN_URL} label="LinkedIn"><LinkedInIcon /></SocialIcon>
          <SocialIcon href={GITHUB_PROFILE_URL} label="GitHub"><GitHubIcon /></SocialIcon>
        </div>
      </div>
    </footer>
  );
}

export default function Landing({ lang, setLang }) {
  const { t } = useI18n();
  const [privacy, setPrivacy] = useState(false);

  // Dil: landing'de oturum yok — yalnızca cihaz tercihi (uygulama girişte backend'e yazar).
  function onLang(l) {
    localStorage.setItem("nr_lang", l);
    setLang(l);
  }

  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = `NewsRadar — ${t("land.hero.title")}`;
  }, [lang, t]);

  // "/#how-it-works" ile gelindiyse (ör. uygulamadaki modaldan) o bölüme kaydır.
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (id) requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView());
  }, []);

  return (
    <div className="min-h-screen">
      <Header lang={lang} onLang={onLang} />
      <main>
        <Hero />
        <Steps lang={lang} />
        <Stats />
        <Stack />
      </main>
      <Footer onPrivacy={() => setPrivacy(true)} />
      {privacy && <PrivacyModal onClose={() => setPrivacy(false)} />}
    </div>
  );
}
