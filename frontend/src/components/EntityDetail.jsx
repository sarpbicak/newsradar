// Entity detay görünümü: özet, yön+kanaat, etkenler, 'önce doğrula' listesi,
// invalidation, makale tablosu ve sohbet paneli.
import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { StanceBadge, RiskScore, RiskDelta, TrendArrow, PriceDisplay, stanceLabel, SignalBand, InfoTip, TERM_HELP } from "./ui.jsx";
import ArticleTable from "./ArticleTable.jsx";
import ChatPanel from "./ChatPanel.jsx";
import SentimentChart from "./SentimentChart.jsx";
import RiskHistoryChart from "./RiskHistoryChart.jsx";
import PriceHistoryChart from "./PriceHistoryChart.jsx";
import AnalystConsensus from "./AnalystConsensus.jsx";

export default function EntityDetail({ entityId, onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

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

  return (
    <div className="space-y-6">
      <button onClick={onBack} className="text-sm text-slate-400 hover:text-slate-200">
        ← genel görünüm
      </button>

      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-semibold text-slate-100">{entity.name}</h2>
        <span className="font-mono text-sm text-slate-500">
          {entity.type === "ticker" ? "$" : "#"}
          {entity.query}
        </span>
        {a && <StanceBadge stance={a.stance} conviction={a.conviction} />}
        {a && <TrendArrow trend={a.sentiment_trend} />}
        {a && entity.delta?.stance_changed && (
          <span className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs font-bold text-amber-200">
            ⚡ {stanceLabel(entity.delta.previous_stance)} → {stanceLabel(a.stance)}
          </span>
        )}
        {entity.price != null && (
          <span className="ml-auto">
            <PriceDisplay
              price={entity.price}
              changePercent={entity.change_percent}
              updatedAt={entity.price_updated_at}
            />
          </span>
        )}
      </div>

      {/* Makale durum sayacı — teşhis için: 'çekildi ama analiz edilmedi' bir bakışta görünsün.
          Bekleyen varken hiç analiz yoksa (takılma sinyali) vurgulu göster. */}
      {st && (
        <div
          className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-3 py-2 font-mono text-xs ${
            st.pending > 0 && st.analyzed === 0
              ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
              : "border-ink-600 bg-ink-800 text-slate-400"
          }`}
          title="Bekleyen makaleler bir sonraki yenilemede işlenir (yenileme başına en fazla tavan kadar)."
        >
          <span>{st.total} makale</span>
          <span className="text-slate-600">·</span>
          <span>{st.analyzed} analiz</span>
          <span className="text-slate-600">·</span>
          <span>{st.prefiltered} elenen</span>
          <span className="text-slate-600">·</span>
          <span className={st.pending > 0 ? "font-semibold" : ""}>{st.pending} bekliyor</span>
          {st.pending > 0 && st.analyzed === 0 && (
            <span className="ml-1 not-italic">— Yenile'ye basın; her yenileme bir grup işler.</span>
          )}
        </div>
      )}

      {a?.headline_verdict && (
        <p className="text-xl font-semibold leading-snug text-slate-100">{a.headline_verdict}</p>
      )}

      {/* Genel sinyal bandı — yön + kanıtı tek görsele indirger */}
      {a && (
        <div className="max-w-md">
          <SignalBand stance={a.stance} evidence={entity.evidence_strength} />
        </div>
      )}

      {!a ? (
        <div className="rounded-xl border border-ink-600 bg-ink-800 p-6 text-slate-400">
          Bu varlık için henüz analiz yok. Üstteki <strong>Yenile</strong> düğmesine basın
          (Claude ve haber anahtarları gerektirir).
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-xl border border-ink-600 bg-ink-800 p-4 md:col-span-2">
            <div className="mb-2 flex items-center gap-3">
              <RiskScore score={a.risk_score} />
              <InfoTip text={TERM_HELP.risk} />
              <RiskDelta delta={entity.delta} />
              <div className="text-xs text-slate-500">
                {a.articles_considered} habere dayalı · {new Date(a.created_at).toLocaleString("tr-TR")}
                {entity.previous_analysis && (
                  <> · önceki: {entity.previous_analysis.risk_score}</>
                )}
              </div>
            </div>
            <p className="text-sm leading-relaxed text-slate-200">{a.summary}</p>

            {a.top_drivers?.length > 0 && (
              <div className="mt-3">
                <div className="mb-1 text-[11px] uppercase text-slate-500">Ana etkenler</div>
                <div className="flex flex-wrap gap-2">
                  {a.top_drivers.map((d, i) => (
                    <span key={i} className="rounded-md border border-ink-500 bg-ink-700 px-2 py-1 text-xs text-slate-300">
                      {d}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
              <div className="mb-2 text-[11px] font-semibold uppercase text-amber-300">
                ✓ Harekete geçmeden önce doğrula
              </div>
              <ul className="space-y-1.5 text-sm text-slate-300">
                {a.what_to_verify.map((v, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-amber-400">▸</span>
                    <span>{v}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
              <div className="mb-1 text-[11px] font-semibold uppercase text-slate-500">
                Görüşü çürütecek olay
              </div>
              <p className="text-sm text-slate-300">{a.invalidation}</p>
            </div>
          </div>
        </div>
      )}

      {/* Analist konsensüsü — veri varsa tam gösterim, yoksa NEDEN yok açıklaması */}
      <AnalystConsensus analyst={entity.analyst} price={entity.price} type={entity.type} />

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Risk üstte, fiyat altta — aynı tarih ekseninde okunur */}
        <div className="space-y-4">
          <RiskHistoryChart history={risk_history} />
          <PriceHistoryChart
            history={price_history}
            updatedAt={entity.price_updated_at}
            isTicker={entity.type === "ticker"}
          />
        </div>
        <SentimentChart articles={articles} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <h3 className="mb-3 text-sm font-semibold text-slate-300">Analiz edilmiş haberler</h3>
          <ArticleTable articles={articles} />
        </div>
        <div>
          <ChatPanel entityId={entity.id} entityName={entity.name} />
        </div>
      </div>
    </div>
  );
}
