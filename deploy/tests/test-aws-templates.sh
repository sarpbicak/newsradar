#!/usr/bin/env bash
# deploy/iam + deploy/aws şablonlarının yerel testi (AWS'ye istek YOK; sahte değerler).
# Doğrular: her şablon render.py ile eksiksiz dolar ve geçerli JSON üretir; eksik değişken
# hata verir; IAM'de "*" yalnızca ecr:GetAuthorizationToken'da; "Action": "*" yok;
# CloudFront Function davranışı (node); render edilmiş user-data shellcheck'ten geçer.
# `koşul && ok || bad`: ok() her zaman 0 döner, bu yüzden if-then-else ile eşdeğer.
# shellcheck disable=SC2015
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="$(dirname "$HERE")"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
FAILS=0
ok() { echo "  ✓ $1"; }
bad() { echo "  ✗ $1"; FAILS=$((FAILS + 1)); }

export REGION=eu-central-1 ACCOUNT_ID=123456789012 DOMAIN=example.com ECR_REPO=newsradar-api \
  BACKUP_BUCKET=newsradar-backups-123456789012 FRONTEND_BUCKET=newsradar-frontend-123456789012 \
  LOG_GROUP=/newsradar/prod DISTRIBUTION_ID=E1EXAMPLE OAC_ID=E2EXAMPLE CF_CALLER_REF=test-1 \
  SSM_KMS_KEY_ARN=arn:aws:kms:eu-central-1:123456789012:key/00000000-0000-0000-0000-000000000000 \
  CERT_ARN=arn:aws:acm:us-east-1:123456789012:certificate/00000000-0000-0000-0000-000000000000 \
  CF_FUNCTION_ARN=arn:aws:cloudfront::123456789012:function/newsradar-www-redirect \
  REPO_URL=git@github.com:example/newsradar.git REPO_BRANCH=main

echo "== render"
for f in "$DEPLOY"/iam/*.json "$DEPLOY"/aws/*.json "$DEPLOY"/aws/user-data.sh; do
  name="${f#"$DEPLOY"/}"
  if python3 "$DEPLOY/aws/render.py" "$f" >"$T/$(basename "$f")" 2>"$T/err"; then
    if grep -qE '__[A-Z][A-Z0-9_]*__' "$T/$(basename "$f")"; then bad "$name: doldurulmamış yer tutucu"; else ok "$name"; fi
  else
    bad "$name: $(cat "$T/err")"
  fi
done
if (unset ACCOUNT_ID; python3 "$DEPLOY/aws/render.py" "$DEPLOY/iam/ec2-instance-policy.json" >/dev/null 2>"$T/err"); then
  bad "eksik değişken fark edilmedi"
else
  ok "eksik değişken → hata ($(cut -c1-70 "$T/err"))"
fi

echo "== IAM en az yetki"
python3 - "$T/ec2-instance-policy.json" "$T/frontend-bucket-policy.json" <<'PY' && ok "'*' yalnızca ecr:GetAuthorizationToken'da; joker eylem yok" || bad "IAM'de beklenmeyen joker"
import json, sys
bad = []
for path in sys.argv[1:]:
    for st in json.load(open(path))["Statement"]:
        acts = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
        res = st.get("Resource", [])
        res = res if isinstance(res, list) else [res]
        if any("*" in a for a in acts):
            bad.append(f"{st['Sid']}: joker eylem {acts}")
        if "*" in res and acts != ["ecr:GetAuthorizationToken"]:
            bad.append(f"{st['Sid']}: Resource '*'")
for b in bad:
    print("    " + b)
sys.exit(1 if bad else 0)
PY

echo "== CloudFront Function (www → apex)"
if command -v node >/dev/null 2>&1; then
  node - "$DEPLOY/aws/www-redirect.js" <<'JS' && ok "301 + yol/sorgu korunur; apex dokunulmadan geçer" || bad "CloudFront Function davranışı"
const fs = require("fs");
eval(fs.readFileSync(process.argv[2], "utf8") + "; globalThis.handler = handler;");
const ev = (host, uri, qs) => ({ request: { uri, headers: host ? { host: { value: host } } : {}, querystring: qs || {} } });
const cases = [
  [ev("www.example.com", "/a/b", { q: { value: "x%20y" }, t: { value: "1", multiValue: [{ value: "1" }, { value: "2" }] }, f: { value: "" } }),
   "https://example.com/a/b?q=x%20y&t=1&t=2&f"],
  [ev("www.example.com", "/", {}), "https://example.com/"],
];
let ok = true;
for (const [e, want] of cases) {
  const r = handler(e);
  if (r.statusCode !== 301 || r.headers.location.value !== want) { ok = false; console.log("    got", JSON.stringify(r)); }
}
const pass = handler(ev("example.com", "/x", {}));
if (pass.uri !== "/x" || pass.statusCode) { ok = false; console.log("    apex değişti", pass); }
if (handler(ev(null, "/", {})).uri !== "/") { ok = false; console.log("    host'suz istek"); }
process.exit(ok ? 0 : 1);
JS
else
  echo "  - node yok, atlandı"
fi

echo "== user-data (render edilmiş) shellcheck"
if command -v docker >/dev/null 2>&1; then
  if docker run --rm -e LANG=C.UTF-8 -v "$T:/mnt:ro" -w /mnt koalaman/shellcheck:v0.11.0 -S style user-data.sh; then
    ok "shellcheck temiz"
  else
    bad "shellcheck bulguları"
  fi
fi
grep -q '"HttpVersion": "http2and3"' "$T/cloudfront-distribution.json" && ok "CloudFront: HTTP/2+3" || bad "HTTP/3 kapalı"
grep -q '"ViewerProtocolPolicy": "redirect-to-https"' "$T/cloudfront-distribution.json" && ok "CloudFront: HTTP → HTTPS" || bad "HTTPS zorlanmıyor"

echo "== $([[ $FAILS -eq 0 ]] && echo "TAMAM" || echo "$FAILS HATA")"
exit $((FAILS > 0))
