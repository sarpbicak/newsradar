// Detay sayfası (/app/e/<id>) — her bilgi TEK yerde:
//   Üst: geri · kısa ad + sembol · durum etiketi · hüküm cümlesi (sayfanın en büyük metni, ~28px)
//   · fiyat satırı (kartla aynı dil) · soluk meta satırı. Hat sayaçları yalnızca admin.
//   Sekmeler (Özet / Grafikler / Haberler / Analistler): ortak Tabs; içerik 200ms fade ile.
//   Ask AI: masaüstünde (≥1024px) sağda sabit panel (kapatılabilir, tercih localStorage'da);
//   mobilde "AI'ya sor" → alttan açılan sayfa (ortak Modal).
// Grafikler (Recharts) ayrı pakette, yalnızca sekme açılınca yüklenir.
import React, { Suspense, lazy, useEffect, useState } from "react";
import { BarChart3, ChevronLeft, FileText, Lock, MessageSquare, Newspaper, Sparkles, TrendingUp, Zap } from "lucide-react";
import { api } from "../api.js";
import { RiskDelta, RiskScore, SignalPill, TrendArrow, horizonLabel, stanceLabel, useIsMobile } from "./ui.jsx";
import ArticleTable from "./ArticleTable.jsx";
import ChatPanel from "./ChatPanel.jsx";
import AnalystConsensus from "./AnalystConsensus.jsx";
import { PriceRow, displayName, symbolOf } from "./EntityCard.jsx";
import { Button, Card, Chip, ErrorState, Modal, Skeleton, Tabs } from "./kit.jsx";
import { tt, fmtDate, fmtDateTime, fmtInt, parseUtc } from "../i18n.jsx";

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
  const qs = [tt("chat.qWhy", { name, stance: stanceLabel(a.stance).toLowerCase() })];
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
      <Skeleton className="h-9 w-24 rounded-full" />
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
    <div className={isDesktop && a && chatOpen ? "grid grid-cols-[minmax(0,1fr)_380px] items-start gap-8" : ""}>
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
            <div className="-mx-5 overflow-x-auto px-5 sm:mx-0 sm:px-0">
              <Tabs items={tabs} value={activeTab} onChange={setTab} label={tt("detail.tabsLabel")} />
            </div>
            <div key={activeTab} className="tab-fade pt-6" role="tabpanel">
              {activeTab === "summary" && <SummaryTab a={a} entity={entity} />}
              {activeTab === "charts" && (
                <Suspense fallback={<Skeleton className="h-72 w-full" />}>
                  <TimeSeriesCharts riskHistory={risk_history} priceHistory={price_history} articles={articles} isTicker={isTicker} isMobile={isMobile} />
                </Suspense>
              )}
              {activeTab === "news" && <ArticleTable articles={articles} />}
              {activeTab === "analysts" && isTicker && <AnalystConsensus analyst={entity.analyst} price={entity.price} type={entity.type} stale={stale} />}
            </div>
          </div>
        )}
      </div>

      {/* ---- ASK AI ---- */}
      {a && isDesktop && chatOpen && (
        <aside className="sticky top-24">
          <ChatPanel entityId={entity.id} entityName={name} suggestions={suggestions} onClose={() => toggleChat(false)} className="h-[calc(100dvh-8rem)]" />
        </aside>
      )}
      {a && isDesktop && !chatOpen && (
        <Button variant="primary" icon={MessageSquare} onClick={() => toggleChat(true)} title={tt("chat.open")} className="fixed bottom-20 right-6 z-40 shadow-raised">
          {tt("chat.askAi")}
        </Button>
      )}
      {a && !isDesktop && (
        <>
          <Button variant="primary" icon={MessageSquare} onClick={() => setSheetOpen(true)} className="fixed bottom-[max(5rem,calc(env(safe-area-inset-bottom)+4rem))] right-[max(1rem,env(safe-area-inset-right))] z-40 shadow-raised">
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

// Özet sekmesi: (özel şirket notu) · "AI ne düşünüyor" · risk + özet + ana etkenler · doğrulanacaklar · geçersiz kılan.
function SummaryTab({ a, entity }) {
  const isPrivate = entity.type !== "ticker";
  return (
    <div className="space-y-6">
      {isPrivate && (
        <p className="flex items-start gap-2.5 text-meta text-slate-400">
          <Lock className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
          <span>
            <span className="font-medium text-slate-300">{tt("card.private")}.</span> {tt("card.privateBody")}
          </span>
        </p>
      )}

      {/* "AI ne düşünüyor?" — yükseltilmiş yüzey, solda ince vurgu çizgisi, rahat okunur metin. */}
      {a.ai_take && (
        <section className="relative overflow-hidden rounded-card bg-raised p-6 shadow-card ring-1 ring-ink-600">
          <span className="absolute inset-y-0 left-0 w-0.5 bg-accent" aria-hidden="true" />
          <h2 className="mb-3 flex items-center gap-2 font-display text-sm font-medium text-slate-200">
            <Sparkles className="h-4 w-4 text-accent" aria-hidden="true" /> {tt("sum.aiTake")}
          </h2>
          <p className="max-w-3xl text-base leading-relaxed text-slate-100">{a.ai_take}</p>
          <p className="mt-4 text-micro text-slate-500">{tt("sum.aiDisclaimer")}</p>
        </section>
      )}

      <div className="grid gap-6 md:grid-cols-3">
        <section className="md:col-span-2">
          <div className="mb-4 flex flex-wrap items-center gap-4">
            <RiskScore score={a.risk_score} />
            <RiskDelta delta={entity.delta} />
            <TrendArrow trend={a.sentiment_trend} />
            {entity.delta?.stance_changed && (
              <Chip tone="warn" icon={Zap}>
                {stanceLabel(entity.delta.previous_stance)} → {stanceLabel(a.stance)}
              </Chip>
            )}
          </div>
          <p className="text-body text-slate-200">{a.summary}</p>
          <p className="mt-2 text-micro text-slate-500">
            {tt("sum.basedOn", { n: a.articles_considered })} · {fmtDateTime(a.created_at)}
            {entity.previous_analysis && <> · {tt("sum.previous", { v: entity.previous_analysis.risk_score })}</>}
          </p>
          {a.top_drivers?.length > 0 && (
            <div className="mt-5">
              <h3 className="mb-2 text-micro font-medium text-slate-500">{tt("sum.drivers")}</h3>
              <div className="flex flex-wrap gap-2">
                {a.top_drivers.map((d, i) => (
                  <Chip key={i} tone="neutral" size="md" wrap>
                    {d}
                  </Chip>
                ))}
              </div>
            </div>
          )}
        </section>

        <div className="space-y-6">
          {a.what_to_verify?.length > 0 && (
            <section>
              <h3 className="mb-2 text-micro font-medium text-amber-600">{tt("sum.verify")}</h3>
              <ul className="space-y-2 text-meta text-slate-300">
                {a.what_to_verify.map((v, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-amber-500" aria-hidden="true" />
                    <span>{v}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {a.invalidation && (
            <section>
              <h3 className="mb-2 text-micro font-medium text-slate-500">{tt("sum.invalidation")}</h3>
              <p className="text-meta text-slate-300">{a.invalidation}</p>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
