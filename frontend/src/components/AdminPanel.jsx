// Admin kullanım paneli — yalnızca is_admin kullanıcı görür (backend 403 ile korur).
// Genel istatistik + kullanıcı tablosu + tıklanınca kullanıcı detayı (eylem dökümü,
// en çok baktığı şirketler, zaman çizelgesi). Veri ORTAK; bu sadece 'kim ne yaptı'.
import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { timeAgo } from "./ui.jsx";

const EVENT_LABELS = {
  login: "giriş",
  login_failed: "başarısız giriş",
  register_failed: "başarısız kayıt",
  refresh: "yenileme",
  view_entity: "görüntüleme",
  add_entity: "şirket ekleme",
  remove_entity: "şirket çıkarma",
  chat: "sohbet",
  add_suggestion: "öneri ekleme",
  dismiss_suggestion: "öneri gizleme",
  delete_user: "kullanıcı silme",
  password_reset: "şifre sıfırlama",
  feedback_sent: "geri bildirim",
};
function eventLabel(t) {
  return EVENT_LABELS[t] || t;
}
function fmtDate(iso) {
  return iso ? new Date(iso).toLocaleString("tr-TR") : "—";
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
      window.alert(`İşaretlenemedi: ${err.message}`);
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
    if (!window.confirm(`${u.username} kullanıcısını ve tüm verilerini silmek istediğinize emin misiniz?`))
      return;
    setDeleting(u.id);
    try {
      await api.adminDeleteUser(u.id);
      if (selected === u.id) setSelected(null);
      await reload();
    } catch (err) {
      window.alert(`Silinemedi: ${err.message}`);
    } finally {
      setDeleting(null);
    }
  }

  const [resetting, setResetting] = useState(null);
  async function handleReset(u, e) {
    e.stopPropagation();
    if (!window.confirm(`${u.username} kullanıcısının şifresi sıfırlansın mı? Geçici bir şifre üretilecek.`))
      return;
    setResetting(u.id);
    try {
      const r = await api.adminResetPassword(u.id);
      window.prompt(
        `${r.username} için geçici şifre (kopyalayın, kullanıcıya iletin — bir daha gösterilmez):`,
        r.temp_password
      );
    } catch (err) {
      window.alert(`Sıfırlanamadı: ${err.message}`);
    } finally {
      setResetting(null);
    }
  }

  if (loading) return <div className="p-8 text-slate-500">Kullanım verileri yükleniyor…</div>;
  if (error) return <div className="p-8 text-rose-400">Hata: {error}</div>;

  return (
    <div className="space-y-6">
      <h2 className="font-display text-xl font-bold text-slate-100">Kullanım paneli</h2>

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
              <div className="text-[11px] uppercase tracking-wide text-slate-500">Kullanıcı (kayıt/limit)</div>
              <div className={`mt-1 font-display text-2xl font-bold ${over ? "text-rose-400" : "text-slate-100"}`}>
                {label}
              </div>
              <div className={`mt-0.5 text-xs ${over ? "text-rose-400" : "text-slate-500"}`}>
                {over ? "⚠ limit aşıldı!" : stats.max_users > 0 ? "kayıt sınırı" : "sınırsız"}
              </div>
            </div>
          );
        })()}
        <StatCard label="Bugün aktif" value={stats.active_today} hint="en az 1 eylem" />
        <StatCard label="Bugünkü yenileme" value={stats.refreshes_today} />
        {/* Okunmamış geri bildirim — >0 ise mor vurguyla dikkat çeker */}
        <div className={`rounded-xl border bg-ink-800 p-4 shadow-card ${
          stats.unread_feedback > 0 ? "border-accent/50" : "border-ink-600"}`}>
          <div className="text-[11px] uppercase tracking-wide text-slate-500">Okunmamış geri bildirim</div>
          <div className={`mt-1 font-display text-2xl font-bold ${
            stats.unread_feedback > 0 ? "text-accent" : "text-slate-100"}`}>
            {stats.unread_feedback}
          </div>
          <div className="mt-0.5 text-xs text-slate-500">
            {stats.unread_feedback > 0 ? "okunmayı bekliyor" : "hepsi okundu"}
          </div>
        </div>
      </div>

      {/* MALİYET + günlük token bütçesi (herkese açık site maliyet güvencesi) */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {(() => {
          const over = stats.budget_exceeded;
          const label = stats.daily_token_budget > 0
            ? `${(stats.tokens_today / 1000).toFixed(0)}K/${(stats.daily_token_budget / 1000).toFixed(0)}K`
            : `${(stats.tokens_today / 1000).toFixed(0)}K`;
          return (
            <div className={`rounded-xl border bg-ink-800 p-4 shadow-card ${over ? "border-rose-500/50" : "border-ink-600"}`}>
              <div className="text-[11px] uppercase tracking-wide text-slate-500">Bugün token (bütçe)</div>
              <div className={`mt-1 font-display text-2xl font-bold ${over ? "text-rose-400" : "text-slate-100"}`}>{label}</div>
              <div className={`mt-0.5 text-xs ${over ? "text-rose-400" : "text-slate-500"}`}>
                {over ? "⚠ günlük kapasite doldu" : stats.daily_token_budget > 0 ? "günlük tavan" : "sınırsız"}
              </div>
            </div>
          );
        })()}
        <StatCard label="Bugünkü maliyet" value={`$${stats.cost_today_usd.toFixed(2)}`} hint="tahmini (token × birim)" />
        <StatCard label="30 günlük maliyet" value={`$${stats.cost_month_usd.toFixed(2)}`} hint={`${(stats.tokens_month / 1000).toFixed(0)}K token`} />
        <StatCard label="Toplam şirket" value={stats.total_entities} hint="havuzda benzersiz" />
      </div>

      {/* Geri bildirim gelen kutusu — okunmamışlar önce, vurgulu */}
      <FeedbackInbox items={feedback} onMarkRead={markRead} />

      {/* En çok TAKİP EDİLEN şirketler (kaç kullanıcının listesinde) + toplam benzersiz */}
      <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">
            En çok takip edilen şirketler
          </div>
          <div className="text-[11px] text-slate-500">
            Havuzda <span className="font-semibold text-slate-300">{stats.total_entities}</span> benzersiz şirket
          </div>
        </div>
        {stats.most_followed.length === 0 ? (
          <span className="text-sm text-slate-500">Henüz kimse şirket takip etmiyor.</span>
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
                <span className="rounded bg-accent/15 px-1.5 font-semibold text-accent">
                  {e.followers} kişi
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
            En çok görüntülenen şirketler
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
              <th className="px-4 py-2.5">Kullanıcı</th>
              <th className="px-4 py-2.5">Kayıt</th>
              <th className="px-4 py-2.5">Son giriş</th>
              <th className="px-4 py-2.5 text-right">Giriş</th>
              <th className="px-4 py-2.5 text-right">Yenileme</th>
              <th className="px-4 py-2.5 text-right">Toplam eylem</th>
              <th className="px-4 py-2.5">Son aktiflik</th>
              <th className="px-4 py-2.5 text-right">İşlem</th>
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
                    <span className="ml-1.5 rounded bg-accent/15 px-1.5 text-[10px] font-semibold text-accent">
                      admin
                    </span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-slate-500">{fmtDate(u.created_at).split(" ")[0]}</td>
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
                      title="Şifre sıfırla (geçici şifre üret)"
                      className="rounded-md border border-ink-500 px-2 py-1 text-[11px] font-medium text-slate-400 transition hover:bg-ink-700 hover:text-slate-200 disabled:opacity-50"
                    >
                      {resetting === u.id ? "…" : "Şifre"}
                    </button>
                    {u.id === currentUserId ? (
                      <span className="text-[11px] text-slate-600">siz</span>
                    ) : (
                      <button
                        onClick={(e) => handleDelete(u, e)}
                        disabled={deleting === u.id}
                        title="Kullanıcıyı ve tüm verilerini sil"
                        className="rounded-md border border-rose-500/30 px-2 py-1 text-[11px] font-medium text-rose-400 transition hover:bg-rose-500/10 disabled:opacity-50"
                      >
                        {deleting === u.id ? "Siliniyor…" : "Sil"}
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
function FeedbackInbox({ items, onMarkRead }) {
  const unread = items.filter((f) => !f.is_read).length;
  return (
    <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-[11px] uppercase tracking-wide text-slate-500">Geri bildirimler</span>
        {unread > 0 && (
          <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[11px] font-semibold text-accent">
            {unread} okunmamış
          </span>
        )}
        <span className="ml-auto text-[11px] text-slate-500">{items.length} toplam</span>
      </div>

      {items.length === 0 ? (
        <span className="text-sm text-slate-500">Henüz geri bildirim yok.</span>
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
                {!f.is_read ? (
                  <button
                    onClick={() => onMarkRead(f.id)}
                    className="shrink-0 rounded-md border border-ink-500 px-2 py-1 text-[11px] font-medium text-slate-400 transition hover:bg-ink-700 hover:text-slate-200"
                  >
                    Okundu
                  </button>
                ) : (
                  <span className="shrink-0 text-[10px] uppercase tracking-wide text-slate-600">okundu</span>
                )}
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-500">
                <span className="font-medium text-slate-400">
                  {f.username || "anonim"}
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
          {data ? data.user.username : "Yükleniyor…"}
          {data?.user.is_admin && (
            <span className="ml-2 rounded bg-accent/15 px-1.5 text-[10px] font-semibold text-accent">
              admin
            </span>
          )}
        </h3>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-200">
          ✕ kapat
        </button>
      </div>

      {error && <div className="text-sm text-rose-400">Hata: {error}</div>}
      {data && (
        <div className="grid gap-5 md:grid-cols-2">
          {/* Eylem dökümü + en çok baktığı şirketler */}
          <div className="space-y-4">
            <div>
              <div className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">Eylem dökümü</div>
              <div className="flex flex-wrap gap-2">
                {Object.keys(data.event_counts).length === 0 && (
                  <span className="text-sm text-slate-500">Henüz eylem yok.</span>
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
                  En çok baktığı şirketler
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
                İzleme listesi ({data.watchlist_size})
              </div>
              {data.watchlist_size === 0 ? (
                <span className="text-sm text-slate-500">Takip ettiği şirket yok.</span>
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
              Kayıt: {fmtDate(data.user.created_at)} · Son giriş:{" "}
              {data.user.last_login_at ? fmtDate(data.user.last_login_at) : "—"}
            </div>
          </div>

          {/* Zaman çizelgesi — son eylemler */}
          <div>
            <div className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">
              Son eylemler
            </div>
            <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
              {data.recent_events.length === 0 && (
                <span className="text-sm text-slate-500">Kayıt yok.</span>
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
