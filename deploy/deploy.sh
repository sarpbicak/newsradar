#!/usr/bin/env bash
# Backend'i BACKEND_IMAGE (ECR, :prod) ile günceller; sağlıksızsa makinedeki önceki image'a döner.
#
#   git -C /opt/newsradar pull --ff-only && /opt/newsradar/deploy/deploy.sh     # instance, root
#
# GitHub Actions bunu SSM Run Command ile çağırır (deploy/ci/release-backend.sh); elle de çalışır.
# Sıra: load-secrets.sh → ECR login → compose pull backend → up -d --no-build → healthy +
# smoke-test.sh. Başarısızsa önceki image ID'si aynı etikete geri bağlanıp servis yeniden kurulur.
# Çıkış: 0 yeni sürüm ayakta · 1 yeni sürüm sağlıksız, ÖNCEKİ image ile ayakta · 2 geri dönüş de
# başarısız (elle müdahale) · 3 deploy'dan önce beklenmeyen hata (ör. load-secrets, pull; servis
# değişmedi). Kod çekme (git pull) bu betiğin dışında: çalışan betik değişmesin.
#
# Yerel test: BACKEND_IMAGE ortamdan verilebilir (compose da ortamdakini kullanır);
# DEPLOY_SKIP_SECRETS=1 load-secrets.sh'i atlar (yerel deploy/.env'yi ezmemek için).
set -Eeuo pipefail
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_TAG=deploy
# shellcheck source=deploy/lib.sh
. "$DEPLOY_DIR/lib.sh"

# Beklenmeyen hata → 3 (1 ve 2 yalnızca aşağıdaki açık sonuçlar için).
die() { log "HATA: $*"; exit 3; }   # lib.sh'teki die 1 döner; burada 1 = "geri dönüldü"
trap 'log "HATA: komut başarısız (satır $LINENO, kod $?)"; exit 3' ERR
need docker curl

if [[ "${DEPLOY_SKIP_SECRETS:-}" != 1 ]]; then
  "$DEPLOY_DIR/load-secrets.sh"
fi
BACKEND_IMAGE="${BACKEND_IMAGE:-$(dotenv_get BACKEND_IMAGE)}"
DOMAIN="${DOMAIN:-$(dotenv_get DOMAIN)}"
[[ -n "$BACKEND_IMAGE" ]] || die "BACKEND_IMAGE tanımlı değil (SSM /newsradar/prod/BACKEND_IMAGE)"
[[ -n "$DOMAIN" ]] || die "DOMAIN tanımlı değil"
export BACKEND_IMAGE

registry="${BACKEND_IMAGE%%/*}"
if [[ "$registry" == *.dkr.ecr.*.amazonaws.com ]]; then
  need aws
  aws ecr get-login-password --region "$AWS_REGION" \
    | docker login --username AWS --password-stdin "$registry" >/dev/null
  log "ECR girişi tamam"
fi

image_id() { docker image inspect -f '{{.Id}}' "$BACKEND_IMAGE" 2>/dev/null || true; }
healthy_and_smoke() { wait_healthy && "$DEPLOY_DIR/smoke-test.sh" "api.$DOMAIN"; }

PREV_ID="$(image_id)"
dc pull "$SERVICE"
NEW_ID="$(image_id)"
log "image: önceki ${PREV_ID:-yok} → yeni $NEW_ID"
# compose, Caddy'nin depends_on (service_healthy) koşulu yüzünden yeni backend sağlıksızsa hata
# döner: bu bir "dur" sebebi değil, karar aşağıdaki sağlık kontrolünde (geri dönüş orada).
dc up -d --no-build || log "compose up hata döndü (yeni backend sağlıksız olabilir) — kontrol ediliyor"

if healthy_and_smoke; then
  log "tamam: yeni sürüm ayakta"
  exit 0
fi

log "HATA: yeni sürüm sağlıksız (healthcheck ya da smoke-test başarısız)"
dc logs --tail 40 "$SERVICE" >&2 || true
if [[ -z "$PREV_ID" || "$PREV_ID" == "$NEW_ID" ]]; then
  log "KRİTİK: geri dönülecek önceki image yok (ilk deploy ya da aynı image)"
  exit 2
fi
log "geri dönülüyor: $PREV_ID"
docker tag "$PREV_ID" "$BACKEND_IMAGE"
dc up -d --no-build || log "compose up hata döndü — kontrol ediliyor"
if healthy_and_smoke; then
  log "önceki image ile ayakta (yeni sürüm reddedildi)"
  exit 1
fi
log "KRİTİK: önceki image ile de ayağa kalkmadı — elle müdahale gerekli"
exit 2
