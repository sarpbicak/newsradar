#!/usr/bin/env bash
# deploy/ci/release-backend.sh testi — sahte aws (deploy/tests/aws) ile, AWS'ye dokunmadan.
# Senaryolar: başarılı yayın · CRITICAL bulgu (prod'a dokunulmaz, SSM çağrılmaz) · tarama
# tamamlanmadı · EC2'de deploy başarısız (prod etiketi önceki digest'e döner) · ilk deploy
# başarısız (geri alınacak etiket yok) · prod zaten bu image'da (ImageAlreadyExists).
# `koşul && ok || bad`: ok() her zaman 0 döner, bu yüzden if-then-else ile eşdeğer.
# shellcheck disable=SC2015
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="$(dirname "$HERE")"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
export PATH="$HERE:$PATH" AWS_REGION=eu-central-1 ECR_REPOSITORY=newsradar-api INSTANCE_ID=i-0123456789abcdef0 POLL=0
FAILS=0
ok() { echo "  ✓ $1"; }
bad() { echo "  ✗ $1"; FAILS=$((FAILS + 1)); }

setup() { # setup <prev-digest|-> <new-scan "DURUM CRITICAL HIGH">
  export FAKE_ECR_DIR="$T/ecr-$RANDOM"
  mkdir -p "$FAKE_ECR_DIR"/{tags,manifests,scan}
  if [[ "$1" != - ]]; then
    echo '{"schemaVersion":2,"layers":["old"]}' >"$FAKE_ECR_DIR/manifests/$1"
    echo "$1" >"$FAKE_ECR_DIR/tags/oldsha"; echo "$1" >"$FAKE_ECR_DIR/tags/prod"
  fi
  echo '{"schemaVersion":2,"layers":["new"]}' >"$FAKE_ECR_DIR/manifests/sha256:new"
  echo "sha256:new" >"$FAKE_ECR_DIR/tags/newsha"
  echo "$2" >"$FAKE_ECR_DIR/scan/sha256:new"
}
prod() { cat "$FAKE_ECR_DIR/tags/prod" 2>/dev/null || echo yok; }
run() { IMAGE_TAG=newsha "$DEPLOY/ci/release-backend.sh" >"$T/out.log" 2>&1; }

echo "== başarılı yayın"
setup sha256:old "COMPLETE None 2"
FAKE_SSM_STATUS=Success FAKE_SSM_CODE=0 run && ok "çıkış 0" || { bad "çıkış ≠ 0"; cat "$T/out.log"; }
[[ "$(prod)" == sha256:new ]] && ok "prod → yeni digest" || bad "prod: $(prod)"
python3 - "$FAKE_ECR_DIR/ssm-params.json" <<'PY' && ok "SSM: git pull --ff-only + deploy/deploy.sh + HOME" || bad "SSM komutları eksik"
import json, sys
c = json.load(open(sys.argv[1]))["commands"]
assert "git pull --ff-only" in c and "deploy/deploy.sh" in c and any("HOME=/root" in x for x in c), c
PY
grep -q "CRITICAL=0 · HIGH=2" "$T/out.log" && ok "None → 0 olarak okundu" || bad "tarama sayıları"

echo "== CRITICAL bulgu"
setup sha256:old "COMPLETE 3 1"
run && bad "CRITICAL'e rağmen 0 döndü" || ok "çıkış ≠ 0 ($(grep -o '3 CRITICAL bulgu' "$T/out.log"))"
[[ "$(prod)" == sha256:old ]] && ok "prod etiketi değişmedi" || bad "prod değişti: $(prod)"
[[ ! -f "$FAKE_ECR_DIR/ssm-params.json" ]] && ok "SSM çağrılmadı" || bad "SSM çağrıldı"

echo "== tarama tamamlanmadı"
setup sha256:old "FAILED None None"
run && bad "0 döndü" || ok "çıkış ≠ 0 (tarama FAILED)"
[[ "$(prod)" == sha256:old ]] && ok "prod etiketi değişmedi" || bad "prod değişti"

echo "== EC2'de deploy başarısız → etiket geri"
setup sha256:old "COMPLETE None None"
FAKE_SSM_STATUS=Failed FAKE_SSM_CODE=1 run && bad "0 döndü" || ok "çıkış ≠ 0"
[[ "$(prod)" == sha256:old ]] && ok "prod önceki digest'e geri alındı" || bad "prod: $(prod)"
grep -q "EC2 önceki image ile ayakta" "$T/out.log" && ok "log: makinede önceki image" || bad "log eksik"

echo "== geri dönüş de başarısız (kod 2)"
setup sha256:old "COMPLETE None None"
FAKE_SSM_STATUS=Failed FAKE_SSM_CODE=2 run && bad "0 döndü" || ok "çıkış ≠ 0"
grep -q "KRİTİK" "$T/out.log" && [[ "$(prod)" == sha256:old ]] && ok "KRİTİK log + prod geri" || bad "kod 2 işlenmedi"

echo "== ilk deploy başarısız (önceki prod yok)"
setup - "COMPLETE None None"
FAKE_SSM_STATUS=TimedOut FAKE_SSM_CODE=-1 run && bad "0 döndü" || ok "çıkış ≠ 0"
grep -q "önceki prod image'ı yok" "$T/out.log" && ok "uyarı: geri alınacak etiket yok" || bad "uyarı eksik"

echo "== prod zaten bu image'da"
setup sha256:old "COMPLETE None None"
echo sha256:new >"$FAKE_ECR_DIR/tags/prod"
FAKE_SSM_STATUS=Success run && ok "ImageAlreadyExists hata sayılmadı" || { bad "çıkış ≠ 0"; cat "$T/out.log"; }

echo "== $([[ $FAILS -eq 0 ]] && echo "TAMAM" || echo "$FAILS HATA")"
exit $((FAILS > 0))
