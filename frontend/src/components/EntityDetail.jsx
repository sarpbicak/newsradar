// Entity detay — her bilgi TEK yerde:
//   Başlık: ad + ticker + TEK durum etiketi (yön · güç) → hüküm cümlesi → tek fiyat bloğu
//   (fiyat · günlük % → analist hedefi · %, hedef tarihi küçük) → soluk meta satırı.
//   Altta sekmeler (Özet / Grafikler / Haberler / Analistler). Hat sayaçları yalnızca admin.
//   Sohbet: masaüstünde (≥1024px) sağda sticky yan panel (kapatılabilir, tercih
//   localStorage'da); mobilde sağ altta "AI'ya sor" → bottom sheet.
import React, { useEffect, useState } from "react";
import { ChevronLeft, FileText, TrendingUp, Newspaper, BarChart3, Sparkles, Lock, MessageSquare } from "lucide-react";
import { api } from "../api.js";
import {
  RiskScore, RiskDelta, TrendArrow, PriceDisplay, StatusTag, stanceLabel, horizonLabel, useIsMobile,
} from "./ui.jsx";
import ArticleTable from "./ArticleTable.jsx";
import ChatPanel from "./ChatPanel.jsx";
import TimeSeriesCharts from "./TimeSeriesCharts.jsx";
import AnalystConsensus from "./AnalystConsensus.jsx";
import { tt, fmtDate, fmtDateTime, fmtInt, fmtPct, getLang, parseUtc } from "../i18n.jsx";

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
  const qs = [tt("chat.qWhy", { name: entity.name, stance: stanceLabel(a.stance).toLowerCase() })];
  if (entity.type === "ticker" && entity.analyst?.target_mean != null) qs.push(tt("chat.qGap"));
  else qs.push(tt("chat.qRisk", { name: entity.name }));
  qs.push(tt("chat.qWatch"));
  return qs;
}

// Tek fiyat bloğu: $214.13 −1.43% → hedef $339.17 +58% · "analist hedefi, 1 Eyl" (küçük).
// Hedef verisi 30 günden eskiyse hedef satırı SOLUK TONDA (slate-500 — AA'yı geçer; opacity
// ile soluklaştırmak kontrastı 4.5'in altına düşürüyordu) + açıklayıcı title.
function PriceBlock({ entity }) {
  const an = entity.analyst;
  const hasTarget = an?.target_mean != null;
  const asOf = an?.fetched_at ? parseUtc(an.fetched_at) : null;
  const stale = asOf ? (Date.now() - asOf.getTime()) / 86400000 > TARGET_STALE_DAYS : false;
  const up = an?.upside_percent;
  return (
    <div className="mt-3 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
      <PriceDisplay price={entity.price} changePercent={entity.change_percent} showTime={false} />
      {hasTarget && (
        <span className="inline-flex flex-wrap items-baseline gap-x-1.5" title={stale ? tt("detail.targetStale") : undefined}>
          <span className="text-slate-500">→ {tt("detail.target")}</span>
          <span className={`font-mono font-semibold ${stale ? "text-slate-500" : "text-slate-100"}`}>${an.target_mean.toFixed(2)}</span>
          {up != null && (
            <span className={`font-mono text-xs font-semibold ${stale ? "text-slate-500" : up >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {fmtPct(up)}
            </span>
          )}
          {asOf && (
            <span className="text-[11px] text-slate-500">· {tt("detail.targetAsOf", { date: fmtDate(an.fetched_at) })}</span>
          )}
        </span>
      )}
    </div>
  );
}

// "Bu değerlendirme İngilizce üretildi" — gösterilen analizin dili UI dilinden farklıysa.
function LangNote({ analysisLang }) {
  if (!analysisLang || analysisLang === getLang()) return null;
  const name = tt(analysisLang === "tr" ? "lang.tr.name" : "lang.en.name");
  return (
    <p className="mt-1.5 text-[11px] italic text-slate-500">
      {tt("detail.langNote", { lang: name })}
    </p>
  );
}

export default function EntityDetail({ entityId, lang, onBack, isAdmin = false }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("summary");
  const isMobile = useIsMobile();
  const isDesktop = !useIsMobile(1024);
  const [chatOpen, setChatOpen] = useState(readChatPref);   // masaüstü yan panel
  const [sheetOpen, setSheetOpen] = useState(false);        // mobil bottom sheet
  const toggleChat = (open) => {
    setChatOpen(open);
    writeChatPref(open);
  };

  // entityId ya da DİL değişince yeniden çek — dil değişiminde AI içeriği (dashboard)
  // yeni dilde gelsin. (App önce POST /users/me/language'i bekler; bu efekt sonra çalışır.)
  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .dashboard(entityId)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [entityId, lang]);

  if (loading) return <div className="p-8 text-slate-500">{tt("detail.loading")}</div>;
  if (error) return <div className="p-8 text-rose-400">{tt("detail.error", { msg: error })}</div>;
  if (!data) return null;

  const { entity, articles, risk_history, price_history, article_status: st } = data;
  const a = entity.analysis;
  const isTicker = entity.type === "ticker";
  const suggestions = chatSuggestions(entity);

  const tabs = [
    { key: "summary", label: tt("detail.tabSummary"), icon: FileText },
    { key: "charts", label: tt("detail.tabCharts"), icon: TrendingUp },
    { key: "news", label: tt("detail.tabNews"), icon: Newspaper },
    ...(isTicker ? [{ key: "analysts", label: tt("detail.tabAnalysts"), icon: BarChart3 }] : []),
  ];
  const activeTab = tabs.some((t) => t.key === tab) ? tab : "summary";

  return (
    /* pb-24 (mobil): alttaki SABİT sekme çubuğu içeriği örtmesin. Masaüstünde çubuk
       yukarıda olduğu için ekstra boşluk yok. */
    <div className={isDesktop && a && chatOpen ? "grid grid-cols-[minmax(0,1fr)_380px] items-start gap-6" : ""}>
    <div className="min-w-0 space-y-5 pb-24 md:pb-0">
      <button
        onClick={onBack}
        className="inline-flex min-h-[44px] items-center gap-1 rounded-lg pr-3 text-sm text-slate-500 transition hover:text-slate-200"
      >
        <ChevronLeft className="h-4 w-4" /> {tt("detail.back")}
      </button>

      {/* ---- BAŞLIK: ad + ticker + tek durum etiketi · hüküm · fiyat · meta ---- */}
      <div className="rounded-2xl border border-ink-600 bg-ink-800 p-5 shadow-card">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h2 className="font-display text-2xl font-bold text-slate-100">{entity.name}</h2>
          <span className="font-mono text-sm text-slate-500">
            {isTicker ? "$" : "#"}{entity.query}
          </span>
          {a && <StatusTag stance={a.stance} evidence={entity.evidence_strength} />}
        </div>

        {a?.headline_verdict && (
          <p className="mt-3 font-display text-2xl font-semibold leading-snug text-slate-100">
            {a.headline_verdict}
          </p>
        )}
        {a && <LangNote analysisLang={entity.analysis_language} />}

        {isTicker ? (
          entity.price != null ? (
            <PriceBlock entity={entity} />
          ) : (
            <p className="mt-3 text-sm text-slate-500">{tt("detail.noPrice")}</p>
          )
        ) : (
          <p className="mt-3 text-sm text-slate-500">{tt("detail.notPublic")}</p>
        )}

        {/* Meta: küçük ve soluk */}
        {a && (
          <p className="mt-2 text-[11px] text-slate-500">
            {entity.horizon && <>{tt("detail.metaHorizon", { h: horizonLabel(entity.horizon) })} · </>}
            {(() => {
              const n = st?.analyzed ?? entity.evidence_count ?? 0;
              return tt("detail.metaArticles", { n, count: fmtInt(n) });
            })()}
          </p>
        )}

        {/* Hat sayaçları (teşhis) — YALNIZCA admin */}
        {isAdmin && st && (
          <p className="mt-1 font-mono text-[10px] text-slate-500" title={tt("detail.pipelineAdmin")}>
            {tt("detail.pipelineAdmin")}: {tt("detail.articlesN", { n: st.total })} · {tt("detail.analyzedN", { n: st.analyzed })} ·{" "}
            {tt("detail.prefilteredN", { n: st.prefiltered })} · {tt("detail.pendingN", { n: st.pending })} ·{" "}
            {tt("detail.expiredN", { n: st.expired ?? 0 })}
          </p>
        )}
      </div>

      {!a ? (
        <div className="rounded-xl border border-ink-600 bg-ink-800 p-6 text-slate-400">
          {tt("detail.noAnalysisBox", { refresh: tt("header.refresh") })}
        </div>
      ) : (
        <>
          {/* ---- SEKME ÇUBUĞU ----
              MOBİL: ekranın ALTINDA sabit (başparmakla tek elle erişim).
              MASAÜSTÜ: içeriğin üstünde normal akışta. */}
          <div className="fixed inset-x-0 bottom-0 z-30 flex gap-1 border-t border-ink-500 bg-ink-800/95 p-1 pb-[max(0.25rem,env(safe-area-inset-bottom))] shadow-[0_-4px_16px_rgb(var(--slate-100)/0.06)] backdrop-blur-md md:static md:rounded-xl md:border md:border-ink-600 md:pb-1 md:shadow-none md:backdrop-blur-none">
            {tabs.map((t) => {
              const Icon = t.icon;
              const on = activeTab === t.key;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`inline-flex min-h-[52px] flex-1 flex-col items-center justify-center gap-0.5 whitespace-nowrap rounded-lg px-2 text-[11px] font-medium transition md:min-h-[40px] md:flex-row md:gap-1.5 md:text-sm ${
                    on ? "bg-accent/20 text-accent" : "text-slate-400 hover:bg-ink-700 hover:text-slate-200"
                  }`}
                >
                  <Icon className="h-5 w-5 md:h-4 md:w-4" /> {t.label}
                </button>
              );
            })}
          </div>

          {/* ---- SEKME İÇERİĞİ ---- */}
          <div key={activeTab} className="tab-fade">
            {activeTab === "summary" && <SummaryTab a={a} entity={entity} />}
            {activeTab === "charts" && (
              <TimeSeriesCharts
                riskHistory={risk_history}
                priceHistory={price_history}
                articles={articles}
                isTicker={isTicker}
                isMobile={isMobile}
              />
            )}
            {activeTab === "news" && <ArticleTable articles={articles} />}
            {activeTab === "analysts" && isTicker && (
              <AnalystConsensus analyst={entity.analyst} price={entity.price} type={entity.type} />
            )}
          </div>

        </>
      )}
    </div>

      {/* ---- SOHBET ---- */}
      {a && isDesktop && chatOpen && (
        <aside className="sticky top-20">
          <ChatPanel
            entityId={entity.id}
            entityName={entity.name}
            suggestions={suggestions}
            onClose={() => toggleChat(false)}
            className="h-[calc(100vh-11rem)]"
          />
        </aside>
      )}
      {a && isDesktop && !chatOpen && (
        <button
          onClick={() => toggleChat(true)}
          className="fixed bottom-24 right-6 z-40 flex min-h-[44px] items-center gap-2 rounded-full bg-accent px-4 text-sm font-semibold text-accent-fg shadow-card transition hover:bg-accent-hover"
          title={tt("chat.open")}
        >
          <MessageSquare className="h-4 w-4" /> {tt("chat.askAi")}
        </button>
      )}
      {a && !isDesktop && (
        <>
          <button
            onClick={() => setSheetOpen(true)}
            className="fixed bottom-[124px] right-4 z-40 flex min-h-[44px] items-center gap-2 rounded-full bg-accent px-4 text-sm font-semibold text-accent-fg shadow-card md:bottom-20 md:right-6"
          >
            <MessageSquare className="h-4 w-4" /> {tt("chat.askAi")}
          </button>
          {sheetOpen && (
            <div
              className="fixed inset-0 z-50 flex items-end bg-black/30 backdrop-blur-sm"
              onClick={(e) => e.target === e.currentTarget && setSheetOpen(false)}
            >
              <div className="w-full rounded-t-2xl bg-ink-900 p-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] shadow-card-hover">
                <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-ink-500" />
                <ChatPanel
                  entityId={entity.id}
                  entityName={entity.name}
                  suggestions={suggestions}
                  onClose={() => setSheetOpen(false)}
                  className="h-[75vh]"
                />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// Özet sekmesi: (özel şirket notu) + AI yorumu (üstte) + risk + özet + ana etkenler + doğrulama + invalidation.
function SummaryTab({ a, entity }) {
  const isPrivate = entity.type !== "ticker";
  return (
    <div className="space-y-4">
      {/* Özel şirket açıklaması — kartla aynı; neden fiyat/analist verisi olmadığını söyler */}
      {isPrivate && (
        <div className="flex items-start gap-2.5 rounded-xl border border-ink-600 bg-ink-800 p-4">
          <Lock className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
          <div>
            <div className="text-sm font-semibold text-slate-200">
              {tt("card.private")}
            </div>
            <p className="mt-0.5 text-[13px] leading-relaxed text-slate-400">
              {tt("card.privateBody")}
            </p>
          </div>
        </div>
      )}

      {/* "AI ne düşünüyor?" — bütünsel yorum (varsa) */}
      {a.ai_take && (
        <div className="rounded-xl border border-accent/30 bg-accent/10 p-5">
          <div className="mb-2 flex items-center gap-2 font-display text-sm font-semibold text-accent">
            <Sparkles className="h-4 w-4" /> {tt("sum.aiTake")}
          </div>
          <p className="text-[15px] leading-relaxed text-slate-100">{a.ai_take}</p>
          <p className="mt-3 text-[11px] text-slate-500">
            {tt("sum.aiDisclaimer")}
          </p>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-3">
      <div className="rounded-xl border border-ink-600 bg-ink-800 p-5 md:col-span-2">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <RiskScore score={a.risk_score} />
          <RiskDelta delta={entity.delta} />
          <TrendArrow trend={a.sentiment_trend} />
          {entity.delta?.stance_changed && (
            <span className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs font-bold text-amber-200">
              ⚡ {stanceLabel(entity.delta.previous_stance)} → {stanceLabel(a.stance)}
            </span>
          )}
          <div className="text-xs text-slate-500">
            {tt("sum.basedOn", { n: a.articles_considered })} · {fmtDateTime(a.created_at)}
            {entity.previous_analysis && <> · {tt("sum.previous", { v: entity.previous_analysis.risk_score })}</>}
          </div>
        </div>
        <p className="text-sm leading-relaxed text-slate-200">{a.summary}</p>

        {a.top_drivers?.length > 0 && (
          <div className="mt-4">
            <div className="mb-1.5 text-[11px] uppercase tracking-wide text-slate-500">{tt("sum.drivers")}</div>
            <div className="flex flex-wrap gap-2">
              {a.top_drivers.map((d, i) => (
                <span key={i} className="rounded-md border border-ink-500 bg-ink-700 px-2.5 py-1 text-xs text-slate-300">
                  {d}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="space-y-4">
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-amber-300">
            {tt("sum.verify")}
          </div>
          <ul className="space-y-2 text-sm text-slate-300">
            {a.what_to_verify.map((v, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-amber-400">▸</span>
                <span>{v}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {tt("sum.invalidation")}
          </div>
          <p className="text-sm text-slate-300">{a.invalidation}</p>
        </div>
      </div>
      </div>
    </div>
  );
}
