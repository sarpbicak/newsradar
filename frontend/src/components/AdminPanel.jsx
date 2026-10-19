// Admin kullanım paneli — yalnızca is_admin kullanıcı görür (backend 403 ile korur).
// Genel istatistik + kullanıcı tablosu + tıklanınca kullanıcı detayı (eylem dökümü,
// en çok baktığı şirketler, zaman çizelgesi). Veri ORTAK; bu sadece 'kim ne yaptı'.
import React, { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { api } from "../api.js";
import { timeAgo } from "./ui.jsx";
import { tt, fmtDate, fmtDateTime, fmtPct } from "../i18n.jsx";

function eventLabel(t) {
  const s = tt(`ev.${t}`);
  return s.startsWith("ev.") ? t : s; // bilinmeyen tip → ham anahtar
}

function StatCard({ label, value, hint }) {
  return (
    <div className="rounded-xl border border-ink-600 bg-ink-800 p-4 shadow-card">
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 font-display text-2xl font-bold text-slate-100">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

// LLM sistem sağlığı: son çağrı başarılı mıydı + son 24s kota/hata sayısı.
// Sorun (ör. OpenRouter kota/bakiye limiti) kullanıcı fark etmeden admin'e görünsün.
export function HealthBanner({ health }) {
  const h = health || {};
  const quota = h.quota_errors_24h || 0;
  const errs = h.errors_24h || 0;
  // Durum: kota hatası → kırmızı; diğer hata → amber; son çağrı ok → yeşil; veri yok → nötr.
  let tone, dot, title;
  if (h.last_kind == null) {
    tone = "border-ink-600 bg-ink-800 text-slate-400"; dot = "bg-slate-500";
    title = tt("adm.healthNoData");
  } else if (quota > 0 || h.last_kind === "quota") {
    tone = "border-rose-500/50 bg-rose-500/10 text-rose-300"; dot = "bg-rose-400";
    title = tt("adm.healthQuota");
  } else if (errs > 0 || h.last_kind === "error") {
    tone = "border-amber-500/50 bg-amber-500/10 text-amber-200"; dot = "bg-amber-400";
    title = tt("adm.healthErrors");
  } else {
    tone = "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"; dot = "bg-emerald-400";
    title = tt("adm.healthOk");
  }
  return (
    <div className={`rounded-xl border p-4 shadow-card ${tone}`}>
      <div className="flex items-center gap-2">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${dot}`} />
        <span className="text-[11px] font-semibold uppercase tracking-wide">
          {tt("adm.healthTitle")}
        </span>
      </div>
      <div className="mt-1.5 text-sm font-medium">{title}</div>
      <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-400">
        <span>
          {tt("adm.healthLastOk")}:{" "}
          <span className="text-slate-300">
            {h.last_ok_at ? timeAgo(h.last_ok_at) : tt("adm.healthNever")}
          </span>
        </span>
        <span>
          {tt("adm.healthQuota24h")}:{" "}
          <span className={quota > 0 ? "font-semibold text-rose-400" : "text-slate-300"}>{quota}</span>
        </span>
        <span>
          {tt("adm.healthErr24h")}:{" "}
          <span className={errs > 0 ? "font-semibold text-amber-300" : "text-slate-300"}>{errs}</span>
        </span>
        {h.last_status_code ? (
          <span>
            {tt("adm.healthCode")}: <span className="font-mono text-slate-300">{h.last_status_code}</span>
          </span>
        ) : null}
      </div>
    </div>
  );
}

export default function AdminPanel({ currentUserId }) {
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [feedback, setFeedback] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null); // seçili kullanıcı id
  const [deleting, setDeleting] = useState(null); // silinmekte olan kullanıcı id

  async function reload() {
    const [s, u, f] = await Promise.all([
      api.adminStats(),
      api.adminUsers(),
      api.adminFeedback(),
    ]);
    setStats(s);
    setUsers(u);
    setFeedback(f);
  }

  async function markRead(id) {
    // İyimser: yereldeki satırı okundu yap + rozeti düşür; sonra sunucuya yaz.
    setFeedback((prev) => prev.map((f) => (f.id === id ? { ...f, is_read: true } : f)));
    setStats((prev) => (prev ? { ...prev, unread_feedback: Math.max(0, prev.unread_feedback - 1) } : prev));
    try {
      await api.adminMarkFeedbackRead(id);
    } catch (err) {
      window.alert(tt("adm.markFail", { m: err.message }));
      reload().catch(() => {});
    }
  }

  async function deleteFeedback(f) {
    // Kalıcı silme → önce onay. İyimser: listeden çıkar (okunmamışsa rozeti düşür).
    if (!window.confirm(tt("adm.deleteFbConfirm"))) return;
    setFeedback((prev) => prev.filter((x) => x.id !== f.id));
    if (!f.is_read) {
      setStats((prev) => (prev ? { ...prev, unread_feedback: Math.max(0, prev.unread_feedback - 1) } : prev));
    }
    try {
      await api.adminDeleteFeedback(f.id);
    } catch (err) {
      window.alert(tt("adm.deleteFbFail", { m: err.message }));
      reload().catch(() => {});
    }
  }

  useEffect(() => {
    let alive = true;
    reload()
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  async function handleDelete(u, e) {
    e.stopPropagation(); // satır tıklamasıyla detay açılmasın
    if (!window.confirm(tt("adm.confirmDelete", { u: u.username })))
      return;
    setDeleting(u.id);
    try {
      await api.adminDeleteUser(u.id);
      if (selected === u.id) setSelected(null);
      await reload();
    } catch (err) {
      window.alert(tt("adm.deleteFail", { m: err.message }));
    } finally {
      setDeleting(null);
    }
  }

  const [resetting, setResetting] = useState(null);
  async function handleReset(u, e) {
    e.stopPropagation();
    if (!window.confirm(tt("adm.confirmReset", { u: u.username })))
      return;
    setResetting(u.id);
    try {
      const r = await api.adminResetPassword(u.id);
      window.prompt(
        tt("adm.tempPrompt", { u: r.username }),
        r.temp_password
      );
    } catch (err) {
      window.alert(tt("adm.resetFail", { m: err.message }));
    } finally {
      setResetting(null);
    }
  }

  if (loading) return <div className="p-8 text-slate-500">{tt("adm.loading")}</div>;
  if (error) return <div className="p-8 text-rose-400">{tt("adm.errPrefix", { m: error })}</div>;

  return (
    <div className="space-y-6">
      <h2 className="font-display text-xl font-bold text-slate-100">{tt("adm.title")}</h2>

      {/* SİSTEM SAĞLIĞI (LLM) — sorunu kullanıcıdan önce gör. En üstte, dikkat çekici. */}
      <HealthBanner health={stats.health} />

      {/* Genel istatistik */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {(() => {
          const over = stats.max_users > 0 && stats.total_users > stats.max_users;
          const label = stats.max_users > 0
            ? `${stats.total_users}/${stats.max_users}`
            : `${stats.total_users}`;
          return (
            <div className={`rounded-xl border bg-ink-800 p-4 shadow-card ${
              over ? "border-rose-500/50" : "border-ink-600"}`}>
              <div className="text-[11px] uppercase tracking-wide text-slate-500">{tt("adm.userLimit")}</div>
              <div className={`mt-1 font-display text-2xl font-bold ${over ? "text-rose-400" : "text-slate-100"}`}>
                {label}
              </div>
              <div className={`mt-0.5 text-xs ${over ? "text-rose-400" : "text-slate-500"}`}>
                {over ? tt("adm.limitReached") : stats.max_users > 0 ? tt("adm.regLimit") : tt("adm.unlimited")}
              </div>
            </div>
          );
        })()}
        <StatCard label={tt("adm.activeToday")} value={stats.active_today} hint={tt("adm.atLeast1")} />
        <StatCard label={tt("adm.refreshesToday")} value={stats.refreshes_today} />
        {/* Okunmamış geri bildirim — >0 ise lacivert vurguyla dikkat çeker */}
        <div className={`rounded-xl border bg-ink-800 p-4 shadow-card ${
          stats.unread_feedback > 0 ? "border-accent/50" : "border-ink-600"}`}>
          <div className="text-[11px] uppercase tracking-wide text-slate-500">{tt("adm.unreadFb")}</div>
          <div className={`mt-1 font-display text-2xl font-bold ${
            stats.unread_feedback > 0 ? "text-accent" : "text-slate-100"}`}>
            {stats.unread_feedback}
          </div>
          <div className="mt-0.5 text-xs text-slate-500">
            {stats.unread_feedback > 0 ? tt("adm.unreadWaiting") : tt("adm.allRead")}
          </div>
        </div>
      </div>

      {/* MALİYET (USD, çağrı başına model fiyatı) + günlük USD bütçesi */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {(() => {
          const over = stats.budget_exceeded;
          const cap = stats.daily_budget_usd || 0;
          const label = cap > 0
            ? `$${stats.cost_today_usd.toFixed(2)}/$${cap.toFixed(2)}`
            : `$${stats.cost_today_usd.toFixed(2)}`;
          return (
            <div className={`rounded-xl border bg-ink-800 p-4 shadow-card ${over ? "border-rose-500/50" : "border-ink-600"}`}>
              <div className="text-[11px] uppercase tracking-wide text-slate-500">{tt("adm.costBudget")}</div>
              <div className={`mt-1 font-display text-2xl font-bold ${over ? "text-rose-400" : "text-slate-100"}`}>{label}</div>
              <div className={`mt-0.5 text-xs ${over ? "text-rose-400" : "text-slate-500"}`}>
                {over ? tt("adm.budgetFull") : cap > 0 ? tt("adm.dailyCap") : tt("adm.unlimited")}
                {" · "}{tt("adm.tokenK", { n: (stats.tokens_today / 1000).toFixed(0) })}
              </div>
            </div>
          );
        })()}
        <StatCard label={tt("adm.cost7")} value={`$${(stats.cost_week_usd ?? 0).toFixed(2)}`} hint={tt("adm.tokenK", { n: ((stats.tokens_week ?? 0) / 1000).toFixed(0) })} />
        <StatCard label={tt("adm.cost30")} value={`$${stats.cost_month_usd.toFixed(2)}`} hint={tt("adm.tokenK", { n: (stats.tokens_month / 1000).toFixed(0) })} />
        <StatCard
          label={tt("adm.cacheHit")}
          value={stats.cache_hit_rate_7d == null ? "—" : fmtPct(stats.cache_hit_rate_7d * 100, { signed: false })}
          hint={tt("adm.cacheHitHint")}
        />
      </div>

      {/* Model kırılımı (son 30 gün) */}
      {stats.model_breakdown?.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-ink-600 bg-ink-800 p-4">
          <div className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">{tt("adm.modelBreakdown")}</div>
          <table className="w-full text-left text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="py-1 pr-3 font-medium">{tt("adm.mbModel")}</th>
                <th className="py-1 pr-3 text-right font-medium">{tt("adm.mbCalls")}</th>
                <th className="py-1 pr-3 text-right font-medium">{tt("adm.mbInOut")}</th>
                <th className="py-1 pr-3 text-right font-medium">{tt("adm.cacheHit")}</th>
                <th className="py-1 text-right font-medium">USD</th>
              </tr>
            </thead>
            <tbody className="text-slate-300">
              {stats.model_breakdown.map((m) => (
                <tr key={m.model} className="border-t border-ink-600">
                  <td className="py-1 pr-3 font-mono">{m.model}</td>
                  <td className="py-1 pr-3 text-right">{m.calls}</td>
                  <td className="py-1 pr-3 text-right">
                    {((m.input_tokens + m.cache_creation_tokens + m.cache_read_tokens) / 1000).toFixed(0)}K / {(m.output_tokens / 1000).toFixed(0)}K
                  </td>
                  <td className="py-1 pr-3 text-right">
                    {m.cache_hit_rate == null ? "—" : fmtPct(m.cache_hit_rate * 100, { signed: false })}
                  </td>
                  <td className="py-1 text-right">${m.cost_usd.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Geri bildirim gelen kutusu — okunmamışlar önce, vurgulu */}
      <FeedbackInbox items={feedback} onMarkRead={markRead} onDelete={deleteFeedback} />

      {/* En çok TAKİP EDİLEN şirketler (kaç kullanıcının listesinde) + toplam benzersiz */}
      <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">
            {tt("adm.mostFollowed")}
          </div>
          <div className="text-[11px] text-slate-500">
            {tt("adm.poolUniqueN", { n: stats.total_entities })}
          </div>
        </div>
        {stats.most_followed.length === 0 ? (
          <span className="text-sm text-slate-500">{tt("adm.noneFollow")}</span>
        ) : (
          <div className="flex flex-wrap gap-2">
            {stats.most_followed.map((e) => (
              <span
                key={`${e.type}:${e.name}`}
                className="inline-flex items-center gap-1.5 rounded-md border border-ink-500 bg-ink-700 px-2 py-1 text-xs text-slate-300"
              >
                <span className="font-mono text-[10px] text-slate-500">
                  {e.type === "ticker" ? "$" : "#"}
                </span>
                {e.name}
                <span className="rounded bg-ink-700 px-1.5 font-semibold text-slate-500">
                  {tt("adm.person", { n: e.followers })}
                </span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* En çok görüntülenen şirketler */}
      {stats.top_entities.length > 0 && (
        <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
          <div className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">
            {tt("adm.mostViewed")}
          </div>
          <div className="flex flex-wrap gap-2">
            {stats.top_entities.map((e) => (
              <span
                key={e.name}
                className="rounded-md border border-ink-500 bg-ink-700 px-2 py-1 text-xs text-slate-300"
              >
                {e.name} <span className="font-semibold text-slate-100">{e.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Kullanıcı tablosu */}
      <div className="overflow-x-auto rounded-xl border border-ink-600 bg-ink-800">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-ink-600 text-[11px] uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2.5">{tt("adm.thUser")}</th>
              <th className="px-4 py-2.5">{tt("adm.thReg")}</th>
              <th className="px-4 py-2.5">{tt("adm.thLastLogin")}</th>
              <th className="px-4 py-2.5 text-right">{tt("adm.thLogin")}</th>
              <th className="px-4 py-2.5 text-right">{tt("adm.thRefresh")}</th>
              <th className="px-4 py-2.5 text-right">{tt("adm.thTotal")}</th>
              <th className="px-4 py-2.5">{tt("adm.thActive")}</th>
              <th className="px-4 py-2.5 text-right">{tt("adm.thAction")}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr
                key={u.id}
                onClick={() => setSelected(u.id)}
                className="cursor-pointer border-b border-ink-700 last:border-0 hover:bg-ink-700"
              >
                <td className="px-4 py-2.5">
                  <span className="font-medium text-slate-200">{u.username}</span>
                  {u.is_admin && (
                    <span className="ml-1.5 rounded bg-ink-700 px-1.5 text-[10px] font-semibold text-slate-500">
                      admin
                    </span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-slate-500">{fmtDate(u.created_at)}</td>
                <td className="px-4 py-2.5 text-slate-500">{u.last_login_at ? timeAgo(u.last_login_at) : "—"}</td>
                <td className="px-4 py-2.5 text-right tabular-nums text-slate-300">{u.login_count}</td>
                <td className="px-4 py-2.5 text-right tabular-nums text-slate-300">{u.refresh_count}</td>
                <td className="px-4 py-2.5 text-right tabular-nums text-slate-300">{u.total_events}</td>
                <td className="px-4 py-2.5 text-slate-500">
                  {u.last_active_at ? timeAgo(u.last_active_at) : "hiç"}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <div className="flex items-center justify-end gap-1.5">
                    <button
                      onClick={(e) => handleReset(u, e)}
                      disabled={resetting === u.id}
                      title={tt("adm.pwResetTitle")}
                      className="rounded-md border border-ink-500 px-2 py-1 text-[11px] font-medium text-slate-400 transition hover:bg-ink-700 hover:text-slate-200 disabled:opacity-50"
                    >
                      {resetting === u.id ? "…" : tt("adm.pwReset")}
                    </button>
                    {u.id === currentUserId ? (
                      <span className="text-[11px] text-slate-600">{tt("adm.you")}</span>
                    ) : (
                      <button
                        onClick={(e) => handleDelete(u, e)}
                        disabled={deleting === u.id}
                        title={tt("adm.deleteTitle")}
                        className="rounded-md border border-rose-500/30 px-2 py-1 text-[11px] font-medium text-rose-400 transition hover:bg-rose-500/10 disabled:opacity-50"
                      >
                        {deleting === u.id ? tt("adm.deleting") : tt("adm.delete")}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected != null && <UserDetail userId={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

// Geri bildirim gelen kutusu — okunmamışlar önce (backend sıralar), vurgulu.
function FeedbackInbox({ items, onMarkRead, onDelete }) {
  const unread = items.filter((f) => !f.is_read).length;
  return (
    <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-[11px] uppercase tracking-wide text-slate-500">{tt("adm.feedbackTitle")}</span>
        {unread > 0 && (
          <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[11px] font-semibold text-accent">
            {tt("adm.unread", { n: unread })}
          </span>
        )}
        <span className="ml-auto text-[11px] text-slate-500">{tt("adm.totalN", { n: items.length })}</span>
      </div>

      {items.length === 0 ? (
        <span className="text-sm text-slate-500">{tt("adm.noFeedback")}</span>
      ) : (
        <div className="space-y-2.5">
          {items.map((f) => (
            <div
              key={f.id}
              className={`rounded-lg border p-3 transition ${
                f.is_read
                  ? "border-ink-600 bg-ink-800"
                  : "border-accent/40 bg-accent/5"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <p
                  className={`min-w-0 flex-1 whitespace-pre-wrap break-words text-sm leading-relaxed ${
                    f.is_read ? "text-slate-400" : "font-medium text-slate-100"
                  }`}
                >
                  {f.message}
                </p>
                <div className="flex shrink-0 items-center gap-1.5">
                  {!f.is_read ? (
                    <button
                      onClick={() => onMarkRead(f.id)}
                      className="rounded-md border border-ink-500 px-2 py-1 text-[11px] font-medium text-slate-400 transition hover:bg-ink-700 hover:text-slate-200"
                    >{tt("adm.read")}</button>
                  ) : (
                    <span className="text-[10px] uppercase tracking-wide text-slate-600">{tt("adm.readMark")}</span>
                  )}
                  <button
                    onClick={() => onDelete(f)}
                    aria-label={tt("adm.deleteFb")}
                    title={tt("adm.deleteFb")}
                    className="flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition hover:bg-rose-500/10 hover:text-rose-400"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-500">
                <span className="font-medium text-slate-400">
                  {f.username || tt("adm.anon")}
                </span>
                {f.contact && (
                  <>
                    <span className="text-slate-600">·</span>
                    <span className="text-accent">{f.contact}</span>
                  </>
                )}
                <span className="text-slate-600">·</span>
                <span>{f.device}</span>
                <span className="text-slate-600">·</span>
                <span title={fmtDate(f.created_at)}>{timeAgo(f.created_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function UserDetail({ userId, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  async function deleteFeedback(f) {
    // Kalıcı silme → önce onay. İyimser: listeden çıkar (okunmamışsa rozeti düşür).
    if (!window.confirm(tt("adm.deleteFbConfirm"))) return;
    setFeedback((prev) => prev.filter((x) => x.id !== f.id));
    if (!f.is_read) {
      setStats((prev) => (prev ? { ...prev, unread_feedback: Math.max(0, prev.unread_feedback - 1) } : prev));
    }
    try {
      await api.adminDeleteFeedback(f.id);
    } catch (err) {
      window.alert(tt("adm.deleteFbFail", { m: err.message }));
      reload().catch(() => {});
    }
  }

  useEffect(() => {
    let alive = true;
    setData(null);
    api
      .adminUserDetail(userId)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [userId]);

  return (
    <div className="rounded-xl border border-accent/30 bg-accent/5 p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-display text-lg font-semibold text-slate-100">
          {data ? data.user.username : tt("detail.loading")}
          {data?.user.is_admin && (
            <span className="ml-2 rounded bg-ink-700 px-1.5 text-[10px] font-semibold text-slate-500">
              admin
            </span>
          )}
        </h3>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-200">
          {tt("adm.close")}
        </button>
      </div>

      {error && <div className="text-sm text-rose-400">{tt("adm.errPrefix", { m: error })}</div>}
      {data && (
        <div className="grid gap-5 md:grid-cols-2">
          {/* Eylem dökümü + en çok baktığı şirketler */}
          <div className="space-y-4">
            <div>
              <div className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">{tt("adm.eventBreakdown")}</div>
              <div className="flex flex-wrap gap-2">
                {Object.keys(data.event_counts).length === 0 && (
                  <span className="text-sm text-slate-500">{tt("adm.noActions")}</span>
                )}
                {Object.entries(data.event_counts).map(([t, c]) => (
                  <span
                    key={t}
                    className="rounded-md border border-ink-500 bg-ink-800 px-2 py-1 text-xs text-slate-300"
                  >
                    {eventLabel(t)} <span className="font-semibold text-slate-100">{c}</span>
                  </span>
                ))}
              </div>
            </div>
            {data.top_entities.length > 0 && (
              <div>
                <div className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">
                  {tt("adm.topViewed")}
                </div>
                <div className="flex flex-wrap gap-2">
                  {data.top_entities.map((e) => (
                    <span
                      key={e.name}
                      className="rounded-md border border-ink-500 bg-ink-800 px-2 py-1 text-xs text-slate-300"
                    >
                      {e.name} <span className="font-semibold text-slate-100">{e.count}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
            {/* İzleme listesi — kullanıcının TAKİP ETTİĞİ şirketler (B6) */}
            <div>
              <div className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">
                {tt("adm.watchlistN", { n: data.watchlist_size })}
              </div>
              {data.watchlist_size === 0 ? (
                <span className="text-sm text-slate-500">{tt("adm.noWatch")}</span>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {data.watchlist.map((e) => (
                    <span
                      key={`${e.type}:${e.query}`}
                      className="inline-flex items-center gap-1 rounded-md border border-ink-500 bg-ink-800 px-2 py-1 text-xs text-slate-300"
                    >
                      {e.name}
                      <span className="font-mono text-[10px] text-slate-500">
                        {e.type === "ticker" ? "$" : "#"}{e.query}
                      </span>
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="text-xs text-slate-500">
              {tt("adm.registered", { d: fmtDateTime(data.user.created_at) })} ·{" "}
              {tt("adm.lastLoginLine", { d: data.user.last_login_at ? fmtDateTime(data.user.last_login_at) : "—" })}
            </div>
          </div>

          {/* Zaman çizelgesi — son eylemler */}
          <div>
            <div className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">{tt("adm.recentActions")}</div>
            <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
              {data.recent_events.length === 0 && (
                <span className="text-sm text-slate-500">{tt("adm.noRecords")}</span>
              )}
              {data.recent_events.map((ev, i) => (
                <div key={i} className="flex items-baseline gap-2 text-sm">
                  <span className="w-24 shrink-0 text-[11px] tabular-nums text-slate-500">
                    {timeAgo(ev.created_at)}
                  </span>
                  <span className="text-slate-300">
                    {eventLabel(ev.event_type)}
                    {(ev.detail?.name || ev.detail?.username) && (
                      <span className="text-slate-500"> · {ev.detail.name || ev.detail.username}</span>
                    )}
                    {ev.detail?.ip && (
                      <span className="text-slate-600"> ({ev.detail.ip})</span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
