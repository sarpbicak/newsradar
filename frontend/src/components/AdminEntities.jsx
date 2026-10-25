// Admin "Şirketler": havuzdaki şirketlerin GÖRÜNEN adını düzenleme (ham ad, sembol, analizler
// değişmez). Boş bırakılırsa otomatik ada döner (placeholder'da görünür). En fazla 60 karakter.
// Uzun havuzda filtre ile aranır. Metinler yalnızca bu (admin) pakette.
import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { addStrings, tt } from "../i18n.jsx";
import { Button, Card, Input, Skeleton } from "./kit.jsx";

addStrings({
  "ent.title": { tr: "Şirketler · görünen ad", en: "Companies · display name" },
  "ent.note": { tr: "Yalnızca kartlarda görünen ad değişir; boş bırakırsan otomatik ada döner (en fazla {n} karakter).", en: "Only the name shown on cards changes; leave it empty to return to the automatic name (max {n} characters)." },
  "ent.filter": { tr: "Şirket ara", en: "Search companies" },
  "ent.save": { tr: "Kaydet", en: "Save" },
  "ent.saved": { tr: "Kaydedildi", en: "Saved" },
  "ent.label": { tr: "{name} için görünen ad", en: "Display name for {name}" },
  "ent.followers": { tr: "{n} kişi", en: "{n} people" },
  "ent.followers_one": { tr: "{n} kişi", en: "{n} person" },
  "ent.empty": { tr: "Eşleşen şirket yok.", en: "No matching companies." },
});

const MAX = 60;

function Row({ row, onSaved }) {
  const [value, setValue] = useState(row.display_name || "");
  const [state, setState] = useState(null); // null | "busy" | "saved" | hata metni
  const changed = value.trim().replace(/\s+/g, " ") !== (row.display_name || "");
  const tooLong = value.trim().length > MAX;
  async function save(e) {
    e.preventDefault();
    if (!changed || tooLong || state === "busy") return;
    setState("busy");
    try {
      const updated = await api.adminSetDisplayName(row.id, value.trim() || null);
      setValue(updated.display_name || "");
      onSaved(updated);
      setState("saved");
    } catch (err) {
      setState(err.message);
    }
  }
  const id = `ent-${row.id}`;
  return (
    <li className="py-3">
      <form onSubmit={save} className="grid gap-2 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_auto] sm:items-center">
        <div className="min-w-0">
          <div className="truncate text-meta text-slate-200" title={row.name}>{row.name}</div>
          <div className="font-mono text-micro text-slate-500">
            {row.type === "ticker" ? "$" : "#"}{row.query} · {tt("ent.followers", { n: row.followers })}
          </div>
        </div>
        <div>
          <label htmlFor={id} className="sr-only">{tt("ent.label", { name: row.name })}</label>
          <Input
            id={id}
            value={value}
            onChange={(e) => { setValue(e.target.value); setState(null); }}
            placeholder={row.auto_display_name || row.name}
            maxLength={MAX + 20}
            aria-invalid={tooLong || undefined}
          />
        </div>
        <div className="flex items-center gap-2">
          <Button type="submit" size="sm" variant="secondary" disabled={!changed || tooLong || state === "busy"}>{tt("ent.save")}</Button>
          <span className="min-w-16 text-micro" role="status">
            {state === "saved" && <span className="text-emerald-600">{tt("ent.saved")}</span>}
            {tooLong && <span className="text-rose-600">{value.trim().length}/{MAX}</span>}
            {state && state !== "saved" && state !== "busy" && <span className="text-rose-600">{state}</span>}
          </span>
        </div>
      </form>
    </li>
  );
}

export default function AdminEntities() {
  const [rows, setRows] = useState(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    api.adminEntities().then(setRows).catch(() => setRows([]));
  }, []);
  const shown = useMemo(() => {
    const k = q.trim().toLocaleLowerCase();
    const all = rows || [];
    return (k ? all.filter((r) => `${r.name} ${r.display_name || ""} ${r.query}`.toLocaleLowerCase().includes(k)) : all).slice(0, 50);
  }, [rows, q]);
  if (rows == null) return <Skeleton className="h-40 w-full" />;
  return (
    <Card className="p-5">
      <h3 className="font-display text-sm font-medium text-slate-200">{tt("ent.title")}</h3>
      <p className="mt-1 text-micro text-slate-500">{tt("ent.note", { n: MAX })}</p>
      <div className="mt-3 max-w-sm">
        <label htmlFor="ent-filter" className="sr-only">{tt("ent.filter")}</label>
        <Input id="ent-filter" value={q} onChange={(e) => setQ(e.target.value)} placeholder={tt("ent.filter")} />
      </div>
      {shown.length ? (
        <ul className="mt-2 divide-y divide-ink-600">
          {shown.map((r) => (
            <Row key={r.id} row={r} onSaved={(u) => setRows((prev) => prev.map((x) => (x.id === u.id ? u : x)))} />
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-meta text-slate-500">{tt("ent.empty")}</p>
      )}
    </Card>
  );
}
