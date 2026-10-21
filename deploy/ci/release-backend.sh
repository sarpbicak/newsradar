#!/usr/bin/env bash
# GitHub Actions (deploy-backend.yml, "deploy" job): ECR'daki $IMAGE_TAG image'ını yayına alır.
#
# Gerekli ortam: AWS_REGION, ECR_REPOSITORY, IMAGE_TAG (commit SHA), INSTANCE_ID; kimlik OIDC rolünden.
# 1) Push sırasında başlayan temel taramayı bekle; CRITICAL bulgu varsa DUR (prod'a dokunulmaz).
# 2) prod etiketini bu image'a taşı (önceki prod digest'i saklanır).
# 3) SSM Run Command ile EC2'de: git pull --ff-only → deploy/deploy.sh (smoke-test dahil).
# 4) Başarısızsa prod etiketini önceki digest'e geri al ve sıfır olmayan kodla çık.
#    (deploy.sh makinede zaten önceki image'a dönmüştür; burada ECR'daki etiket de tutarlı olur.)
set -Eeuo pipefail
: "${AWS_REGION:?}" "${ECR_REPOSITORY:?}" "${IMAGE_TAG:?}" "${INSTANCE_ID:?}"
SSM_TIMEOUT="${SSM_TIMEOUT:-1200}"   # sn: komutun bitmesi için en fazla bekleme
POLL="${POLL:-10}"

log() { printf '%s [release] %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }
ecr() { aws ecr --region "$AWS_REGION" "$@"; }

digest_of() { # etiket → digest (yoksa boş)
  ecr describe-images --repository-name "$ECR_REPOSITORY" --image-ids "imageTag=$1" \
    --query 'imageDetails[0].imageDigest' --output text 2>/dev/null | grep -v '^None$' || true
}

point_prod_to() { # digest → prod etiketi (manifest yeniden yazılmaz, yalnızca etiket)
  local manifest media out
  manifest="$(ecr batch-get-image --repository-name "$ECR_REPOSITORY" --image-ids "imageDigest=$1" \
    --query 'images[0].imageManifest' --output text)"
  media="$(ecr batch-get-image --repository-name "$ECR_REPOSITORY" --image-ids "imageDigest=$1" \
    --query 'images[0].imageManifestMediaType' --output text)"
  if ! out="$(ecr put-image --repository-name "$ECR_REPOSITORY" --image-tag prod \
    --image-manifest "$manifest" --image-manifest-media-type "$media" 2>&1)"; then
    # Etiket zaten bu digest'teyse ECR ImageAlreadyExistsException döner: hedef durum sağlanmış.
    [[ "$out" == *ImageAlreadyExistsException* ]] || { log "put-image başarısız: $out"; return 1; }
  fi
}

# --- 1) Tarama kapısı ---
log "tarama bekleniyor: $ECR_REPOSITORY:$IMAGE_TAG"
ecr wait image-scan-complete --repository-name "$ECR_REPOSITORY" --image-id "imageTag=$IMAGE_TAG"
read -r scan_status critical high < <(ecr describe-image-scan-findings --repository-name "$ECR_REPOSITORY" \
  --image-id "imageTag=$IMAGE_TAG" \
  --query '[imageScanStatus.status, imageScanFindings.findingSeverityCounts.CRITICAL, imageScanFindings.findingSeverityCounts.HIGH]' \
  --output text)
[[ "$critical" == None ]] && critical=0
[[ "$high" == None ]] && high=0
log "tarama: $scan_status · CRITICAL=$critical · HIGH=$high"
if [[ "$scan_status" != COMPLETE ]]; then
  log "HATA: tarama tamamlanmadı ($scan_status) — yayına alınmıyor"
  exit 1
fi
if ((critical > 0)); then
  log "HATA: $critical CRITICAL bulgu — yayına alınmıyor (prod etiketi değişmedi)"
  exit 1
fi

# --- 2) prod etiketini taşı ---
NEW_DIGEST="$(digest_of "$IMAGE_TAG")"
[[ -n "$NEW_DIGEST" ]] || { log "HATA: $IMAGE_TAG bulunamadı"; exit 1; }
PREV_DIGEST="$(digest_of prod)"
log "prod: ${PREV_DIGEST:-yok} → $NEW_DIGEST"
point_prod_to "$NEW_DIGEST"

rollback_tag() {
  if [[ -n "$PREV_DIGEST" && "$PREV_DIGEST" != "$NEW_DIGEST" ]]; then
    point_prod_to "$PREV_DIGEST" && log "prod etiketi önceki image'a geri alındı: $PREV_DIGEST"
  else
    log "UYARI: önceki prod image'ı yok — etiket geri alınamadı"
  fi
}

# --- 3) EC2'de deploy (SSM Run Command) ---
params="$(mktemp)"
trap 'rm -f "$params"' EXIT
python3 - "$params" "$AWS_REGION" "$IMAGE_TAG" <<'PY'
import json, sys
path, region, tag = sys.argv[1:4]
commands = [
    "set -euo pipefail",
    f"export HOME=/root AWS_REGION={region}",       # RunShellScript'te HOME yok (docker login için)
    "cd /opt/newsradar",
    "git pull --ff-only",
    f'head="$(git rev-parse HEAD)"; [ "$head" = "{tag}" ] || echo "UYARI: repo HEAD $head, image {tag}"',
    "deploy/deploy.sh",
]
json.dump({"commands": commands, "executionTimeout": ["900"]}, open(path, "w"))
PY
command_id="$(aws ssm send-command --region "$AWS_REGION" --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript --comment "deploy ${IMAGE_TAG:0:12}" \
  --timeout-seconds 600 --parameters "file://$params" --query Command.CommandId --output text)"
log "SSM komutu: $command_id"

status=Pending
code=-1
for ((waited = 0; waited < SSM_TIMEOUT; waited += POLL)); do
  sleep "$POLL"
  if ! read -r status code < <(aws ssm get-command-invocation --region "$AWS_REGION" \
    --command-id "$command_id" --instance-id "$INSTANCE_ID" \
    --query '[Status, ResponseCode]' --output text 2>/dev/null); then
    status=Pending   # InvocationDoesNotExist: komut instance'a henüz ulaşmadı
    continue
  fi
  case "$status" in Pending | InProgress | Delayed) continue ;; *) break ;; esac
done

echo "::group::EC2 çıktısı (deploy.sh)"
aws ssm get-command-invocation --region "$AWS_REGION" --command-id "$command_id" --instance-id "$INSTANCE_ID" \
  --query '[StandardOutputContent, StandardErrorContent]' --output text 2>/dev/null || true
echo "::endgroup::"

# --- 4) Sonuç ---
if [[ "$status" == Success ]]; then
  log "tamam: $IMAGE_TAG yayında"
  exit 0
fi
case "$code" in
  1) log "HATA: yeni sürüm sağlıksız; EC2 önceki image ile ayakta" ;;
  2) log "KRİTİK: EC2'de geri dönüş de başarısız — elle müdahale (docs/DEPLOY_AWS.md, Adım 22)" ;;
  3) log "HATA: deploy.sh deploy'dan önce durdu (load-secrets/ECR/pull); servis değişmedi" ;;
  *) log "HATA: SSM komutu '$status' (kod $code) — deploy tamamlanmadı" ;;
esac
rollback_tag
exit 1
