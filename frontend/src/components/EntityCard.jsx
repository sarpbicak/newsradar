// Pano kartı, yukarıdan aşağı: ad/sembol · haber etiketi (+ yön değiştiyse küçük işaret) ve vade
// seçici · hüküm cümlesi · fiyat ("$372.22 −0,63% bugün", tek satır) · kompakt skala (başlığında
// "54 analist · hedef $442 (+%19)") · ayrışma notu (varsa). Alt grup en alta yapışır; aynı
// satırdaki kartlar eşit yükseklikte. Makale sayısı yalnızca detayda.
// Renk göstergesi: üst kenarda ince (2px) anlamsal çizgi. Kısa ad: display_name, yoksa ad
// (iki satıra kadar sarar, asla kesilmez).
import React from "react";
import { Activity, ArrowLeftRight, Compass, GitFork, Lock, RotateCw, TrendingUp, Zap } from "lucide-react";
import {
  AnimatedNumber, HorizonToggle, NewsPill, divergenceText, hasHorizons, newsSignal, riskColor, stanceLabel, targetOf,
  useHorizon,
} from "./ui.jsx";
import { Card, Chip, cx } from "./kit.jsx";
import { tt, fmtPct, getLang, localeOf, parseUtc } from "../i18n.jsx";
import { SignalScaleCompact, TargetInline } from "./SignalScale.jsx";
import { exchangeName } from "../appStrings.js";
import { fmtMoney } from "../money.js";
import { C } from "../theme.js";

// Analiz yoksa NEDEN: dil eksik · bekleyen haber var (yenileme işe yarar) · pencerede haber yok
// (yenileme işe yaramaz; yeni haber çıkınca kendiliğinden güncellenir). short: liste satırı.
// Haber kaynağı geçici olarak kullanılamıyor (GDELT devre kesici): tek, sakin not; mevcut haberler
// görünmeye devam eder. Yenileme özetinde ayrıca uyarı çıkmaz.
export function NewsPausedNote({ className = "" }) {
  return <p className={cx("text-micro text-slate-500", className)}>{tt("card.newsPaused")}</p>;
}

export function noAnalysisText(card, short = false) {
  if (card.analysis_missing_language) return tt("card.langMissing");
  if (card.no_analysis_reason === "few_news") return tt("card.fewNews", { days: card.news_window_days ?? 2 });
  return short ? tt("card.noAnalysisYet") : tt("card.pressRefresh", { refresh: tt("header.refresh") });
}

export const displayName = (e) => e.display_name || e.name;
export const symbolOf = (e) => `${e.type === "ticker" ? "$" : "#"}${e.query}`;
// ABD dışı hissede borsa · ülke ("XETRA · Almanya"); ABD ve keyword'de null (gürültü olmasın).
// Borsa adı kullanıcının dilinde (pazar kodu → exchange.<kod>); bilinmeyen kodda backend'in adı.
export const exchangeOf = (e) => exchangeName(e.market, e.exchange);
export const marketLabel = (e) => (e.us_market === false && e.exchange ? `${exchangeOf(e)} · ${e.country}` : null);

// "yön 24 Eki'de değişti" / "direction changed on 24 Oct" / "Richtung am 24. Okt. geändert".
// Türkçede bulunma eki ayın tam adının okunuşuna göre (Ekim'de, Kasım'da, Aralık'ta).
const TR_LOC = { oca: "ta", şub: "ta", mar: "ta", nis: "da", may: "ta", haz: "da", tem: "da", ağu: "ta", eyl: "de", eki: "de", kas: "da", ara: "ta" };
// Yön değişikliği: haber etiketinin yanında küçük işaret (↻); ipucunda tarih ve önceki → yeni
// yön, ekran okuyucuya aynı metin. Tarih yoksa (eski API) tarihsiz.
export function StanceMark({ delta, stance, className = "" }) {
  const when = delta?.changed_at ? changedOnText(delta.changed_at) : tt("card.directionChangedNoDate");
  const dirs = delta?.previous_stance ? tt("card.directionChangedTip", { from: stanceLabel(delta.previous_stance), to: stanceLabel(stance) }) : "";
  const text = dirs ? `${when} · ${dirs}` : when;
  return (
    <span className={cx("relative z-10 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-control text-amber-600", className)} title={text}>
      <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
      <span className="sr-only">{text}</span>
    </span>
  );
}

export function changedOnText(iso) {
  const lang = getLang();
  const d = parseUtc(iso);
  const label = d.toLocaleDateString(lang === "en" ? "en-GB" : localeOf(lang), { day: "numeric", month: "short" });
  if (lang !== "tr") return tt("card.directionChanged", { date: label });
  const m = label.split(" ").pop().toLocaleLowerCase("tr-TR").replace(".", "");
  return tt("card.directionChanged", { date: `${label}'${TR_LOC[m] || "de"}` });
}

// Fiyat satırı (kart, detay aynı dil): "$372.22 −0,63% bugün", tek satır, alt etiket yok.
// Analist hedefi burada değil, skalanın başlığında / altında.
export function PriceRow({ entity, size = "md" }) {
  const price = entity.price;
  const chg = entity.change_percent;
  // ABD dışı borsa: fiyat/analist kaynağı yok (yuva boş) → borsayı adıyla söyle.
  if (price == null) {
    return (
      <p className="text-meta text-slate-500">
        {entity.us_market === false ? tt("card.noPriceExchange", { exchange: exchangeOf(entity) }) : tt("card.noPrice")} · {tt("card.newsOnly")}
      </p>
    );
  }
  // Fiyat kendi para biriminde, dile uygun ondalıkla (dönüşüm yok).
  const cur = entity.currency || "USD";
  const lang = getLang();
  return (
    <p className={cx("flex flex-wrap items-baseline gap-x-2 tabular-nums", size === "lg" ? "text-title" : "text-body")}>
      <span className="font-semibold text-slate-100">
        <AnimatedNumber value={price} format={(v) => fmtMoney(v, cur, lang)} />
      </span>
      {chg != null && <span className={cx("text-meta font-medium", chg >= 0 ? "text-emerald-600" : "text-rose-600")}>{fmtPct(chg, { digits: 2 })}</span>}
      <span className="text-meta text-slate-500">{tt("card.today")}</span>
    </p>
  );
}


function PrivateLine({ drivers }) {
  return (
    <div className="space-y-1.5">
      <p className="flex items-center gap-1.5 text-meta text-slate-400">
        <Lock className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
        {tt("card.privateShort")}
      </p>
      {drivers?.[0] && (
        <p className="text-micro text-slate-500">
          <span className="font-medium">{tt("card.topDriver")}</span> <span className="text-slate-400">{drivers[0]}</span>
        </p>
      )}
    </div>
  );
}

// "Bugün önemli" nedeni (sert hareket, risk sıçraması…): genişte çip, darda ikon + açıklama.
const PRIORITY_ICON = { stance_reversed: ArrowLeftRight, stance_clarified: Compass, risk_jump: TrendingUp, sharp_move: Activity, divergence: GitFork };
function PriorityChip({ reason }) {
  const label = tt(`pr.${reason}`);
  const Icon = PRIORITY_ICON[reason] || Zap;
  return (
    <>
      <Chip tone="neutral" className="chip-full">{label}</Chip>
      <span className="chip-compact h-7 w-7 shrink-0 items-center justify-center rounded-control bg-ink-700 text-slate-300" title={label}>
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="sr-only">{label}</span>
      </span>
    </>
  );
}

export default function EntityCard({ card, onOpen }) {
  const a = card.analysis;
  const [horizon, setHorizon] = useHorizon();
  const edge = a ? newsSignal(a, card.evidence_strength, horizon).color : C.subtle;
  const changed = a && card.delta?.stance_changed;
  const diverge = a ? divergenceText(a, card.evidence_strength, card.analyst, horizon) : null;
  // Ayrışma notu görünüyorsa aynı bilgiyi taşıyan "ayrışma" çipi tekrarlanmaz.
  const priority = diverge && card.priority_reason === "divergence" ? null : card.priority_reason;
  const open = () => onOpen(card.id);
  return (
    // Kart düz bir kutu: fareyle her yeri açar; klavye/ekran okuyucu için tüm kartı kaplayan TEK
    // açma düğmesi var. Vade seçici bu düğmenin üstünde (iç içe etkileşimli öğe yok — axe).
    <Card interactive onClick={open} className="card-cq relative flex h-full flex-col gap-4 overflow-hidden p-5 text-left md:p-6">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          open();
        }}
        aria-label={tt("card.openDetail", { name: displayName(card) })}
        className="absolute inset-0 rounded-card focus-visible:[outline-offset:-2px]"
      />
      <span className="absolute inset-x-0 top-0 h-0.5" style={{ background: edge }} aria-hidden="true" />

      {/* Başlık: sabit en az yükseklik (iki satırlık ad + sembol) → hüküm her kartta aynı hizada. */}
      <div className="flex min-h-14 items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="break-words font-display text-base font-medium leading-tight text-slate-100">{displayName(card)}</div>
          <div className="mt-1 text-micro text-slate-500">
            {symbolOf(card)}
            {marketLabel(card) && <span> · {exchangeOf(card)}</span>}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {!a && <Chip tone="muted">{tt(card.analysis_missing_language ? "card.langMissingShort" : "card.noAnalysis")}</Chip>}
          {priority && <PriorityChip reason={priority} />}
        </div>
      </div>
      {a && (
        <div className="-mt-1 flex flex-wrap items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-1">
            <NewsPill a={a} evidence={card.evidence_strength} horizon={horizon} />
            {changed && <StanceMark delta={card.delta} stance={a.stance} />}
          </span>
          {hasHorizons(a) && <HorizonToggle value={horizon} onChange={setHorizon} compact className="relative z-10" />}
        </div>
      )}

      {a ? (
        <>
          <p className="font-display text-title font-medium text-slate-100">{a.headline_verdict || a.summary}</p>
          <div className="mt-auto space-y-3">
            {card.type === "ticker" ? (
              <>
                <PriceRow entity={card} />
                {card.analyst?.total > 0 ? (
                  <SignalScaleCompact a={a} entity={card} horizon={horizon} />
                ) : (
                  targetOf(card.analyst) != null && (
                    <p className="text-micro text-slate-500"><TargetInline analyst={card.analyst} currency={card.currency} label="card.analystTargetCap" /></p>
                  )
                )}
              </>
            ) : (
              <PrivateLine drivers={a.top_drivers} />
            )}
            {diverge && (
              <p className="flex items-center gap-1.5 text-micro text-slate-400">
                <GitFork className="h-3.5 w-3.5 shrink-0 text-slate-500" aria-hidden="true" />
                {diverge}
              </p>
            )}
          </div>
        </>
      ) : (
        // Kullanıcının dilinde analiz yoksa diğer dili sessizce göstermek yerine açık not.
        <p className="mt-auto text-body text-slate-400">
          {noAnalysisText(card)}
        </p>
      )}
      {card.news_paused && <NewsPausedNote />}
    </Card>
  );
}

// Liste satırı: ince renk göstergesi · kısa ad · sembol · tek satır değerlendirme (tooltip'te
// tamamı) · sağda risk skoru (hizalı rakamlar) ve varsa yön değişikliği işareti (↻). Satırlar ince çizgilerle ayrılır (tablo).
// Mobilde değerlendirme adın altına iner (iki satıra kadar).
export function EntityRow({ card, onOpen }) {
  const a = card.analysis;
  const [horizon] = useHorizon();
  const edge = a ? newsSignal(a, card.evidence_strength, horizon).color : C.subtle;
  const changed = a && card.delta?.stance_changed;
  const verdict = a ? a.headline_verdict || a.summary : noAnalysisText(card, true);
  return (
    <button
      type="button"
      onClick={() => onOpen(card.id)}
      title={verdict}
      className="group flex w-full items-center gap-3 px-2 py-3 text-left transition-colors duration-hover ease-std hover:bg-ink-800"
    >
      <span className="h-9 w-0.5 shrink-0 self-center rounded-full" style={{ background: edge }} aria-hidden="true" />
      <span className="min-w-0 flex-1 md:flex md:items-center md:gap-4">
        <span className="flex items-baseline gap-2 md:w-56 md:shrink-0">
          <span className="break-words font-display text-sm font-medium text-slate-100">{displayName(card)}</span>
          <span className="shrink-0 text-micro text-slate-500">{symbolOf(card)}</span>
        </span>
        {a && (
          <span className="mt-1 flex md:mt-0 md:w-60 md:min-w-fit md:shrink-0">
            <NewsPill a={a} evidence={card.evidence_strength} horizon={horizon} />
          </span>
        )}
        <span className="mt-0.5 line-clamp-2 text-meta text-slate-400 md:mt-0 md:line-clamp-1 md:flex-1">{verdict}</span>
      </span>
      {changed && <StanceMark delta={card.delta} stance={a.stance} className="hidden md:inline-flex" />}
      {a && (
        <span className="w-8 shrink-0 text-right text-meta font-semibold tabular-nums" style={{ color: riskColor(a.risk_score) }} title={tt("sum.riskLabel")}>
          {a.risk_score}
        </span>
      )}
    </button>
  );
}
