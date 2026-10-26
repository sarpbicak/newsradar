// Detay sayfası (/app/e/<id>) — her bilgi TEK yerde:
//   Üst: geri · kısa ad + sembol · durum etiketi · hüküm cümlesi (sayfanın en büyük metni, ~28px)
//   · fiyat satırı (kartla aynı dil) · soluk meta satırı. Hat sayaçları yalnızca admin.
//   Sekmeler (Özet / Grafikler / Haberler / Analistler): ortak Tabs; içerik 200ms fade ile.
//   Ask AI: masaüstünde (≥1024px) sağda sabit panel (kapatılabilir, tercih localStorage'da);
//   mobilde "AI'ya sor" → alttan açılan sayfa (ortak Modal).
// Grafikler (Recharts) ayrı pakette, yalnızca sekme açılınca yüklenir.
import React, { Suspense, lazy, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, BarChart3, ChevronLeft, Eye, FileText, GitFork, Info, Lock, MessageSquare, Minus, Newspaper, Sparkles, TrendingUp } from "lucide-react";
import { api } from "../api.js";
import {
  HorizonToggle, InfoTip, NewsPill, RelTime, RiskChange, divergenceText, effectiveHorizon, hasHorizons, horizonName, horizonOf,
  riskColor, whyQuestion,
  sentimentLabel, targetOf, useHorizon, useIsMobile, verdictInfo,
} from "./ui.jsx";
import { C } from "../theme.js";
import ArticleTable from "./ArticleTable.jsx";
import ChatPanel from "./ChatPanel.jsx";
import AnalystConsensus from "./AnalystConsensus.jsx";
import { SignalScale } from "./SignalScale.jsx";
import { NewsPausedNote, PriceRow, displayName, exchangeOf, marketLabel, noAnalysisText, symbolOf } from "./EntityCard.jsx";
import { Button, Card, ErrorState, Modal, Skeleton, Tabs } from "./kit.jsx";
import { tt, fmtDate, fmtInt, fmtPct, parseUtc } from "../i18n.jsx";

const TimeSeriesCharts = lazy(() => import("./TimeSeriesCharts.jsx"));

const CHAT_PREF_KEY = "nr_chat_panel_open";
const TARGET_STALE_DAYS = 30;

function readChatPref() {
  try {
    return localStorage.getItem(CHAT_PREF_KEY) !== "0";
  } catch {
    return true;
  }
}
function writeChatPref(open) {
  try {
    localStorage.setItem(CHAT_PREF_KEY, open ? "1" : "0");
  } catch {
    /* gizli sekme vb. — tercih bu oturumla sınırlı kalır */
  }
}

// O entity'ye özel 2–3 örnek soru (sohbet panelinin başındaki çipler).
// "Neden" sorusu görünen etiketle aynı yönde: seçili vadenin hükmü (yetersiz veride genel yön).
function chatSuggestions(entity, horizon) {
  const a = entity.analysis;
  if (!a) return [];
  const name = displayName(entity);
  const qs = [whyQuestion(a, entity.evidence_strength, horizon, { name })];
  if (entity.type === "ticker" && targetOf(entity.analyst) != null) qs.push(tt("chat.qGap"));
  else qs.push(tt("chat.qRisk", { name }));
  qs.push(tt("chat.qWatch"));
  return qs;
}

export function targetIsStale(analyst) {
  const asOf = analyst?.fetched_at ? parseUtc(analyst.fetched_at) : null;
  return asOf ? (Date.now() - asOf.getTime()) / 86400000 > TARGET_STALE_DAYS : false;
}

// Yükleniyor: detay düzenini taklit eden iskelet.
function DetailSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <Skeleton className="h-9 w-24 rounded-control" />
      <div className="space-y-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-9 w-full max-w-3xl" />
        <Skeleton className="h-9 w-2/3 max-w-2xl" />
        <Skeleton className="h-12 w-72" />
      </div>
      <Skeleton className="h-11 w-full max-w-md" />
      <div className="grid gap-4 md:grid-cols-3">
        <Skeleton className="h-40 md:col-span-2" />
        <Skeleton className="h-40" />
      </div>
    </div>
  );
}

export default function EntityDetail({ entityId, lang, onBack, isAdmin = false }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reload, setReload] = useState(0);
  const [tab, setTab] = useState("summary");
  const isMobile = useIsMobile();
  const isDesktop = !useIsMobile(1024);
  const [chatOpen, setChatOpen] = useState(readChatPref); // masaüstü yan panel
  const [sheetOpen, setSheetOpen] = useState(false); // mobil alttan sayfa
  const [horizon, setHorizon] = useHorizon(); // kısa / uzun vade (kartlarla ortak)
  const toggleChat = (open) => {
    setChatOpen(open);
    writeChatPref(open);
  };

  // Başka bir şirkete geçince sayfanın başından başla (üst satırlar header'ın altında kalmasın).
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [entityId]);

  // Sekme değişince: sekme çubuğu header'a yapışmışsa (kaydırılmış sayfa) içeriğin başı onun
  // hemen altına gelsin; yeni sekme yarıdan başlamasın.
  const tabsRef = useRef(null);
  const changeTab = (k) => {
    setTab(k);
    const el = tabsRef.current;
    if (!el) return;
    const top = el.getBoundingClientRect().top;
    const stick = parseFloat(getComputedStyle(el).top) || 0;
    if (top <= stick + 1) window.scrollTo({ top: window.scrollY + top - stick, behavior: "instant" });
  };

  // Grafikler sekmesi açılınca daha uzun haber geçmişi (200) bir kez çekilir; ilk yükleme 50 haberle hafif.
  const [chartArticles, setChartArticles] = useState(null);
  useEffect(() => setChartArticles(null), [entityId, lang]);
  useEffect(() => {
    if (tab !== "charts" || chartArticles) return undefined;
    let alive = true;
    api.dashboard(entityId, 200).then((d) => alive && setChartArticles(d.articles)).catch(() => {});
    return () => {
      alive = false;
    };
  }, [tab, entityId, chartArticles]);

  // entityId ya da DİL değişince yeniden çek — AI içeriği yeni dilde gelsin.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .dashboard(entityId)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [entityId, lang, reload]);

  const back = (
    <Button variant="ghost" icon={ChevronLeft} onClick={onBack} className="-ml-3">
      {tt("detail.back")}
    </Button>
  );
  if (loading && !data) return <DetailSkeleton />;
  if (error)
    return (
      <div className="space-y-6">
        {back}
        <ErrorState message={tt("detail.errorBody")} detail={isAdmin ? error : null} onRetry={() => setReload((n) => n + 1)} />
      </div>
    );
  if (!data) return null;

  const { entity, articles, risk_history, price_history, article_status: st } = data;
  const a = entity.analysis;
  const isTicker = entity.type === "ticker";
  // Bu şirkette seçili ufukta veri yoksa veri olan ufuk gösterilir (genel seçim aynı kalır).
  const shown = a ? effectiveHorizon(a, horizon) : { horizon, fellBack: false };
  const suggestions = chatSuggestions(entity, shown.horizon);
  const name = displayName(entity);

  const tabs = [
    { key: "summary", label: tt("detail.tabSummary"), icon: FileText },
    { key: "charts", label: tt("detail.tabCharts"), icon: TrendingUp },
    { key: "news", label: tt("detail.tabNews"), icon: Newspaper },
    ...(isTicker ? [{ key: "analysts", label: tt("detail.tabAnalysts"), icon: BarChart3 }] : []),
  ];
  const activeTab = tabs.some((t) => t.key === tab) ? tab : "summary";
  const stale = targetIsStale(entity.analyst);

  return (
    <div className={isDesktop && a && chatOpen ? "grid grid-cols-[minmax(0,1fr)_360px] items-start gap-8" : ""}>
      <div className="min-w-0 space-y-8 pb-24 lg:pb-0">
        {back}

        {/* ---- ÜST: kısa ad + sembol + durum · hüküm · fiyat · meta ---- */}
        <header className="space-y-4">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <h1 className="font-display text-xl font-semibold text-slate-100">{name}</h1>
            <span className="tabular-nums text-meta text-slate-500">{symbolOf(entity)}</span>
            {marketLabel(entity) && <span className="text-meta text-slate-500">{marketLabel(entity)}</span>}
            {a && (
              <span className="inline-flex flex-wrap items-center gap-2">
                <NewsPill a={a} evidence={entity.evidence_strength} horizon={shown.horizon} />
                {hasHorizons(a) && <HorizonToggle value={horizon} onChange={setHorizon} />}
                <InfoTip text={tt("hz.explain")} />
              </span>
            )}
          </div>
          {a?.headline_verdict && <p className="max-w-4xl font-display text-verdict font-medium text-slate-100">{a.headline_verdict}</p>}
          {isTicker ? (
            entity.price != null ? (
              <PriceRow entity={entity} size="lg" />
            ) : (
              <p className="text-meta text-slate-500">
                {entity.us_market === false ? tt("detail.noPriceExchange", { exchange: exchangeOf(entity) }) : tt("detail.noPrice")}
              </p>
            )
          ) : (
            <p className="flex items-center gap-1.5 text-meta text-slate-500">
              <Lock className="h-3.5 w-3.5" aria-hidden="true" /> {tt("detail.notPublic")}
            </p>
          )}
          {entity.news_paused && <NewsPausedNote className="text-meta" />}
          {a && (
            <p className="text-micro text-slate-500">
              {(() => {
                const n = st?.analyzed ?? entity.evidence_count ?? 0;
                return tt("detail.metaArticles", { n, count: fmtInt(n) });
              })()}
              {entity.analyst?.fetched_at && isTicker && <> · {tt("detail.targetAsOf", { date: fmtDate(entity.analyst.fetched_at) })}</>}
            </p>
          )}
          {isAdmin && st && (
            <p className="text-micro tabular-nums text-slate-500" title={tt("detail.pipelineAdmin")}>
              {tt("detail.pipelineAdmin")}: {tt("detail.articlesN", { n: st.total })} · {tt("detail.analyzedN", { n: st.analyzed })} ·{" "}
              {tt("detail.prefilteredN", { n: st.prefiltered })} · {tt("detail.pendingN", { n: st.pending })} · {tt("detail.expiredN", { n: st.expired ?? 0 })}
            </p>
          )}
        </header>

        {!a ? (
          <Card className="p-6 text-body text-slate-400">
            {entity.analysis_missing_language || entity.no_analysis_reason === "few_news"
              ? noAnalysisText(entity)
              : tt("detail.noAnalysisBox", { refresh: tt("header.refresh") })}
          </Card>
        ) : (
          <div>
            {/* Sekmeler header'ın hemen altına yapışır (header 64px + güvenli alan). */}
            <div ref={tabsRef} className="sticky top-[calc(4rem+env(safe-area-inset-top))] z-30 -mx-5 overflow-x-auto bg-ink-900 px-5 sm:mx-0 sm:px-0">
              <Tabs items={tabs} value={activeTab} onChange={changeTab} label={tt("detail.tabsLabel")} />
            </div>
            <div key={activeTab} className="tab-fade pt-6" role="tabpanel">
              {activeTab === "summary" && <SummaryTab a={a} entity={entity} riskHistory={risk_history} articles={articles} analyzedCount={st?.analyzed} horizon={shown.horizon} fellBackFrom={shown.fellBack ? horizon : null} />}
              {activeTab === "charts" && (
                <Suspense fallback={<Skeleton className="h-72 w-full" />}>
                  <TimeSeriesCharts riskHistory={risk_history} priceHistory={price_history} articles={chartArticles || articles} isTicker={isTicker} isMobile={isMobile} currency={entity.currency || "USD"} />
                </Suspense>
              )}
              {activeTab === "news" && <ArticleTable articles={articles} />}
              {activeTab === "analysts" && isTicker && (
                <AnalystConsensus analyst={entity.analyst} price={entity.price} type={entity.type} stale={stale} history={data.analyst_history || []} currency={entity.currency || "USD"} />
              )}
            </div>
          </div>
        )}
      </div>

      {/* ---- ASK AI ---- */}
      {a && isDesktop && chatOpen && (
        <aside className="sticky top-24">
          {/* Yükseklik içeriğe göre (boş panelde büyük boşluk yok); uzayınca ekranla sınırlanır ve kayar. */}
          <ChatPanel entityId={entity.id} entityName={name} suggestions={suggestions} onClose={() => toggleChat(false)} className="max-h-[calc(100dvh-8rem)]" />
        </aside>
      )}
      {a && isDesktop && !chatOpen && (
        <Button variant="primary" icon={MessageSquare} onClick={() => toggleChat(true)} title={tt("chat.open")} className="fixed bottom-20 right-6 z-40">
          {tt("chat.askAi")}
        </Button>
      )}
      {a && !isDesktop && (
        <>
          <Button variant="primary" icon={MessageSquare} onClick={() => setSheetOpen(true)} className="fixed bottom-[calc(env(safe-area-inset-bottom)+5rem)] right-[calc(env(safe-area-inset-right)+1rem)] z-40">
            {tt("chat.askAi")}
          </Button>
          {sheetOpen && (
            <Modal onClose={() => setSheetOpen(false)} label={tt("chat.title", { name })} size="lg" className="!p-0">
              <ChatPanel entityId={entity.id} entityName={name} suggestions={suggestions} onClose={() => setSheetOpen(false)} className="h-[min(78dvh,calc(var(--vvh,100dvh)_-_1rem))] sm:h-[min(70dvh,calc(var(--vvh,100dvh)_-_2rem))]" bare />
            </Modal>
          )}
        </>
      )}
    </div>
  );
}

// AI yorumu tek blok: ai_take + summary birleşir, tekrar eden cümleler atılır, en fazla 5 cümle.
// (Backend iki alanı ayrı üretir; alan yapısı korunur, birleştirme yalnızca gösterimde.)
const SENT_SPLIT = /(?<=[.!?…])\s+(?=[A-ZÇĞİÖŞÜ0-9"“(])/u;
function words(s) {
  return new Set(s.toLocaleLowerCase().replace(/[^\p{L}\p{N}\s]/gu, " ").split(/\s+/).filter((w) => w.length > 2));
}
function similar(x, y) {
  const a = words(x);
  const b = words(y);
  if (!a.size || !b.size) return false;
  let common = 0;
  a.forEach((w) => b.has(w) && common++);
  return common / Math.min(a.size, b.size) >= 0.6;
}
export function mergeTake(take, summary, max = 5) {
  const out = [];
  for (const part of [take, summary]) {
    for (const s of String(part || "").split(SENT_SPLIT).map((x) => x.trim()).filter(Boolean)) {
      if (out.length < max && !out.some((o) => similar(o, s))) out.push(s);
    }
  }
  return out.join(" ");
}

// Son N değerlendirmenin risk mini çizgisi (0–100 dikey ölçek sabit, kıyaslanabilir).
function Sparkline({ values, color }) {
  if (!values || values.length < 2) return null;
  const w = 84;
  const h = 26;
  const pts = values.map((v, i) => `${((i / (values.length - 1)) * w).toFixed(1)},${(h - 2 - (v / 100) * (h - 4)).toFixed(1)}`).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="shrink-0" aria-hidden="true">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function Indicator({ label, children }) {
  return (
    <div className="min-w-0 px-5 py-4">
      <div className="text-micro font-medium text-slate-500">{label}</div>
      <div className="mt-2">{children}</div>
    </div>
  );
}

// Özet sekmesi: (özel şirket notu) · AI yorumu · 3 gösterge · etkenler + takip edilecekler.
// Etken listesi (↑ olumlu / ↓ olumsuz; ekran okuyucuya yön metni).
function DriverList({ items }) {
  return (
    <ul className="divide-y divide-ink-600">
      {items.map(({ text, direction: dir }, i) => {
        const Icon = dir === "up" ? ArrowUp : dir === "down" ? ArrowDown : Minus;
        const cls = dir === "up" ? "text-emerald-600" : dir === "down" ? "text-rose-600" : "text-slate-500";
        return (
          <li key={i} className="flex gap-3 py-3 text-body text-slate-200">
            <Icon className={`mt-1 h-4 w-4 shrink-0 ${cls}`} aria-hidden="true" />
            <span>
              {dir && <span className="sr-only">{tt(dir === "up" ? "sum.dirUp" : "sum.dirDown")}: </span>}
              {text}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

// Seçili vade: özet + etkenler; altında diğer vadenin tek satırı. Yetersiz veride açık not.
function HorizonSection({ a, horizon }) {
  const other = horizon === "long" ? "short" : "long";
  const cur = horizonOf(a, horizon);
  const curInfo = verdictInfo(cur);
  const oth = horizonOf(a, other);
  const othInfo = verdictInfo(oth);
  const noData = (h) => tt(h === "long" ? "hz.noDataLong" : "hz.noDataShort");
  const cap = (x) => x.charAt(0).toLocaleUpperCase() + x.slice(1);
  return (
    <section>
      <h3 className="border-b border-ink-600 pb-2 font-display text-base font-medium text-slate-100">
        {tt("hz.drivers", { h: horizonName(horizon) })}
      </h3>
      {curInfo.noData ? (
        <p className="py-3 text-body text-slate-400">{noData(horizon)}</p>
      ) : (
        <>
          {cur?.summary && <p className="pt-3 text-body text-slate-200">{cur.summary}</p>}
          {cur?.drivers?.length > 0 && <DriverList items={cur.drivers} />}
        </>
      )}
      <p className="mt-2 border-t border-ink-600 pt-3 text-meta text-slate-400">
        <span className="font-medium text-slate-300">{tt("hz.otherLine", { h: cap(horizonName(other)), v: othInfo.label })}</span>{" "}
        {othInfo.noData ? noData(other) : oth?.summary}
      </p>
    </section>
  );
}

function SummaryTab({ a, entity, riskHistory = [], articles = [], analyzedCount, horizon = "short", fellBackFrom = null }) {
  const isPrivate = entity.type !== "ticker";
  const take = mergeTake(a.ai_take, a.summary);
  const spark = riskHistory.slice(-7).map((p) => p.risk_score);
  const scored = articles.filter((x) => x.analyzed && x.sentiment != null);
  const dist = { positive: 0, neutral: 0, negative: 0 };
  scored.forEach((x) => dist[sentimentLabel(x.sentiment)]++);
  const pct = (n) => (scored.length ? Math.round((n / scored.length) * 100) : 0);
  const follow = [...(a.what_to_verify || []), ...(a.invalidation ? [a.invalidation] : [])];
  const dirs = a.driver_directions || [];
  const horizons = hasHorizons(a);
  const divNote = divergenceText(a, entity.evidence_strength, entity.analyst, horizon);
  return (
    <div className="space-y-8">
      {/* Göstergeler + (ayrışma varsa) tek nötr not — kart notunun detaydaki karşılığı. */}
      <div className="space-y-3">
        {fellBackFrom && (
          <p className="flex items-start gap-2 text-meta text-slate-400" role="status">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
            {tt(fellBackFrom === "long" ? "hz.fallbackToShort" : "hz.fallbackToLong")}
          </p>
        )}
        <SignalScale a={a} entity={entity} horizon={horizon} stale={targetIsStale(entity.analyst)} />
        {divNote && (
          <p className="flex items-start gap-2 text-meta text-slate-400">
            <GitFork className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
            {divNote}
          </p>
        )}
      </div>
      {isPrivate && (
        <p className="flex items-start gap-2.5 text-meta text-slate-400">
          <Lock className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
          <span>
            <span className="font-medium text-slate-300">{tt("card.private")}.</span> {tt("card.privateBody")}
          </span>
        </p>
      )}

      {take && (
        <section className="relative rounded-card bg-ink-800 p-6 ring-1 ring-inset ring-ink-600">
          <span className="absolute inset-y-0 left-0 w-0.5 bg-accent" aria-hidden="true" />
          <h2 className="mb-3 flex items-center gap-2 font-display text-sm font-medium text-slate-200">
            <Sparkles className="h-4 w-4 text-accent" aria-hidden="true" /> {tt("sum.aiTake")}
          </h2>
          <p className="max-w-3xl text-base leading-relaxed text-slate-100">{take}</p>
          <p className="mt-4 text-micro text-slate-500">{tt("sum.aiDisclaimer")}</p>
        </section>
      )}

      {/* Gösterge satırı: tek panel, ince dikey çizgilerle ayrılmış üç sütun (mobilde alt alta). */}
      <section className="grid divide-y divide-ink-600 rounded-card ring-1 ring-inset ring-ink-600 sm:grid-cols-3 sm:divide-x sm:divide-y-0" aria-label={tt("sum.indicators")}>
        <Indicator label={tt("sum.indRisk")}>
          <div className="flex items-end justify-between gap-3">
            <div className="flex items-baseline gap-2">
              <span className="font-display text-3xl font-medium tabular-nums" style={{ color: riskColor(a.risk_score) }}>{a.risk_score}</span>
              <span className="text-meta tabular-nums text-slate-500">/100</span>
              <RiskChange delta={entity.delta} />
            </div>
            <span title={tt("sum.riskTrendTitle")}><Sparkline values={spark} color={riskColor(a.risk_score)} /></span>
          </div>
        </Indicator>
        <Indicator label={tt("sum.indSentiment")}>
          {scored.length ? (
            <>
              <div className="flex h-2 w-full overflow-hidden rounded-[2px] bg-ink-700" aria-hidden="true">
                <span style={{ width: `${pct(dist.positive)}%`, background: C.pos }} />
                <span style={{ width: `${pct(dist.neutral)}%`, background: C.neutral, opacity: 0.45 }} />
                <span style={{ width: `${pct(dist.negative)}%`, background: C.neg }} />
              </div>
              <p className="mt-2 text-micro tabular-nums text-slate-400">
                <span className="text-emerald-600">{tt("sum.sentPos")} {fmtPct(pct(dist.positive), { signed: false })}</span> · {tt("sum.sentNeu")} {fmtPct(pct(dist.neutral), { signed: false })} ·{" "}
                <span className="text-rose-600">{tt("sum.sentNeg")} {fmtPct(pct(dist.negative), { signed: false })}</span>
              </p>
            </>
          ) : (
            <p className="text-meta text-slate-500">{tt("sum.noSentiment")}</p>
          )}
        </Indicator>
        <Indicator label={tt("sum.indCoverage")}>
          <div className="flex items-baseline gap-2">
            <span className="font-display text-3xl font-medium tabular-nums text-slate-100">{fmtInt(analyzedCount ?? a.articles_considered)}</span>
            <span className="text-meta text-slate-500">{tt("sum.newsAnalyzed", { n: analyzedCount ?? a.articles_considered })}</span>
          </div>
          <p className="mt-1 text-micro text-slate-500">
            {tt("sum.updated")} <RelTime iso={a.created_at} />
          </p>
        </Indicator>
      </section>

      <div className="grid gap-8 md:grid-cols-2">
        {horizons ? (
          <HorizonSection a={a} horizon={horizon} />
        ) : (
          a.top_drivers?.length > 0 && (
            <section>
              <h3 className="border-b border-ink-600 pb-2 font-display text-base font-medium text-slate-100">{tt("sum.drivers")}</h3>
              <DriverList items={a.top_drivers.map((text, i) => ({ text, direction: dirs[i] }))} />
            </section>
          )
        )}
        {follow.length > 0 && (
          <section>
            <h3 className="border-b border-ink-600 pb-2 font-display text-base font-medium text-slate-100">{tt("sum.follow")}</h3>
            <p className="mt-2 text-micro text-slate-500">{tt("sum.followNote")}</p>
            <ul className="divide-y divide-ink-600">
              {follow.map((v, i) => (
                <li key={i} className="flex gap-3 py-3 text-body text-slate-200">
                  <Eye className="mt-1 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
                  <span>{v}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
