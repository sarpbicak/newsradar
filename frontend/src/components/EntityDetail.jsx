// Detay sayfası (/app/e/<id>) — her bilgi TEK yerde:
//   Üst: geri · kısa ad + sembol · durum etiketi · hüküm cümlesi (sayfanın en büyük metni, ~28px)
//   · fiyat satırı (kartla aynı dil) · soluk meta satırı. Hat sayaçları yalnızca admin.
//   Sekmeler (Özet / Grafikler / Haberler / Analistler): ortak Tabs; içerik 200ms fade ile.
//   Ask AI: masaüstünde (≥1024px) sağda sabit panel (kapatılabilir, tercih localStorage'da);
//   mobilde "AI'ya sor" → alttan açılan sayfa (ortak Modal).
// Grafikler (Recharts) ayrı pakette, yalnızca sekme açılınca yüklenir.
import React, { Suspense, lazy, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, BarChart3, ChevronLeft, Eye, FileText, Lock, MessageSquare, Minus, Newspaper, Sparkles, TrendingUp } from "lucide-react";
import { api } from "../api.js";
import { RelTime, RiskChange, SignalPill, horizonLabel, riskColor, sentimentLabel, useIsMobile } from "./ui.jsx";
import { C } from "../theme.js";
import ArticleTable from "./ArticleTable.jsx";
import ChatPanel from "./ChatPanel.jsx";
import AnalystConsensus from "./AnalystConsensus.jsx";
import { PriceRow, displayName, symbolOf } from "./EntityCard.jsx";
import { Button, Card, ErrorState, Modal, Skeleton, Tabs } from "./kit.jsx";
import { tt, fmtDate, fmtInt, parseUtc } from "../i18n.jsx";

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
function chatSuggestions(entity) {
  const a = entity.analysis;
  if (!a) return [];
  const name = displayName(entity);
  const why = a.stance === "bullish" ? "chat.qWhyPos" : a.stance === "bearish" ? "chat.qWhyNeg" : "chat.qWhyMixed";
  const qs = [tt(why, { name })];
  if (entity.type === "ticker" && entity.analyst?.target_mean != null) qs.push(tt("chat.qGap"));
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
  const suggestions = chatSuggestions(entity);
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
            <span className="font-mono text-meta text-slate-500">{symbolOf(entity)}</span>
            {a && <SignalPill stance={a.stance} evidence={entity.evidence_strength} />}
          </div>
          {a?.headline_verdict && <p className="max-w-4xl font-display text-verdict font-medium text-slate-100">{a.headline_verdict}</p>}
          {isTicker ? (
            entity.price != null ? (
              <div title={stale ? tt("detail.targetStale") : undefined}>
                <PriceRow entity={entity} size="lg" muted={stale} />
              </div>
            ) : (
              <p className="text-meta text-slate-500">{tt("detail.noPrice")}</p>
            )
          ) : (
            <p className="flex items-center gap-1.5 text-meta text-slate-500">
              <Lock className="h-3.5 w-3.5" aria-hidden="true" /> {tt("detail.notPublic")}
            </p>
          )}
          {a && (
            <p className="text-micro text-slate-500">
              {entity.horizon && <>{tt("detail.metaHorizon", { h: horizonLabel(entity.horizon) })} · </>}
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
            {entity.analysis_missing_language ? tt("card.langMissing") : tt("detail.noAnalysisBox", { refresh: tt("header.refresh") })}
          </Card>
        ) : (
          <div>
            {/* Sekmeler header'ın hemen altına yapışır (header 64px + güvenli alan). */}
            <div ref={tabsRef} className="sticky top-[calc(4rem+env(safe-area-inset-top))] z-30 -mx-5 overflow-x-auto bg-ink-900 px-5 sm:mx-0 sm:px-0">
              <Tabs items={tabs} value={activeTab} onChange={changeTab} label={tt("detail.tabsLabel")} />
            </div>
            <div key={activeTab} className="tab-fade pt-6" role="tabpanel">
              {activeTab === "summary" && <SummaryTab a={a} entity={entity} riskHistory={risk_history} articles={articles} analyzedCount={st?.analyzed} />}
              {activeTab === "charts" && (
                <Suspense fallback={<Skeleton className="h-72 w-full" />}>
                  <TimeSeriesCharts riskHistory={risk_history} priceHistory={price_history} articles={chartArticles || articles} isTicker={isTicker} isMobile={isMobile} />
                </Suspense>
              )}
              {activeTab === "news" && <ArticleTable articles={articles} />}
              {activeTab === "analysts" && isTicker && (
                <AnalystConsensus analyst={entity.analyst} price={entity.price} type={entity.type} stale={stale} history={data.analyst_history || []} />
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
          <Button variant="primary" icon={MessageSquare} onClick={() => setSheetOpen(true)} className="fixed bottom-[max(5rem,calc(env(safe-area-inset-bottom)+4rem))] right-[max(1rem,env(safe-area-inset-right))] z-40">
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
function SummaryTab({ a, entity, riskHistory = [], articles = [], analyzedCount }) {
  const isPrivate = entity.type !== "ticker";
  const take = mergeTake(a.ai_take, a.summary);
  const spark = riskHistory.slice(-7).map((p) => p.risk_score);
  const scored = articles.filter((x) => x.analyzed && x.sentiment != null);
  const dist = { positive: 0, neutral: 0, negative: 0 };
  scored.forEach((x) => dist[sentimentLabel(x.sentiment)]++);
  const pct = (n) => (scored.length ? Math.round((n / scored.length) * 100) : 0);
  const follow = [...(a.what_to_verify || []), ...(a.invalidation ? [a.invalidation] : [])];
  const dirs = a.driver_directions || [];
  return (
    <div className="space-y-8">
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
                <span className="text-emerald-600">{tt("sum.sentPos")} %{pct(dist.positive)}</span> · {tt("sum.sentNeu")} %{pct(dist.neutral)} ·{" "}
                <span className="text-rose-600">{tt("sum.sentNeg")} %{pct(dist.negative)}</span>
              </p>
            </>
          ) : (
            <p className="text-meta text-slate-500">{tt("sum.noSentiment")}</p>
          )}
        </Indicator>
        <Indicator label={tt("sum.indCoverage")}>
          <div className="flex items-baseline gap-2">
            <span className="font-display text-3xl font-medium tabular-nums text-slate-100">{fmtInt(analyzedCount ?? a.articles_considered)}</span>
            <span className="text-meta text-slate-500">{tt("sum.newsAnalyzed")}</span>
          </div>
          <p className="mt-1 text-micro text-slate-500">
            {tt("sum.updated")} <RelTime iso={a.created_at} />
          </p>
        </Indicator>
      </section>

      <div className="grid gap-8 md:grid-cols-2">
        {a.top_drivers?.length > 0 && (
          <section>
            <h3 className="border-b border-ink-600 pb-2 font-display text-base font-medium text-slate-100">{tt("sum.drivers")}</h3>
            <ul className="divide-y divide-ink-600">
              {a.top_drivers.map((d, i) => {
                const dir = dirs[i];
                const Icon = dir === "up" ? ArrowUp : dir === "down" ? ArrowDown : Minus;
                const cls = dir === "up" ? "text-emerald-600" : dir === "down" ? "text-rose-600" : "text-slate-500";
                return (
                  <li key={i} className="flex gap-3 py-3 text-body text-slate-200">
                    <Icon className={`mt-1 h-4 w-4 shrink-0 ${cls}`} aria-hidden="true" />
                    <span>
                      {dir && <span className="sr-only">{tt(dir === "up" ? "sum.dirUp" : "sum.dirDown")}: </span>}
                      {d}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
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
