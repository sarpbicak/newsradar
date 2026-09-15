// Entity detay: ÜSTTE sabit özet (ad · hüküm · sinyal · Yön/Vade/Kanıt · fiyat/hedef),
// ALTTA sekmeler (Özet / Grafikler / Haberler / Analistler). Her şey aynı ekranda değil.
import React, { useEffect, useState } from "react";
import { ChevronLeft, FileText, TrendingUp, Newspaper, BarChart3, Sparkles, Lock } from "lucide-react";
import { api } from "../api.js";
import {
  StanceBadge, RiskScore, RiskDelta, TrendArrow, PriceDisplay, stanceLabel,
  stanceColor, horizonLabel, evidenceLabel, evidenceColor, SignalBand, useIsMobile,
} from "./ui.jsx";
import ArticleTable from "./ArticleTable.jsx";
import ChatPanel from "./ChatPanel.jsx";
import TimeSeriesCharts from "./TimeSeriesCharts.jsx";
import AnalystConsensus from "./AnalystConsensus.jsx";

function MiniStat({ label, value, color }) {
  return (
    <div className="px-1 py-2 text-center">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-sm font-bold" style={color ? { color } : undefined}>{value}</div>
    </div>
  );
}

export default function EntityDetail({ entityId, onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("summary");
  const isMobile = useIsMobile();

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
  }, [entityId]);

  if (loading) return <div className="p-8 text-slate-500">Yükleniyor…</div>;
  if (error) return <div className="p-8 text-rose-400">Hata: {error}</div>;
  if (!data) return null;

  const { entity, articles, risk_history, price_history, article_status: st } = data;
  const a = entity.analysis;
  const isTicker = entity.type === "ticker";
  const dir = a ? stanceColor(a.stance) : "#8B8F9E";
  const upside = entity.analyst?.upside_percent;

  const tabs = [
    { key: "summary", label: "Özet", icon: FileText },
    { key: "charts", label: "Grafikler", icon: TrendingUp },
    { key: "news", label: "Haberler", icon: Newspaper },
    ...(isTicker ? [{ key: "analysts", label: "Analistler", icon: BarChart3 }] : []),
  ];
  const activeTab = tabs.some((t) => t.key === tab) ? tab : "summary";

  return (
    /* pb-24 (mobil): alttaki SABİT sekme çubuğu içeriği örtmesin. Masaüstünde çubuk
       yukarıda olduğu için ekstra boşluk yok. */
    <div className="space-y-5 pb-24 md:pb-0">
      <button
        onClick={onBack}
        className="inline-flex min-h-[44px] items-center gap-1 rounded-lg pr-3 text-sm text-slate-500 transition hover:text-slate-200"
      >
        <ChevronLeft className="h-4 w-4" /> genel görünüm
      </button>

      {/* ---- ÜST SABİT ÖZET ---- */}
      <div className="rounded-2xl border border-ink-600 bg-ink-800 p-5 shadow-card">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h2 className="font-display text-2xl font-bold text-slate-100">{entity.name}</h2>
          <span className="font-mono text-sm text-slate-500">
            {isTicker ? "$" : "#"}{entity.query}
          </span>
          {a && <StanceBadge stance={a.stance} conviction={a.conviction} />}
          {a && <TrendArrow trend={a.sentiment_trend} />}
          {a && entity.delta?.stance_changed && (
            <span className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs font-bold text-amber-200">
              ⚡ {stanceLabel(entity.delta.previous_stance)} → {stanceLabel(a.stance)}
            </span>
          )}
        </div>

        {a?.headline_verdict && (
          <p className="mt-3 font-serif text-2xl font-semibold leading-snug text-slate-100">
            {a.headline_verdict}
          </p>
        )}

        {a && (
          <div className="mt-4 max-w-md">
            <SignalBand stance={a.stance} evidence={entity.evidence_strength} />
          </div>
        )}

        {a && (
          <div className="mt-4 grid grid-cols-3 divide-x divide-ink-700 rounded-lg border border-ink-700">
            <MiniStat label="Yön" value={stanceLabel(a.stance)} color={dir} />
            <MiniStat label="Vade" value={horizonLabel(entity.horizon)} />
            <MiniStat
              label="Kanıt"
              value={evidenceLabel(entity.evidence_strength)}
              color={evidenceColor(entity.evidence_strength)}
            />
          </div>
        )}

        {/* Fiyat → hedef → % (ticker) VEYA borsada işlem görmüyor (keyword) */}
        <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          {isTicker ? (
            entity.price != null ? (
              <>
                <PriceDisplay
                  price={entity.price}
                  changePercent={entity.change_percent}
                  updatedAt={entity.price_updated_at}
                />
                {entity.analyst?.target_mean != null && (
                  <span className="inline-flex items-baseline gap-1.5 text-slate-400">
                    <span className="text-slate-600">·</span> hedef
                    <span className="font-semibold text-slate-100">${entity.analyst.target_mean.toFixed(2)}</span>
                    {upside != null && (
                      <span className={`font-semibold ${upside >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                        · {upside >= 0 ? "+" : "−"}%{Math.abs(Math.round(upside))}
                      </span>
                    )}
                  </span>
                )}
              </>
            ) : (
              <span className="text-slate-500">Fiyat verisi yok (ABD dışı borsa olabilir).</span>
            )
          ) : (
            <span className="text-slate-500">Borsada işlem görmüyor (özel şirket).</span>
          )}
        </div>

        {/* Makale durum sayacı — küçük teşhis satırı */}
        {st && (
          <div
            className={`mt-4 flex flex-wrap items-center gap-x-2 rounded-lg px-3 py-1.5 font-mono text-[11px] ${
              st.pending > 0 && st.analyzed === 0
                ? "bg-amber-500/10 text-amber-200"
                : "bg-ink-700/60 text-slate-500"
            }`}
          >
            <span>{st.total} makale</span>·<span>{st.analyzed} analiz</span>·
            <span>{st.prefiltered} elenen</span>·
            <span className={st.pending > 0 ? "font-semibold text-slate-300" : ""}>{st.pending} bekliyor</span>
          </div>
        )}
      </div>

      {!a ? (
        <div className="rounded-xl border border-ink-600 bg-ink-800 p-6 text-slate-400">
          Bu varlık için henüz analiz yok. Üstteki <strong>Yenile</strong> düğmesine basın.
        </div>
      ) : (
        <>
          {/* ---- SEKME ÇUBUĞU ----
              MOBİL: ekranın ALTINDA sabit (başparmakla tek elle erişim).
              MASAÜSTÜ: içeriğin üstünde normal akışta. */}
          <div className="fixed inset-x-0 bottom-0 z-30 flex gap-1 border-t border-ink-500 bg-ink-800/95 p-1 pb-[max(0.25rem,env(safe-area-inset-bottom))] shadow-[0_-4px_16px_rgba(0,0,0,0.06)] backdrop-blur-md md:static md:rounded-xl md:border md:border-ink-600 md:pb-1 md:shadow-none md:backdrop-blur-none">
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

          {/* Sohbet — her sekmenin altında (bağlamdan kopmasın) */}
          <ChatPanel entityId={entity.id} entityName={entity.name} />
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
              Özel şirket — borsada işlem görmüyor
            </div>
            <p className="mt-0.5 text-[13px] leading-relaxed text-slate-400">
              {entity.name} halka açık olmadığı için fiyat ve analist hedefi yok.
              Aşağıdaki değerlendirme yalnızca haber akışına dayanıyor.
            </p>
          </div>
        </div>
      )}

      {/* "AI ne düşünüyor?" — bütünsel yorum (varsa) */}
      {a.ai_take && (
        <div className="rounded-xl border border-accent/30 bg-accent/10 p-5">
          <div className="mb-2 flex items-center gap-2 font-display text-sm font-semibold text-accent">
            <Sparkles className="h-4 w-4" /> AI ne düşünüyor?
          </div>
          <p className="text-[15px] leading-relaxed text-slate-100">{a.ai_take}</p>
          <p className="mt-3 text-[11px] text-slate-500">
            Bu bir yorum, yatırım tavsiyesi değil — kararlar sana ait.
          </p>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-3">
      <div className="rounded-xl border border-ink-600 bg-ink-800 p-5 md:col-span-2">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <RiskScore score={a.risk_score} />
          <RiskDelta delta={entity.delta} />
          <div className="text-xs text-slate-500">
            {a.articles_considered} habere dayalı · {new Date(a.created_at).toLocaleString("tr-TR")}
            {entity.previous_analysis && <> · önceki: {entity.previous_analysis.risk_score}</>}
          </div>
        </div>
        <p className="text-sm leading-relaxed text-slate-200">{a.summary}</p>

        {a.top_drivers?.length > 0 && (
          <div className="mt-4">
            <div className="mb-1.5 text-[11px] uppercase tracking-wide text-slate-500">Ana etkenler</div>
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
            ✓ Harekete geçmeden önce doğrula
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
            Görüşü çürütecek olay
          </div>
          <p className="text-sm text-slate-300">{a.invalidation}</p>
        </div>
      </div>
      </div>
    </div>
  );
}
