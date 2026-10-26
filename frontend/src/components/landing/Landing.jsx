// Landing sayfası (/). Pano /app'te (ayrı pakette, lazy). Daha önce gelmiş ziyaretçi "/"'ta
// durmaz, doğrudan /app'e gider (router.shouldSkipLanding).
// Yön: haber masasının gece vardiyası — koyu, sakin, az ama büyük; her bölüm tek fikir.
// Bölümler: hero · manifesto · nasıl çalışır (sabitlenen anlatım) · rakamlar · altında ne var ·
// kapanış · footer. Hareket kaydırmaya bağlı (scroll.js); yalnızca hero açılışı bir kez oynar.
// Hero ve sahneler aynı gerçek örneği kullanır: /public/how-it-works bir kez çekilir; örnek yoksa
// uydurma yok, görseller gizlenir. reduced-motion: hareket yok, her şey son halinde.
import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { api } from "../../api.js";
import { fmtCompact, useI18n } from "../../i18n.jsx";
import { navigate } from "../../router.js";
import { Button } from "../kit.jsx";
import NavBar, { Brand, NavLink, WRAP } from "../NavBar.jsx";
import { LanguageMenu, LanguageSwitcher } from "../LanguageBits.jsx";
import { ThemeMenu } from "../ThemeToggle.jsx";
import { DataSources } from "../ui.jsx";

// Gizlilik penceresi tıklanınca yüklenir (metinleriyle birlikte) — landing'in ilk paketi küçük kalsın.
const PrivacyModal = lazy(() => import("../PrivacyModal.jsx"));
import { GITHUB_PROFILE_URL, GITHUB_REPO_URL, GitHubIcon, LINKEDIN_URL, LinkedInIcon, SocialIcon } from "../Social.jsx";
import ArchitectureDiagram from "./ArchitectureDiagram.jsx";
import Hero from "./Hero.jsx";
import Manifesto from "./Manifesto.jsx";
import Walkthrough from "./Walkthrough.jsx";
import { ease } from "../../motion.js";
import { EngineContext, scrollToId, scrub, useEngineLoader, useScrub } from "./scroll.js";
import { Lines, Reveal } from "./Type.jsx";


function goApp(e) {
  e?.preventDefault();
  navigate("/app");
}

function AppButton({ size = "md", className = "", children }) {
  return (
    <Button as="a" href="/app" onClick={goApp} variant="primary" size={size} className={className}>
      {children}
    </Button>
  );
}

function Nav({ lang, onLang, onAnchor }) {
  const { t } = useI18n();
  return (
    <NavBar
      fixed
      brand={
        <Brand
          href="/?welcome"
          onClick={(e) => {
            e.preventDefault();
            window.scrollTo({ top: 0 });
          }}
        />
      }
    >
      <NavLink href="#how-it-works" onClick={onAnchor}>
        {t("land.nav.how")}
      </NavLink>
      <NavLink href="#stack" onClick={onAnchor}>
        {t("land.nav.stack")}
      </NavLink>
      <span className="hidden sm:inline-flex">
        <LanguageSwitcher lang={lang} onChange={onLang} />
      </span>
      <span className="sm:hidden">
        <LanguageMenu lang={lang} onChange={onLang} />
      </span>
      <ThemeMenu />
      <AppButton className="nav-text">
        <span className="sm:hidden">{t("land.openAppShort")}</span>
        <span className="hidden sm:inline">{t("land.openApp")}</span>
      </AppButton>
    </NavBar>
  );
}

// Rakamlar: /public/stats. Sayaçlar kaydırmayla artar, geri kaydırınca azalır. Uydurma yok —
// veri gelmezse bölüm görünmez.
function Stats() {
  const { t } = useI18n();
  const [stats, setStats] = useState(null);
  const [failed, setFailed] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    api.publicStats().then(setStats).catch(() => setFailed(true));
  }, []);
  useScrub(
    ref,
    (engine, el) => {
      const nums = [...el.querySelectorAll("[data-count]")];
      if (!nums.length) return undefined;
      return scrub(engine, {
        trigger: el,
        end: "center 55%",
        render: (p) => {
          const e = ease(p);
          nums.forEach((n) => (n.textContent = fmtCompact(Math.round(Number(n.dataset.count) * e))));
        },
      });
    },
    [stats]
  );
  if (failed) return null;
  const items = stats
    ? [
        { value: stats.articles_analyzed, label: t("land.stats.articles") },
        { value: stats.assessments, label: t("land.stats.assessments") },
        { value: stats.news_sources, label: t("land.stats.sources") },
        { value: stats.languages.length, label: t("land.stats.languages") },
      ]
    : null;
  return (
    <section className={`${WRAP} py-20 sm:py-32 lg:py-44`} aria-labelledby="stats-title">
      <Lines id="stats-title" lines={[t("land.stats.title")]} className="lx-h2 text-slate-100" />
      <Reveal as="p" className="lx-body mt-6 max-w-xl text-slate-400">
        {t("land.stats.sub")}
      </Reveal>
      {/* Masaüstünde 4 yan yana, mobilde 2×2. */}
      <dl ref={ref} className="mt-16 grid grid-cols-2 gap-x-5 gap-y-12 sm:gap-x-8 lg:mt-20 lg:grid-cols-4">
        {(items || [0, 1, 2, 3]).map((it, i) => (
          <div key={i} className="flex flex-col-reverse border-t border-ink-600 pt-6">
            {it ? (
              <>
                <dt className="lx-body mt-3 text-slate-400">{it.label}</dt>
                <dd className="lx-num whitespace-nowrap text-[clamp(2.5rem,1rem+4vw,5rem)] font-medium leading-none text-accent" data-count={it.value}>
                  {fmtCompact(it.value)}
                </dd>
              </>
            ) : (
              <div aria-hidden="true">
                <div className="skeleton h-16 w-32 max-w-full" />
                <div className="skeleton mt-4 h-5 w-24" />
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
    <section id="stack" tabIndex={-1} className="scroll-mt-16 border-t border-ink-600 py-20 outline-none sm:py-32 lg:py-44" aria-labelledby="stack-title">
      <div className={WRAP}>
        <Lines id="stack-title" lines={[t("land.stack.title")]} className="lx-h2 text-slate-100" />
        <Reveal as="p" className="lx-body mt-6 max-w-2xl text-slate-400">
          {t("land.stack.sub")}
        </Reveal>
        <div className="mt-10 sm:mt-16 lg:mt-20">
          <ArchitectureDiagram />
        </div>
        <Reveal className="mt-8 sm:mt-12">
          <a href={GITHUB_REPO_URL} target="_blank" rel="noreferrer" className="link-u inline-flex min-h-[44px] items-center gap-2.5 text-[17px] font-medium text-slate-200">
            <GitHubIcon /> {t("land.stack.repo")} <span aria-hidden="true">↗</span>
          </a>
        </Reveal>
      </div>
    </section>
  );
}

// "Neden yaptım": kapanıştan önce kısa kişisel not. Metin i18n'de (land.why.body, TR/EN ayrı);
// boşsa bölüm DOM'a hiç girmez. /sarp.jpg varsa yanında küçük yuvarlak fotoğraf, yoksa gizlenir.
// TODO(sarp): kendi metnim
function Why() {
  const { t } = useI18n();
  const [photo, setPhoto] = useState(true);
  const body = t("land.why.body").trim();
  if (!body) return null;
  return (
    <section className="border-t border-ink-600 py-16 sm:py-24 lg:py-32" aria-labelledby="why-title">
      <div className={`${WRAP} grid gap-8 md:grid-cols-[minmax(0,14rem)_minmax(0,1fr)] md:gap-12`}>
        <h2 id="why-title" className="font-display text-2xl font-medium text-slate-100">{t("land.why.title")}</h2>
        <div className="flex items-start gap-5">
          {photo && (
            <img
              src="/sarp.jpg"
              alt={t("land.why.photoAlt")}
              width="64"
              height="64"
              loading="lazy"
              onError={() => setPhoto(false)}
              className="h-16 w-16 shrink-0 rounded-full object-cover ring-1 ring-ink-600"
            />
          )}
          <div className="lx-body max-w-2xl space-y-4 text-slate-300">
            {body.split(/\n\s*\n/).map((p, i) => <p key={i}>{p}</p>)}
          </div>
        </div>
      </div>
    </section>
  );
}

function Closing() {
  const { t } = useI18n();
  return (
    <section className="lx-clip-x border-t border-ink-600 py-20 sm:py-32 lg:py-48">
      <div className={WRAP}>
        <Lines lines={[t("land.cta.title")]} className="lx-h1 text-slate-100" drift={6} />
        <Reveal className="mt-8 sm:mt-12">
          <AppButton size="lg">
            {t("land.openApp")} <ArrowRight className="h-5 w-5" aria-hidden="true" />
          </AppButton>
        </Reveal>
      </div>
    </section>
  );
}

function Footer({ onPrivacy }) {
  const { t } = useI18n();
  return (
    <footer className="border-t border-ink-600">
      <div className={`${WRAP} flex flex-col gap-6 pb-[calc(env(safe-area-inset-bottom)+72px)] pt-10 sm:flex-row md:pb-10 sm:items-end sm:justify-between`}>
        <div>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="font-display text-lg font-medium text-slate-100">{t("land.footer.built", { name: "Sarp Bıçak" })}</span>
            <span className="text-sm text-slate-500">{t("land.footer.place")}</span>
          </div>
          <p className="mt-2 text-sm text-slate-500">
            {t("land.footer.note")}{" "}
            <button onClick={onPrivacy} className="link-u -mx-1 -my-3.5 inline-block px-1 py-3.5 text-slate-400 hover:text-slate-200">
              {t("land.footer.privacy")}
            </button>
          </p>
          <DataSources className="mt-1 text-micro text-slate-500" />
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
  const root = useRef(null);
  const engine = useEngineLoader(root);
  const [privacy, setPrivacy] = useState(false);
  const [demo, setDemo] = useState(null); // null = yükleniyor, false = örnek yok
  // Ekranın altındaki bölümler ilk boyamadan kısa süre sonra: ilk render küçük kalır, yalnızca
  // aşağıda kullanılan fontlar (serif, kalın) hero'dan sonra istenir. #bağlantıyla gelindiyse hemen.
  const [below, setBelow] = useState(() => !!window.location.hash);
  useEffect(() => {
    if (below) return undefined;
    const id = setTimeout(() => setBelow(true), 250);
    return () => clearTimeout(id);
  }, [below]);

  // Dil: landing'de oturum yok — yalnızca cihaz tercihi (uygulama girişte backend'e yazar).
  const onLang = setLang;

  useEffect(() => {
    let alive = true;
    setDemo(null);
    api.publicHowItWorks(lang)
      .then((d) => alive && setDemo(d?.available && d.entity && d.headlines?.length ? d : false))
      .catch(() => alive && setDemo(false));
    return () => { alive = false; };
  }, [lang]);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = `NewsRadar · ${[t("land.hero.l1"), t("land.hero.l2"), t("land.hero.l3")].filter(Boolean).join(" ")}`;
  }, [lang, t]);

  // "/#how-it-works" ile gelindiyse (ör. uygulamadaki modaldan) o bölüme kaydır.
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (id) requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView());
  }, []);

  const onAnchor = useCallback(
    (e) => {
      const id = e.currentTarget.getAttribute("href").slice(1);
      e.preventDefault();
      scrollToId(engine, id);
    },
    [engine]
  );

  return (
    <EngineContext.Provider value={engine}>
      <div ref={root} className="lx min-h-dvh">
        <Nav lang={lang} onLang={onLang} onAnchor={onAnchor} />
        <main>
          <Hero demo={demo} onAnchor={onAnchor} onApp={goApp} />
          {/* Yer tutucu: sayfa baştan kaydırılabilir (kaydırma çubuğu sonradan çıkıp hero'yu kaydırmasın). */}
          {!below && <div style={{ height: "100dvh" }} aria-hidden="true" />}
          {below && (
            <>
              <Manifesto />
              <Walkthrough demo={demo} />
              <Stats />
              <Stack />
              <Why />
              <Closing />
            </>
          )}
        </main>
        {below && <Footer onPrivacy={() => setPrivacy(true)} />}
        {privacy && (
          <Suspense fallback={null}>
            <PrivacyModal onClose={() => setPrivacy(false)} />
          </Suspense>
        )}
      </div>
    </EngineContext.Provider>
  );
}
