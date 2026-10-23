// E2E yığını: anahtarsız backend + derlenmiş frontend, iki düzende.
//   local: frontend http://localhost:4174, API http://localhost:8899 (ayrı port, aynı site)
//   prod : frontend https://app.newsradar.test:4443, API https://api.newsradar.test:8443
//          (production gibi ayrı alt alan adları; Secure + SameSite=lax + .newsradar.test cookie)
// Kullanım: node e2e/stack.mjs <api|web> <local|prod>  (playwright.config.js webServer'dan)
//
// GÜVENLİK: tüm API anahtarları BOŞ verilir. backend/.env yüklense bile load_dotenv mevcut
// ortam değişkenlerini ezmez → testler hiçbir zaman gerçek LLM/haber API'si çağırmaz.
import { execFileSync, spawn } from "node:child_process";
import fs from "node:fs";
import https from "node:https";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(HERE, "..");
const BACKEND = path.resolve(FRONTEND, "..", "backend");
export const CERT_DIR = path.join(HERE, ".certs");

export const TARGETS = {
  local: {
    web: "http://localhost:4174",
    api: "http://localhost:8899",
    webPort: 4174,
    apiPort: 8899,
    tls: false,
    cookie: { NEWSRADAR_COOKIE_SECURE: "off", NEWSRADAR_COOKIE_SAMESITE: "lax", NEWSRADAR_COOKIE_DOMAIN: "" },
  },
  prod: {
    web: "https://app.newsradar.test:4443",
    api: "https://api.newsradar.test:8443",
    webPort: 4443,
    apiPort: 8443,
    tls: true,
    cookie: { NEWSRADAR_COOKIE_SECURE: "on", NEWSRADAR_COOKIE_SAMESITE: "lax", NEWSRADAR_COOKIE_DOMAIN: ".newsradar.test" },
  },
};

const NO_KEYS = {
  ANTHROPIC_API_KEY: "",
  NEWSRADAR_LLM_API_KEY: "",
  NEWSRADAR_LLM_PROVIDER: "anthropic",
  FINNHUB_API_KEY: "",
  NEWSAPI_KEY: "",
  FMP_API_KEY: "",
};

// *.newsradar.test için kendinden imzalı sertifika (yoksa üretilir; tarayıcı ignoreHTTPSErrors).
export function ensureCert() {
  const key = path.join(CERT_DIR, "key.pem");
  const cert = path.join(CERT_DIR, "cert.pem");
  if (fs.existsSync(key) && fs.existsSync(cert)) return { key, cert };
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "nr-cert-"));
  execFileSync("openssl", [
    "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "30",
    "-keyout", path.join(tmp, "key.pem"), "-out", path.join(tmp, "cert.pem"),
    "-subj", "/CN=newsradar.test",
    "-addext", "subjectAltName=DNS:*.newsradar.test,DNS:newsradar.test,IP:127.0.0.1",
  ], { stdio: "ignore" });
  fs.mkdirSync(CERT_DIR, { recursive: true });
  fs.copyFileSync(path.join(tmp, "key.pem"), key);
  fs.copyFileSync(path.join(tmp, "cert.pem"), cert);
  return { key, cert };
}

function startApi(t) {
  const db = path.join(os.tmpdir(), `nr_e2e_${t.apiPort}.db`);
  for (const sfx of ["", "-wal", "-shm"]) fs.rmSync(db + sfx, { force: true });
  const args = ["-m", "uvicorn", "app.api.main:app", "--host", "127.0.0.1", "--port", String(t.apiPort)];
  if (t.tls) {
    const { key, cert } = ensureCert();
    args.push("--ssl-keyfile", key, "--ssl-certfile", cert);
  }
  const child = spawn(process.env.PYTHON || "python", args, {
    cwd: BACKEND,
    stdio: "inherit",
    env: {
      ...process.env,
      ...NO_KEYS,
      ...t.cookie,
      NEWSRADAR_DB: db,
      APP_PASSWORD: "e2e-genel-sifre",
      APP_SECRET: "e2e-secret-1234567890",
      ADMIN_USERNAME: "e2eadmin",
      NEWSRADAR_SCHEDULER: "off",
      NEWSRADAR_SEED_ON_START: "off",
      NEWSRADAR_MAX_USERS: "0",
      NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR: "0",
      NEWSRADAR_TRUSTED_PROXY: "render",
      FRONTEND_URL: t.web,
    },
  });
  child.on("exit", (code) => process.exit(code ?? 1));
  for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill(sig));
}

// Derle (API adresi gömülü) ve SPA olarak sun: bilinmeyen yollar index.html'e düşer.
function startWeb(t) {
  const out = path.join(HERE, `.dist-${t.webPort}`);
  execFileSync("npx", ["vite", "build", "--outDir", out, "--emptyOutDir", "--logLevel", "warn"], {
    cwd: FRONTEND,
    stdio: "inherit",
    env: { ...process.env, VITE_API_URL: t.api },
  });
  const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
    ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json", ".webmanifest": "application/manifest+json",
    ".woff2": "font/woff2" };
  const handler = (req, res) => {
    const url = decodeURIComponent(new URL(req.url, "http://x").pathname);
    let file = path.join(out, url);
    if (!file.startsWith(out) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(out, "index.html");
    res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  };
  const server = t.tls
    ? https.createServer((({ key, cert }) => ({ key: fs.readFileSync(key), cert: fs.readFileSync(cert) }))(ensureCert()), handler)
    : http.createServer(handler);
  server.listen(t.webPort, "127.0.0.1");
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [what, mode] = process.argv.slice(2);
  const t = TARGETS[mode];
  if (!t || !["api", "web"].includes(what)) {
    console.error("kullanım: node e2e/stack.mjs <api|web> <local|prod>");
    process.exit(2);
  }
  (what === "api" ? startApi : startWeb)(t);
}
