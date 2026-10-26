// Admin paneli — yalnızca is_admin kullanıcı görür (backend 403 ile korur). Ayrı pakette (lazy).
// Sistem sağlığı · genel istatistik · maliyet · model kırılımı · geri bildirim kutusu · en çok
// takip/görüntülenen · kullanıcı tablosu (tıklanınca detay). Ortak bileşenler; sayılar mono.
// Onaylar ortak ConfirmDialog, geçici şifre ortak Modal, hatalar ortak Toast.
import React, { useEffect, useState } from "react";
import { Copy, Trash2, X } from "lucide-react";
import { api } from "../api.js";
import { timeAgo } from "./ui.jsx";
import { tt, fmtDate, fmtDateTime, fmtPct, getLang } from "../i18n.jsx";
import { fmtMoney } from "../money.js";

const usd = (v) => fmtMoney(v, "USD", getLang());
import { Button, Card, Chip, ConfirmDialog, ErrorState, Input, Modal, ModalHeader, Skeleton, Toast, cx } from "./kit.jsx";
import { displayName } from "./EntityCard.jsx";
import AdminEntities from "./AdminEntities.jsx";
import AdminVisits from "./AdminVisits.jsx";

function eventLabel(t) {
  const s = tt(`ev.${t}`);
  return s.startsWith("ev.") ? t : s; // bilinmeyen tip → ham anahtar
}

function SectionLabel({ children, aside }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h3 className="font-display text-sm font-medium text-slate-200">{children}</h3>
      {aside}
    </div>
  );
}

// Misafir temizliği: son çalışma (zamanlayıcı günde bir). İlk çalıştırma deneme: hiçbir şey
// silinmez, yalnızca "silinecek" sayısı gösterilir.
function CleanupCard() {
  const [run, setRun] = useState(undefined);
  useEffect(() => {
    api.adminMaintenance().then((d) => setRun(d.anon_cleanup)).catch(() => setRun(null));
  }, []);
  if (run === undefined) return null;
  return (
    <Card className="p-5">
      <SectionLabel>{tt("adm.cleanupTitle")}</SectionLabel>
      {run ? (
        <p className="text-meta text-slate-300">
          {tt(run.dry_run ? "adm.cleanupDry" : "adm.cleanupDone", { n: run.deleted, total: run.anon_total ?? "—" })}{" "}
          <span className="text-slate-500">· {timeAgo(run.ran_at)}</span>
        </p>
      ) : (
        <p className="text-meta text-slate-500">{tt("adm.cleanupNever")}</p>
      )}
      <p className="mt-1 text-micro text-slate-500">{tt("adm.cleanupRule")}</p>
    </Card>
  );
}

function StatCard({ label, value, hint, tone }) {
  const toneText = tone === "neg" ? "text-rose-600" : tone === "accent" ? "text-accent" : "text-slate-100";
  return (
    <Card className="p-5">
      <div className="text-micro font-medium text-slate-500">{label}</div>
      {/* Dar ekranda sayı ortadan bölünmesin: yalnızca "/" sonrasında satır kırılabilir. */}
      <div className={cx("mt-2 break-words font-mono text-xl font-semibold tabular-nums sm:text-2xl", toneText)}>
        {typeof value === "string" ? value.replaceAll("/", "/\u200b") : value}
      </div>
      {hint && <div className={cx("mt-1 text-micro", tone === "neg" ? "text-rose-600" : "text-slate-500")}>{hint}</div>}
    </Card>
  );
}

// LLM sistem sağlığı: son çağrı başarılı mıydı + son 24s kota/hata sayısı. Anlamsal renk
// yalnızca ince sol kenar ve noktada (ağır dolgu yok).
export function HealthBanner({ health }) {
  const h = health || {};
  const quota = h.quota_errors_24h || 0;
  const errs = h.errors_24h || 0;
  let edge, dot, title;
  if (h.last_kind == null) {
    edge = "bg-slate-500"; dot = "bg-slate-500"; title = tt("adm.healthNoData");
  } else if (quota > 0 || h.last_kind === "quota") {
    edge = "bg-rose-500"; dot = "bg-rose-500"; title = tt("adm.healthQuota");
  } else if (errs > 0 || h.last_kind === "error") {
    edge = "bg-amber-500"; dot = "bg-amber-500"; title = tt("adm.healthErrors");
  } else {
    edge = "bg-emerald-500"; dot = "bg-emerald-500"; title = tt("adm.healthOk");
  }
  return (
    <Card className="relative overflow-hidden p-5">
      <span className={cx("absolute inset-y-0 left-0 w-0.5", edge)} aria-hidden="true" />
      <div className="flex items-center gap-2 text-micro font-medium text-slate-500">
        <span className={cx("h-2 w-2 rounded-full", dot)} aria-hidden="true" />
        {tt("adm.healthTitle")}
      </div>
      <div className="mt-1.5 font-display text-base font-medium text-slate-100">{title}</div>
      <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-micro text-slate-500">
        <span>
          {tt("adm.healthLastOk")}: <span className="text-slate-300">{h.last_ok_at ? timeAgo(h.last_ok_at) : tt("adm.healthNever")}</span>
        </span>
        <span>
          {tt("adm.healthQuota24h")}: <span className={cx("font-mono", quota > 0 ? "font-semibold text-rose-600" : "text-slate-300")}>{quota}</span>
        </span>
        <span>
          {tt("adm.healthErr24h")}: <span className={cx("font-mono", errs > 0 ? "font-semibold text-amber-600" : "text-slate-300")}>{errs}</span>
        </span>
        {h.last_status_code ? (
          <span>
            {tt("adm.healthCode")}: <span className="font-mono text-slate-300">{h.last_status_code}</span>
          </span>
        ) : null}
      </div>
    </Card>
  );
}

function AdminSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-24 w-full" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      <Skeleton className="h-64 w-full" />
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
  const [busy, setBusy] = useState(null); // `${işlem}:${id}`
  const [confirm, setConfirm] = useState(null); // { title, body, label, run }
  const [notice, setNotice] = useState(null); // hata metni (toast)
  const [tempPw, setTempPw] = useState(null); // { username, temp_password }

  async function reload() {
    const [s, u, f] = await Promise.all([api.adminStats(), api.adminUsers(), api.adminFeedback()]);
    setStats(s);
    setUsers(u);
    setFeedback(f);
  }

  function load() {
    setLoading(true);
    setError(null);
    reload()
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  async function markRead(id) {
    // İyimser: yereldeki satırı okundu yap + rozeti düşür; sonra sunucuya yaz.
    setFeedback((prev) => prev.map((f) => (f.id === id ? { ...f, is_read: true } : f)));
    setStats((prev) => (prev ? { ...prev, unread_feedback: Math.max(0, prev.unread_feedback - 1) } : prev));
    try {
      await api.adminMarkFeedbackRead(id);
    } catch (err) {
      setNotice(tt("adm.markFail", { m: err.message }));
      reload().catch(() => {});
    }
  }

  function deleteFeedback(f) {
    setConfirm({
      title: tt("adm.deleteFb"),
      body: tt("adm.deleteFbConfirm"),
      label: tt("adm.delete"),
      run: async () => {
        setFeedback((prev) => prev.filter((x) => x.id !== f.id));
        if (!f.is_read) setStats((prev) => (prev ? { ...prev, unread_feedback: Math.max(0, prev.unread_feedback - 1) } : prev));
        try {
          await api.adminDeleteFeedback(f.id);
        } catch (err) {
          setNotice(tt("adm.deleteFbFail", { m: err.message }));
          reload().catch(() => {});
        }
      },
    });
  }

  function handleDelete(u, e) {
    e.stopPropagation(); // satır tıklamasıyla detay açılmasın
    setConfirm({
      title: tt("adm.deleteTitle"),
      body: tt("adm.confirmDelete", { u: u.username }),
      label: tt("adm.delete"),
      run: async () => {
        setBusy(`del:${u.id}`);
        try {
          await api.adminDeleteUser(u.id);
          if (selected === u.id) setSelected(null);
          await reload();
        } catch (err) {
          setNotice(tt("adm.deleteFail", { m: err.message }));
        } finally {
          setBusy(null);
        }
      },
    });
  }

  function handleReset(u, e) {
    e.stopPropagation();
    setConfirm({
      title: tt("adm.pwResetTitle"),
      body: tt("adm.confirmReset", { u: u.username }),
      label: tt("adm.pwReset"),
      run: async () => {
        setBusy(`pw:${u.id}`);
        try {
          setTempPw(await api.adminResetPassword(u.id));
        } catch (err) {
          setNotice(tt("adm.resetFail", { m: err.message }));
        } finally {
          setBusy(null);
        }
      },
    });
  }

  if (loading && !stats) return <AdminSkeleton />;
  if (error) return <ErrorState message={tt("adm.errorBody")} detail={error} onRetry={load} />;

  const overUsers = stats.max_users > 0 && stats.total_users > stats.max_users;
  const cap = stats.daily_budget_usd || 0;
  const unread = stats.unread_feedback;

  return (
    <div className="space-y-8">
      <h1 className="font-display text-page font-semibold text-slate-100">{tt("adm.title")}</h1>

      {notice && (
        <Toast tone="error" inline onClose={() => setNotice(null)}>
          {notice}
        </Toast>
      )}

      {/* SİSTEM SAĞLIĞI (LLM) — sorunu kullanıcıdan önce gör. */}
      <HealthBanner health={stats.health} />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label={tt("adm.userLimit")}
          value={stats.max_users > 0 ? `${stats.total_users}/${stats.max_users}` : `${stats.total_users}`}
          hint={overUsers ? tt("adm.limitReached") : stats.max_users > 0 ? tt("adm.regLimit") : tt("adm.unlimited")}
          tone={overUsers ? "neg" : undefined}
        />
        <StatCard label={tt("adm.activeToday")} value={stats.active_today} hint={tt("adm.atLeast1")} />
        <StatCard label={tt("adm.refreshesToday")} value={stats.refreshes_today} />
        <StatCard
          label={tt("adm.unreadFb")}
          value={unread}
          hint={unread > 0 ? tt("adm.unreadWaiting") : tt("adm.allRead")}
          tone={unread > 0 ? "accent" : undefined}
        />
      </div>

      {/* MALİYET (USD) + günlük bütçe */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label={tt("adm.costBudget")}
          value={cap > 0 ? `${usd(stats.cost_today_usd)} / ${usd(cap)}` : usd(stats.cost_today_usd)}
          hint={`${stats.budget_exceeded ? tt("adm.budgetFull") : cap > 0 ? tt("adm.dailyCap") : tt("adm.unlimited")} · ${tt("adm.tokenK", { n: (stats.tokens_today / 1000).toFixed(0) })}`}
          tone={stats.budget_exceeded ? "neg" : undefined}
        />
        <StatCard label={tt("adm.cost7")} value={usd(stats.cost_week_usd ?? 0)} hint={tt("adm.tokenK", { n: ((stats.tokens_week ?? 0) / 1000).toFixed(0) })} />
        <StatCard label={tt("adm.cost30")} value={usd(stats.cost_month_usd)} hint={tt("adm.tokenK", { n: (stats.tokens_month / 1000).toFixed(0) })} />
        <StatCard
          label={tt("adm.cacheHit")}
          value={stats.cache_hit_rate_7d == null ? "—" : fmtPct(stats.cache_hit_rate_7d * 100, { signed: false })}
          hint={tt("adm.cacheHitHint")}
        />
      </div>

      {/* ZİYARETLER (çerezsiz sayaç, son 30 gün) */}
      <AdminVisits />
      <CleanupCard />

      {/* Model kırılımı (son 30 gün) */}
      {stats.model_breakdown?.length > 0 && (
        <Card className="overflow-x-auto p-5">
          <SectionLabel>{tt("adm.modelBreakdown")}</SectionLabel>
          <table className="w-full text-left text-meta">
            <thead className="text-micro text-slate-500">
              <tr>
                <th className="py-2 pr-3 font-medium">{tt("adm.mbModel")}</th>
                <th className="py-2 pr-3 text-right font-medium">{tt("adm.mbCalls")}</th>
                <th className="py-2 pr-3 text-right font-medium">{tt("adm.mbInOut")}</th>
                <th className="py-2 pr-3 text-right font-medium">{tt("adm.cacheHit")}</th>
                <th className="py-2 text-right font-medium">USD</th>
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums text-slate-300">
              {stats.model_breakdown.map((m) => (
                <tr key={m.model}>
                  <td className="py-1.5 pr-3">{m.model}</td>
                  <td className="py-1.5 pr-3 text-right">{m.calls}</td>
                  <td className="py-1.5 pr-3 text-right">
                    {((m.input_tokens + m.cache_creation_tokens + m.cache_read_tokens) / 1000).toFixed(0)}K / {(m.output_tokens / 1000).toFixed(0)}K
                  </td>
                  <td className="py-1.5 pr-3 text-right">{m.cache_hit_rate == null ? "—" : fmtPct(m.cache_hit_rate * 100, { signed: false })}</td>
                  <td className="py-1.5 text-right">${m.cost_usd.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <FeedbackInbox items={feedback} onMarkRead={markRead} onDelete={deleteFeedback} />

      {/* Şirketlerin görünen adı (ör. "KOC" → "Koç Holding") */}
      <AdminEntities />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <SectionLabel aside={<span className="text-micro tabular-nums text-slate-500">{tt("adm.poolUniqueN", { n: stats.total_entities })}</span>}>
            {tt("adm.mostFollowed")}
          </SectionLabel>
          {stats.most_followed.length === 0 ? (
            <span className="text-meta text-slate-500">{tt("adm.noneFollow")}</span>
          ) : (
            <div className="flex flex-wrap gap-2">
              {stats.most_followed.map((e) => (
                <Chip key={`${e.type}:${e.name}`} tone="neutral" size="md">
                  <span className="font-mono text-micro text-slate-500">{e.type === "ticker" ? "$" : "#"}</span>
                  {displayName(e)}
                  <span className="text-micro tabular-nums text-slate-500">{tt("adm.person", { n: e.followers })}</span>
                </Chip>
              ))}
            </div>
          )}
        </Card>
        {stats.top_entities.length > 0 && (
          <Card className="p-5">
            <SectionLabel>{tt("adm.mostViewed")}</SectionLabel>
            <div className="flex flex-wrap gap-2">
              {stats.top_entities.map((e) => (
                <Chip key={e.name} tone="neutral" size="md">
                  {e.name} <span className="font-mono font-semibold text-slate-100">{e.count}</span>
                </Chip>
              ))}
            </div>
          </Card>
        )}
      </div>

      {/* Kullanıcı tablosu */}
      <Card className="overflow-x-auto">
        <table className="w-full text-left text-meta">
          <thead className="text-micro text-slate-500">
            <tr className="border-b border-ink-600">
              <th className="px-5 py-3 font-medium">{tt("adm.thUser")}</th>
              <th className="px-4 py-3 font-medium">{tt("adm.thEmail")}</th>
              <th className="px-4 py-3 font-medium">{tt("adm.thReg")}</th>
              <th className="px-4 py-3 font-medium">{tt("adm.thLastLogin")}</th>
              <th className="px-4 py-3 text-right font-medium">{tt("adm.thLogin")}</th>
              <th className="px-4 py-3 text-right font-medium">{tt("adm.thRefresh")}</th>
              <th className="px-4 py-3 text-right font-medium">{tt("adm.thTotal")}</th>
              <th className="px-4 py-3 font-medium">{tt("adm.thActive")}</th>
              <th className="px-5 py-3 text-right font-medium">{tt("adm.thAction")}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr
                key={u.id}
                onClick={() => setSelected(u.id)}
                className={cx("cursor-pointer transition-colors duration-hover ease-std hover:bg-ink-700", selected === u.id && "bg-ink-700")}
              >
                <td className="px-5 py-2.5">
                  <span className="font-medium text-slate-100">{u.username}</span>
                  {u.is_admin && <Chip tone="accent" className="ml-2">admin</Chip>}
                </td>
                <td className="max-w-56 truncate px-4 py-2.5 text-slate-400" title={u.email || undefined}>{u.email || "—"}</td>
                <td className="px-4 py-2.5 text-slate-500">{fmtDate(u.created_at)}</td>
                <td className="px-4 py-2.5 text-slate-500">{u.last_login_at ? timeAgo(u.last_login_at) : "—"}</td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums text-slate-300">{u.login_count}</td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums text-slate-300">{u.refresh_count}</td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums text-slate-300">{u.total_events}</td>
                <td className="px-4 py-2.5 text-slate-500">{u.last_active_at ? timeAgo(u.last_active_at) : tt("adm.never")}</td>
                <td className="px-5 py-2.5 text-right">
                  <div className="flex items-center justify-end gap-1">
                    <Button variant="ghost" size="sm" onClick={(e) => handleReset(u, e)} disabled={busy === `pw:${u.id}`} title={tt("adm.pwResetTitle")}>
                      {busy === `pw:${u.id}` ? "…" : tt("adm.pwReset")}
                    </Button>
                    {u.id === currentUserId ? (
                      <span className="px-3 text-micro text-slate-500">{tt("adm.you")}</span>
                    ) : (
                      <Button variant="ghost" size="sm" onClick={(e) => handleDelete(u, e)} disabled={busy === `del:${u.id}`} title={tt("adm.deleteTitle")} className="text-rose-600 hover:bg-rose-500/10 hover:text-rose-600">
                        {busy === `del:${u.id}` ? tt("adm.deleting") : tt("adm.delete")}
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {selected != null && <UserDetail userId={selected} onClose={() => setSelected(null)} />}

      {confirm && (
        <ConfirmDialog
          title={confirm.title}
          body={confirm.body}
          confirmLabel={confirm.label}
          cancelLabel={tt("common.cancel")}
          onCancel={() => setConfirm(null)}
          onConfirm={() => {
            const run = confirm.run;
            setConfirm(null);
            run();
          }}
        />
      )}
      {tempPw && <TempPasswordModal data={tempPw} onClose={() => setTempPw(null)} />}
    </div>
  );
}

// Geçici şifre (window.prompt yerine): kopyalanabilir alan + kopyala butonu.
function TempPasswordModal({ data, onClose }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(data.temp_password);
      setCopied(true);
    } catch {
      /* pano erişimi yoksa alan seçili kalır, elle kopyalanır */
    }
  }
  return (
    <Modal onClose={onClose} labelledBy="temp-pw-title" size="sm">
      <ModalHeader id="temp-pw-title" title={tt("adm.pwReset")} onClose={onClose}>
        {tt("adm.tempPrompt", { u: data.username })}
      </ModalHeader>
      <div className="flex gap-2">
        <Input readOnly mono value={data.temp_password} onFocus={(e) => e.target.select()} data-autofocus aria-label={tt("adm.pwReset")} />
        <Button icon={Copy} onClick={copy}>
          {copied ? tt("adm.copied") : tt("adm.copy")}
        </Button>
      </div>
    </Modal>
  );
}

// Geri bildirim gelen kutusu — okunmamışlar önce (backend sıralar), ince vurgu kenarıyla.
function FeedbackInbox({ items, onMarkRead, onDelete }) {
  const unread = items.filter((f) => !f.is_read).length;
  return (
    <Card className="p-5">
      <SectionLabel aside={<span className="text-micro tabular-nums text-slate-500">{tt("adm.totalN", { n: items.length })}</span>}>
        <span className="flex items-center gap-2">
          {tt("adm.feedbackTitle")}
          {unread > 0 && <Chip tone="accent">{tt("adm.unread", { n: unread })}</Chip>}
        </span>
      </SectionLabel>
      {items.length === 0 ? (
        <span className="text-meta text-slate-500">{tt("adm.noFeedback")}</span>
      ) : (
        <div className="space-y-1">
          {items.map((f) => (
            <div key={f.id} className={cx("relative rounded-control px-4 py-3", !f.is_read && "bg-ink-700")}>
              {!f.is_read && <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-accent" aria-hidden="true" />}
              <div className="flex items-start justify-between gap-3">
                <p className={cx("min-w-0 flex-1 whitespace-pre-wrap break-words text-body", f.is_read ? "text-slate-400" : "font-medium text-slate-100")}>{f.message}</p>
                <div className="flex shrink-0 items-center gap-1">
                  {!f.is_read ? (
                    <Button variant="ghost" size="sm" onClick={() => onMarkRead(f.id)}>
                      {tt("adm.read")}
                    </Button>
                  ) : (
                    <span className="px-2 text-micro text-slate-500">{tt("adm.readMark")}</span>
                  )}
                  <Button variant="ghost" size="sm" iconOnly icon={Trash2} onClick={() => onDelete(f)} aria-label={tt("adm.deleteFb")} title={tt("adm.deleteFb")} className="hover:text-rose-600" />
                </div>
              </div>
              <p className="mt-1.5 text-micro text-slate-500">
                <span className="font-medium text-slate-400">{f.username || tt("adm.anon")}</span>
                {f.contact && <> · <span className="text-accent">{f.contact}</span></>} · {f.device} · <span title={fmtDate(f.created_at)}>{timeAgo(f.created_at)}</span>
              </p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function UserDetail({ userId, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    api
      .adminUserDetail(userId)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [userId]);

  return (
    <section className="rounded-card bg-raised p-6 ring-1 ring-ink-600">
      <div className="mb-5 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 font-display text-title font-semibold text-slate-100">
          {data ? data.user.username : <Skeleton className="h-6 w-32" />}
          {data?.user.is_admin && <Chip tone="accent">admin</Chip>}
        </h2>
        <Button variant="ghost" size="sm" iconOnly icon={X} onClick={onClose} aria-label={tt("adm.close")} title={tt("adm.close")} />
      </div>

      {error && <ErrorState message={tt("adm.errorBody")} detail={error} />}
      {!data && !error && <Skeleton className="h-40 w-full" />}
      {data && (
        <div className="grid gap-8 md:grid-cols-2">
          <div className="space-y-6">
            <div>
              <SectionLabel>{tt("adm.eventBreakdown")}</SectionLabel>
              <div className="flex flex-wrap gap-2">
                {Object.keys(data.event_counts).length === 0 && <span className="text-meta text-slate-500">{tt("adm.noActions")}</span>}
                {Object.entries(data.event_counts).map(([t, c]) => (
                  <Chip key={t} tone="neutral" size="md">
                    {eventLabel(t)} <span className="font-mono font-semibold text-slate-100">{c}</span>
                  </Chip>
                ))}
              </div>
            </div>
            {data.top_entities.length > 0 && (
              <div>
                <SectionLabel>{tt("adm.topViewed")}</SectionLabel>
                <div className="flex flex-wrap gap-2">
                  {data.top_entities.map((e) => (
                    <Chip key={e.name} tone="neutral" size="md">
                      {e.name} <span className="font-mono font-semibold text-slate-100">{e.count}</span>
                    </Chip>
                  ))}
                </div>
              </div>
            )}
            <div>
              <SectionLabel>{tt("adm.watchlistN", { n: data.watchlist_size })}</SectionLabel>
              {data.watchlist_size === 0 ? (
                <span className="text-meta text-slate-500">{tt("adm.noWatch")}</span>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {data.watchlist.map((e) => (
                    <Chip key={`${e.type}:${e.query}`} tone="neutral" size="md">
                      {displayName(e)}
                      <span className="font-mono text-micro text-slate-500">
                        {e.type === "ticker" ? "$" : "#"}
                        {e.query}
                      </span>
                    </Chip>
                  ))}
                </div>
              )}
            </div>
            <p className="text-micro text-slate-500">
              {tt("adm.registered", { d: fmtDateTime(data.user.created_at) })} ·{" "}
              {tt("adm.lastLoginLine", { d: data.user.last_login_at ? fmtDateTime(data.user.last_login_at) : "—" })}
            </p>
          </div>

          <div>
            <SectionLabel>{tt("adm.recentActions")}</SectionLabel>
            <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
              {data.recent_events.length === 0 && <span className="text-meta text-slate-500">{tt("adm.noRecords")}</span>}
              {data.recent_events.map((ev, i) => (
                <div key={i} className="flex items-baseline gap-3 text-meta">
                  <span className="w-24 shrink-0 text-micro tabular-nums text-slate-500">{timeAgo(ev.created_at)}</span>
                  <span className="text-slate-300">
                    {eventLabel(ev.event_type)}
                    {(ev.detail?.name || ev.detail?.username) && <span className="text-slate-500"> · {ev.detail.name || ev.detail.username}</span>}
                    {ev.detail?.ip && <span className="text-slate-500"> ({ev.detail.ip})</span>}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
