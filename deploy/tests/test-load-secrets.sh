#!/usr/bin/env bash
# load-secrets.sh testi — sahte aws (deploy/tests/aws) ile, AWS'ye dokunmadan.
# Doğrular: değerler compose'a BİREBİR ulaşır (tırnak/$/#/boşluk/unicode), izin 600,
# değerler log'a sızmaz, zorunlu eksikse mevcut .env değişmez, String tipli sır uyarısı,
# git'te izlenen/ignore dışı hedef reddedilir, Python 3.9 (Amazon Linux 2023) ile aynı çıktı.
# `koşul && ok || bad`: ok() her zaman 0 döner, bu yüzden if-then-else ile eşdeğer.
# shellcheck disable=SC2015
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="$(dirname "$HERE")"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
export PATH="$HERE:$PATH" FAKE_SSM_JSON="$T/ssm.json" FAKE_AWS_LOG="$T/aws.log"
FAILS=0
ok() { echo "  ✓ $1"; }
bad() { echo "  ✗ $1"; FAILS=$((FAILS + 1)); }

# Sahte (gerçek olmayan) değerler; zor karakterler bilerek.
python3 - "$T/ssm.json" <<'PY'
import json, sys
P = "/newsradar/prod/"
vals = {
    "DOMAIN": ("String", "newsradarapp.com"),
    "APP_SECRET": ("SecureString", "FAKE-secret-it's \"q\" $HOME ${X} \\n #x"),
    "ANTHROPIC_API_KEY": ("SecureString", "sk-ant-api03-FAKEFAKEFAKEFAKEFAKE"),
    "APP_PASSWORD": ("SecureString", "FAKE pass # not comment"),
    "FINNHUB_API_KEY": ("String", "FAKE-finnhub-plain"),
    "NEWSRADAR_CORS_ORIGINS": ("String", "https://newsradarapp.com,https://www.newsradarapp.com"),
    "NEWSRADAR_CONTACT_EMAIL": ("String", "privacy@example.com"),
    "BACKUP_BUCKET": ("String", "newsradar-backups-example"),
    "BACKEND_IMAGE": ("String", "123456789012.dkr.ecr.eu-central-1.amazonaws.com/newsradar-api:prod"),
    "NEWSRADAR_HOSTING_PROVIDER": ("String", "AWS (Frankfurt) — şifreli ✓"),
}
json.dump({"Parameters": [{"Name": P + k, "Type": t, "Value": v} for k, (t, v) in vals.items()]},
          open(sys.argv[1], "w"))
json.dump({k: v for k, (t, v) in vals.items()}, open(sys.argv[1] + ".expected", "w"))
PY

echo "== normal çalıştırma"
mkdir -p "$T/proj"
cp "$DEPLOY/docker-compose.yml" "$T/proj/"
"$DEPLOY/load-secrets.sh" --output "$T/proj/.env" >"$T/out.log" 2>&1 && ok "çıkış kodu 0" || { bad "çıkış kodu ≠ 0"; cat "$T/out.log"; }
perm="$(stat -f %Lp "$T/proj/.env" 2>/dev/null || stat -c %a "$T/proj/.env")"
[[ "$perm" == 600 ]] && ok "izin 600" || bad "izin $perm"
leak=0
while IFS= read -r v; do
  [[ ${#v} -ge 6 ]] && grep -qF -- "$v" "$T/out.log" "$T/aws.log" && leak=1
done < <(python3 -c 'import json,sys; [print(v) for v in json.load(open(sys.argv[1])).values() if v.startswith(("FAKE", "sk-ant"))]' "$FAKE_SSM_JSON.expected")
((leak == 0)) && ok "sır değerleri log'da yok" || bad "SIR LOG'A SIZDI"
grep -q "FINNHUB_API_KEY SecureString değil" "$T/out.log" && ok "String tipli sır için uyarı" || bad "String sır uyarısı yok"

if command -v docker >/dev/null 2>&1; then
  docker compose --project-directory "$T/proj" -f "$T/proj/docker-compose.yml" config --format json >"$T/cfg.json"
  python3 - "$T/cfg.json" "$FAKE_SSM_JSON.expected" <<'PY' && ok "compose değerleri birebir (tırnak, \$, #, boşluk, unicode)" || bad "compose değerleri farklı"
import json, sys
env = json.load(open(sys.argv[1]))["services"]["backend"]["environment"]
exp = json.load(open(sys.argv[2]))
bad = [k for k, v in exp.items() if env.get(k, "").replace("$$", "$") != v]
if bad:
    print("    farklı:", bad); sys.exit(1)
PY
fi

echo "== zorunlu parametre eksik"
cp "$T/proj/.env" "$T/before.env"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["Parameters"]=[p for p in d["Parameters"] if not p["Name"].endswith("/APP_SECRET")]; json.dump(d, open(sys.argv[1],"w"))' "$FAKE_SSM_JSON"
if "$DEPLOY/load-secrets.sh" --output "$T/proj/.env" >"$T/out2.log" 2>&1; then bad "eksik zorunluya rağmen 0 döndü"; else ok "sıfır olmayan çıkış ($(grep -o 'zorunlu parametre eksik/boş: .*' "$T/out2.log"))"; fi
cmp -s "$T/before.env" "$T/proj/.env" && ok "mevcut .env değişmedi" || bad "mevcut .env değişti"
leftover=("$T"/proj/.env.tmp.*)
[[ -e "${leftover[0]}" ]] && bad "geçici dosya kaldı" || ok "geçici dosya kalmadı"

echo "== repo içinde ignore dışı hedef"
if "$DEPLOY/load-secrets.sh" --output "$DEPLOY/secrets-test.txt" >"$T/out3.log" 2>&1; then bad "reddedilmedi"; else ok "reddedildi: $(grep -o '\.gitignore kapsamında değil' "$T/out3.log")"; fi
[[ -e "$DEPLOY/secrets-test.txt" ]] && { bad "dosya oluştu"; rm -f "$DEPLOY/secrets-test.txt"; } || true

if command -v docker >/dev/null 2>&1; then
  echo "== Python 3.9 (Amazon Linux 2023'teki python3) ile aynı çıktı"
  python3 -c 'import json,sys; d={"Parameters":[{"Name":"/newsradar/prod/"+k,"Type":"SecureString","Value":v} for k,v in json.load(open(sys.argv[1])).items()]}; json.dump(d, open(sys.argv[2],"w"))' "$FAKE_SSM_JSON.expected" "$T/ssm39.json"
  FAKE_SSM_JSON="$T/ssm39.json" "$DEPLOY/load-secrets.sh" --output "$T/host.env" >/dev/null 2>&1
  docker run --rm -v "$DEPLOY:/d:ro" -v "$T:/t" -e PATH=/d/tests:/usr/local/bin:/usr/bin:/bin \
    -e FAKE_SSM_JSON=/t/ssm39.json python:3.9-slim bash /d/load-secrets.sh --output /t/py39.env >"$T/out4.log" 2>&1 \
    && diff <(tail -n +2 "$T/host.env") <(tail -n +2 "$T/py39.env") >/dev/null \
    && ok "python 3.9 çıktısı aynı" || { bad "python 3.9 farklı/başarısız"; cat "$T/out4.log"; }
fi

echo "== $([[ $FAILS -eq 0 ]] && echo "TAMAM" || echo "$FAILS HATA")"
exit $((FAILS > 0))
