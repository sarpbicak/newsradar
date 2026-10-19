#!/usr/bin/env bash
# SSM Parameter Store → deploy/.env (EC2'de, instance rolüyle; bölge eu-central-1).
#
#   ./load-secrets.sh                       # /newsradar/prod/* → deploy/.env
#   ./load-secrets.sh --prefix /newsradar/staging/ --output /path/.env
#
# /newsradar/prod/ANTHROPIC_API_KEY → ANTHROPIC_API_KEY='…' (SecureString'ler --with-decryption).
# Parametre listesi: deploy/PARAMETERS.md.
# Güvenlik: değerler HİÇBİR ZAMAN ekrana/log'a yazılmaz (yalnızca adlar). Dosya 600 izinle,
# atomik (geçici dosya + mv) yazılır; önceki sürüm .env.prev olarak kalır. Hedef dosya git
# deposunda izleniyorsa ya da .gitignore dışındaysa betik durur.
set -Eeuo pipefail
umask 077
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_TAG=load-secrets
# shellcheck source=deploy/lib.sh
. "$DEPLOY_DIR/lib.sh"

usage() { sed -n '2,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

PREFIX=/newsradar/prod/
OUT="$DEPLOY_DIR/.env"
while (($#)); do
  case "$1" in
    --prefix) PREFIX="${2:?--prefix bir yol ister}"; shift 2 ;;
    --output) OUT="${2:?--output bir dosya ister}"; shift 2 ;;
    -h | --help) usage; exit 0 ;;
    *) die "bilinmeyen argüman: $1 (--help)" ;;
  esac
done
[[ "$PREFIX" == /*/ ]] || die "--prefix '/' ile başlayıp bitmeli (ör. /newsradar/prod/)"

# Zorunlu parametreler (eksikse .env YAZILMAZ) ve SecureString olması gerekenler.
REQUIRED="DOMAIN APP_SECRET ANTHROPIC_API_KEY NEWSRADAR_CORS_ORIGINS BACKUP_BUCKET"
SECRETS="APP_SECRET APP_PASSWORD ANTHROPIC_API_KEY FINNHUB_API_KEY NEWSAPI_KEY FMP_API_KEY NEWSRADAR_LLM_API_KEY"
# docker-compose.yml'nin sabitlediği değerler (SSM'de olsalar bile compose ezer → uyarı).
COMPOSE_FIXED="NEWSRADAR_DB NEWSRADAR_TRUSTED_PROXY NEWSRADAR_CADDY_IP"

need aws python3
OUT_DIR="$(cd "$(dirname "$OUT")" && pwd)"
OUT="$OUT_DIR/$(basename "$OUT")"

# Depoya asla girmesin: izleniyorsa ya da ignore edilmiyorsa dur.
if git -C "$OUT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git -C "$OUT_DIR" ls-files --error-unmatch "$OUT" >/dev/null 2>&1; then
    die "$OUT git'te İZLENİYOR — sırlar buraya yazılmaz (git rm --cached)"
  fi
  git -C "$OUT_DIR" check-ignore -q "$OUT" || die "$OUT .gitignore kapsamında değil — sırlar buraya yazılmaz"
fi

TMP="$(mktemp "$OUT.tmp.XXXXXX")"
trap 'rm -f "$TMP"' EXIT
trap 'log "HATA: sırlar yüklenemedi (satır $LINENO, kod $?) — mevcut .env değişmedi"' ERR

# JSON → .env. aws çıktısı (değerler) yalnızca bu boruda akar; hiçbir yere yazdırılmaz.
# shellcheck disable=SC2016  # Python kodu, kabuk açılımı yok
PY='
import json, os, re, sys
from datetime import datetime, timezone
prefix, out, required, secrets, fixed = sys.argv[1], sys.argv[2], *(a.split() for a in sys.argv[3:6])
params = json.load(sys.stdin).get("Parameters", [])
env, problems, warnings = {}, [], []
for p in params:
    name, typ = p["Name"], p.get("Type")
    key = name[len(prefix):]
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
        problems.append(f"geçersiz parametre adı: {name}")
        continue
    v = p.get("Value", "")
    if any(c in v for c in "\n\r\0"):
        problems.append(f"{key}: değer satır sonu/NUL içeriyor (.env satırına sığmaz)")
        continue
    if key in secrets and typ != "SecureString":
        warnings.append(f"{key} SecureString değil ({typ}) — şifreli saklayın")
    if key in fixed:
        warnings.append(f"{key} docker-compose.yml tarafından sabitleniyor; SSM değeri kullanılmaz")
    env[key] = v
missing = [k for k in required if not env.get(k)]
if missing:
    problems.append("zorunlu parametre eksik/boş: " + ", ".join(missing))
for w in warnings:
    print(f"UYARI: {w}", file=sys.stderr)
if problems:
    for e in problems:
        print(f"HATA: {e}", file=sys.stderr)
    sys.exit(2)

def quote(v):
    # docker compose env_file: tek tırnak tamamen literal. İçinde tek tırnak varsa çift
    # tırnak + kaçış (\\ \" \$ çözülür, ${...} açılımı olmaz).
    if "\x27" not in v:
        return "\x27" + v + "\x27"
    return "\"" + v.replace("\\", "\\\\").replace("\"", "\\\"").replace("$", "\\$") + "\""

ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
with open(out, "w", encoding="utf-8") as f:
    f.write(f"# load-secrets.sh ile SSM {prefix}* parametrelerinden üretildi ({ts}).\n")
    f.write("# Elle düzenlemeyin (bir sonraki çalıştırmada ezilir). Repoya GİRMEZ.\n")
    for k in sorted(env):
        f.write(f"{k}={quote(env[k])}\n")
os.chmod(out, 0o600)
print(" ".join(sorted(env)))
'

log "okunuyor: ssm:$PREFIX* ($AWS_REGION)"
NAMES="$(aws ssm get-parameters-by-path --path "$PREFIX" --with-decryption \
  --region "$AWS_REGION" --output json \
  | python3 -c "$PY" "$PREFIX" "$TMP" "$REQUIRED" "$SECRETS" "$COMPOSE_FIXED")"

[[ -f "$OUT" ]] && cp -p "$OUT" "$OUT.prev"
mv -f "$TMP" "$OUT"
chmod 600 "$OUT"
log "yazıldı: $OUT (izin 600, $(wc -w <<<"$NAMES" | tr -d ' ') parametre): $NAMES"

# Varsayılan konumdaysa compose dosyasıyla birlikte geçerli mi (değerler yazdırılmaz).
if [[ "$OUT" == "$DEPLOY_DIR/.env" ]] && command -v docker >/dev/null 2>&1; then
  dc config -q && log "docker compose config: geçerli"
fi
