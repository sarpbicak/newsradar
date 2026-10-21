# shellcheck shell=bash
# NewsRadar AWS runbook değişkenleri ve yardımcıları (docs/DEPLOY_AWS.md, Adım 1). Sır içermez.
#
# Bir kez:            cp deploy/aws/newsradar-env.sh ~/newsradar-env.sh
# Her yeni terminalde: bash            (macOS'ta varsayılan zsh; komutlar bash içindir)
#                      source ~/newsradar-env.sh
# Repo başka bir yerdeyse: NEWSRADAR_REPO=/yol/newsradar source ~/newsradar-env.sh
# Adımların ürettiği kimlikler (instance ID, dağıtım ID …) $STATE_FILE'a yazılır ve burada geri yüklenir.
# shellcheck disable=SC2317  # source edilince return, doğrudan çalıştırılınca exit
[ -n "${BASH_VERSION:-}" ] || { echo "Bu dosya bash ile source edilmeli (önce: bash)"; return 1 2>/dev/null || exit 1; }

cd "$(git -C "${NEWSRADAR_REPO:-$HOME/Desktop/newsradar}" rev-parse --show-toplevel)" || return 1

export AWS_PROFILE=newsradar
export REGION=eu-central-1
export AWS_REGION="$REGION"
export DOMAIN=newsradarapp.com
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)" \
  || echo "UYARI: hesap kimliği alınamadı — SSO oturumu düşmüş olabilir: aws sso login" >&2
export ACCOUNT_ID
export BACKUP_BUCKET="newsradar-backups-${ACCOUNT_ID}"
export FRONTEND_BUCKET="newsradar-frontend-${ACCOUNT_ID}"
export ECR_REPO=newsradar-api
export ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"
export LOG_GROUP=/newsradar/prod
export SSM_PREFIX=/newsradar/prod
export ROLE_NAME=newsradar-ec2-role
export PROFILE_NAME=newsradar-ec2-profile
export SG_NAME=newsradar-api-sg
export INSTANCE_NAME=newsradar-api
export CF_FUNCTION_NAME=newsradar-www-redirect
export OAC_NAME=newsradar-frontend-oac
REPO_URL="https://github.com/$(git remote get-url origin | sed -E 's#^(https://github\.com/|git@github\.com:)##')"
export REPO_URL
export REPO_BRANCH=main
# GitHub Actions (Adım 25): OIDC rolleri yalnızca bu reponun main dalına güvenir.
GITHUB_REPO="$(git remote get-url origin | sed -E 's#^(https://github\.com/|git@github\.com:)##; s#\.git$##')"
export GITHUB_REPO
export GH_BACKEND_ROLE=newsradar-github-backend
export GH_FRONTEND_ROLE=newsradar-github-frontend
export STATE_FILE="$HOME/.newsradar-aws-state.env"

# Durum dosyası: adımların ürettiği kimlikler (sır yok). Yeni terminalde geri yüklenir.
# shellcheck source=/dev/null
touch "$STATE_FILE" && chmod 600 "$STATE_FILE" && . "$STATE_FILE"
save() { # save AD DEĞER → bu oturuma export + durum dosyasına yaz
  export "$1=$2"
  { grep -v "^export $1=" "$STATE_FILE" || true; printf 'export %s=%q\n' "$1" "$2"; } >"$STATE_FILE.tmp"
  mv "$STATE_FILE.tmp" "$STATE_FILE" && chmod 600 "$STATE_FILE"
}
render() { python3 deploy/aws/render.py "$@"; }   # __AD__ yer tutucularını değişkenlerle doldurur
put_param() { # put_param AD TÜR [DEĞER] — değer verilmezse sorulur (SecureString gizli); boş = atla
  local name="$1" type="$2" value="${3-}"
  if [ $# -lt 3 ]; then
    if [ "$type" = SecureString ]; then read -rsp "  $name (gizli; boş = atla): " value; echo
    else read -rp "  $name (boş = atla): " value; fi
  fi
  if [ -z "$value" ]; then echo "  - $name atlandı (uygulama varsayılanı kullanılır)"; return 0; fi
  # Değer stdin'den gider: argv'de (ps) ve shell geçmişinde görünmez.
  printf '%s' "$value" | aws ssm put-parameter --region "$REGION" --name "$SSM_PREFIX/$name" --type "$type" \
    --value file:///dev/stdin --overwrite --query Version --output text >/dev/null && echo "  ✓ $name ($type)"
}
