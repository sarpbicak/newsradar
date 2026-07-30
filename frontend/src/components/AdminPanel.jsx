// Admin kullanım paneli — yalnızca is_admin kullanıcı görür (backend 403 ile korur).
// Genel istatistik + kullanıcı tablosu + tıklanınca kullanıcı detayı (eylem dökümü,
// en çok baktığı şirketler, zaman çizelgesi). Veri ORTAK; bu sadece 'kim ne yaptı'.
import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { timeAgo } from "./ui.jsx";

const EVENT_LABELS = {
  login: "giriş",
  refresh: "yenileme",
  view_entity: "görüntüleme",
  add_entity: "şirket ekleme",
  remove_entity: "şirket çıkarma",
  chat: "sohbet",
  add_suggestion: "öneri ekleme",
  dismiss_suggestion: "öneri gizleme",
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

export default function AdminPanel() {
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null); // seçili kullanıcı id

  useEffect(() => {
    let alive = true;
    Promise.all([api.adminStats(), api.adminUsers()])
      .then(([s, u]) => {
        if (!alive) return;
        setStats(s);
        setUsers(u);
      })
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  if (loading) return <div className="p-8 text-slate-500">Kullanım verileri yükleniyor…</div>;
  if (error) return <div className="p-8 text-rose-400">Hata: {error}</div>;

  return (
    <div className="space-y-6">
      <h2 className="font-display text-xl font-bold text-slate-100">Kullanım paneli</h2>

      {/* Genel istatistik */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Toplam kullanıcı" value={stats.total_users} />
        <StatCard label="Bugün aktif" value={stats.active_today} hint="en az 1 eylem" />
        <StatCard label="Bugünkü yenileme" value={stats.refreshes_today} />
        <StatCard
          label="En popüler"
          value={stats.top_entities[0]?.name || "—"}
          hint={stats.top_entities[0] ? `${stats.top_entities[0].count} görüntüleme` : ""}
        />
      </div>

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
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected != null && <UserDetail userId={selected} onClose={() => setSelected(null)} />}
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
                    {ev.detail?.name && (
                      <span className="text-slate-500"> · {ev.detail.name}</span>
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
