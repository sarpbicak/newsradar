// i18n bütünlüğü (tarayıcı gerekmez): yenileme özeti metni ve anahtar çakışması.
import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { refreshParts, ttFor } from "../src/i18n.jsx";

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

// Aynı anahtar iki kez tanımlanırsa JS nesnesinde ikincisi SESSİZCE birincinin yerine geçer
// (kök neden: 'notice.queued' hem özet sayacı hem kuyruk durumu için kullanılmıştı).
test("i18n anahtarları tek tanımlı (sözlük + bileşenlerin addStrings blokları)", () => {
  const files = [];
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p);
    else if (/\.jsx?$/.test(e.name)) files.push(p);
  });
  walk(SRC);
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
