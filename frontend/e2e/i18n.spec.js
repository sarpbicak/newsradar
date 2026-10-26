// i18n bütünlüğü (tarayıcı gerekmez): yenileme özeti metni, anahtar çakışması, kodda kullanılan
// anahtarların varlığı, üç dilin (TR/EN/DE) eksiksizliği ve de-DE biçimleri.
import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { fmtDate, loadLang, refreshParts, timeAgo, ttFor } from "../src/i18n.jsx";
import { I18nProvider } from "../src/i18n.jsx";
import { fmtMoney } from "../src/money.js";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");

test("biten yenilemenin özeti kuyruk durumunu ('Sıradasın') içermez", () => {
  const sm = { fetched_new: 364, llm_articles: 40, prefiltered: 5, discarded: 3, queued: 12 };
  const tr = refreshParts(sm, ttFor("tr")).join(" · ");
  const en = refreshParts(sm, ttFor("en")).join(" · ");
  expect(tr).toBe("364 yeni makale · bu taramada 40 analiz · 8 elendi · 12 makale sonraki taramada");
  expect(en).toBe("364 new articles · 40 analyzed this run · 8 filtered out · 12 queued for next refresh");
  expect(tr).not.toContain("Sıradasın");
  expect(refreshParts({ ...sm, queued: 1 }, ttFor("tr")).at(-1)).toBe("1 makale sonraki taramada");
});

function sourceFiles() {
  const files = [];
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p);
    else if (/\.jsx?$/.test(e.name)) files.push(p);
  });
  walk(SRC);
  return files;
}

function definedKeys(files) {
  const keys = new Set();
  for (const f of files) {
    const text = fs.readFileSync(f, "utf8");
    if (!/STR = \{|addStrings\(\{/.test(text)) continue;
    for (const m of text.matchAll(/^\s+"([a-zA-Z][\w.]*)": \{ tr:/gm)) keys.add(m[1]);
  }
  return keys;
}

// Sözlük satırları: "anahtar": { tr: "…", en: "…" } → {key, tr, en}.
const Q = `"(?:[^"\\\\]|\\\\.)*"`;
function entries(files) {
  const out = [];
  const re = new RegExp(`^\\s+"([a-zA-Z][\\w.]*)": \\{ tr: (${Q}), en: (${Q}) \\},?\\s*$`, "gm");
  for (const f of files) {
    const text = fs.readFileSync(f, "utf8");
    if (!/STR = \{|addStrings\(\{/.test(text)) continue;
    for (const m of text.matchAll(re)) out.push({ key: m[1], tr: JSON.parse(m[2]), en: JSON.parse(m[3]) });
  }
  return out;
}
const vars = (str) => [...new Set([...str.matchAll(/\{(\w+)\}/g)].map((m) => m[1]))].sort().join(",");
const DE = JSON.parse(fs.readFileSync(path.join(SRC, "locales/de.json"), "utf8"));

// Aynı anahtar iki kez tanımlanırsa JS nesnesinde ikincisi SESSİZCE birincinin yerine geçer
// (kök neden: 'notice.queued' hem özet sayacı hem kuyruk durumu için kullanılmıştı).
test("i18n anahtarları tek tanımlı (sözlük + bileşenlerin addStrings blokları)", () => {
  const files = sourceFiles();
  const seen = new Map();
  const dups = [];
  for (const f of files) {
    const text = fs.readFileSync(f, "utf8");
    if (!/STR = \{|addStrings\(\{/.test(text)) continue;
    for (const m of text.matchAll(/^\s+"([a-zA-Z][\w.]*)": \{ tr:/gm)) {
      const where = `${path.relative(SRC, f)}`;
      if (seen.has(m[1])) dups.push(`${m[1]} (${seen.get(m[1])} + ${where})`);
      else seen.set(m[1], where);
    }
  }
  expect(dups).toEqual([]);
  expect(seen.size).toBeGreaterThan(500);
});

// Sabit anahtarla çağrılan t("…") / tt("…") sözlükte yoksa ekranda anahtarın kendisi görünür
// (kök neden: 'chat.qWhy' üçe bölünmüş, landing ve "nasıl çalışır" eski anahtarı kullanıyordu).
test("kodda sabit yazılan her i18n anahtarı sözlükte var", () => {
  const files = sourceFiles();
  const keys = definedKeys(files);
  const missing = [];
  for (const f of files) {
    const text = fs.readFileSync(f, "utf8");
    for (const m of text.matchAll(/\b(?:t|tt|tr)\("([a-z][\w]*\.[\w.]+)"/g)) {
      const k = m[1];
      if (!keys.has(k) && !keys.has(`${k}_one`)) missing.push(`${k} (${path.relative(SRC, f)})`);
    }
  }
  expect([...new Set(missing)]).toEqual([]);
});

// Üç dil eksiksiz: her anahtarın TR, EN ve DE metni var (locales/de.json: tüm Almanca metinler,
// e-posta metinleri dahil). Eksik ya da fazla anahtarda, yer tutucu farkında kırılır.
test("üç dil eksiksiz: her anahtar TR, EN ve DE'de var, yer tutucular aynı", () => {
  const files = sourceFiles();
  const all = entries(files);
  expect(all.length).toBe(definedKeys(files).size); // tüm satırlar ayrıştırıldı
  const problems = [];
  const intentionallyEmpty = (e) => e.tr === "" && e.en === "" && DE[e.key] === "";
  for (const e of all) {
    if (!(e.key in DE)) { problems.push(`DE eksik: ${e.key}`); continue; }
    if (!intentionallyEmpty(e)) {
      for (const [lang, v] of [["tr", e.tr], ["en", e.en], ["de", DE[e.key]]]) if (!v.trim()) problems.push(`${lang} boş: ${e.key}`);
    }
    if (vars(e.en) !== vars(DE[e.key])) problems.push(`yer tutucu farkı: ${e.key} (en: ${vars(e.en)} · de: ${vars(DE[e.key])})`);
    if (vars(e.en) !== vars(e.tr) && !e.key.endsWith("_one")) problems.push(`yer tutucu farkı: ${e.key} (en: ${vars(e.en)} · tr: ${vars(e.tr)})`);
  }
  const known = new Set(all.map((e) => e.key));
  for (const k of Object.keys(DE)) if (!known.has(k) && !k.startsWith("email.")) problems.push(`DE fazla: ${k}`);
  expect(problems).toEqual([]);
});

test("Almanca metinlerde uzun tire yok", () => {
  expect(Object.entries(DE).filter(([, v]) => /—| – /.test(v)).map(([k]) => k)).toEqual([]);
});

test("DE: sözlükten metin, tekil/çoğul ve de-DE biçimleri", async () => {
  await loadLang("de");
  const t = ttFor("de");
  expect(t("header.refresh")).toBe("Aktualisieren");
  expect(t("notice.newArticles", { n: 1 })).toBe("1 neuer Artikel");
  expect(t("notice.newArticles", { n: 3 })).toBe("3 neue Artikel");
  expect(t("err.password_short", { n: 8 })).toBe("Das Passwort muss mindestens 8 Zeichen haben."); // appStrings anahtarı da DE'de
  const sp = (v) => v.replace(/\u00a0|\u202f/g, " "); // Intl: sembolden önce bölünmez boşluk
  expect(sp(fmtMoney(238.14, "USD", "de"))).toBe("238,14 $");
  expect(sp(fmtMoney(1234.5, "EUR", "de"))).toBe("1.234,50 €");
  // fmtDate/timeAgo modül dilini okur: I18nProvider dili ayarlar (render etmeden çağrı yeter).
  I18nProvider({ lang: "de", setLang: () => {}, children: null });
  expect(sp(fmtDate("2026-10-25T12:00:00Z"))).toBe("25. Okt.");
  expect(sp(timeAgo(new Date(Date.now() - 2 * 3600 * 1000).toISOString()))).toBe("vor 2 Stunden");
  expect(timeAgo(new Date(Date.now() - 10 * 1000).toISOString())).toBe("gerade eben");
  I18nProvider({ lang: "tr", setLang: () => {}, children: null });
});
