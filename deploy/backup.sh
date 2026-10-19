#!/usr/bin/env bash
# NewsRadar SQLite yedeği → s3://$BACKUP_BUCKET/backups/newsradar-YYYYMMDD-HHMM.db.gz (UTC).
#
#   ./backup.sh                  # S3'e (EC2: instance rolü; bölge eu-central-1)
#   ./backup.sh --dry-run DIR    # S3 yerine DIR/backups/ (yerel test)
#
# Akış: sqlite3 .backup (çalışan DB'nin tutarlı anlık görüntüsü, dosya kopyası DEĞİL) →
# PRAGMA integrity_check → gzip (+ gzip -t) → yükle → S3'te boyut doğrulaması.
# Herhangi bir adım başarısızsa log yazılır ve sıfır olmayan kodla çıkılır.
# BACKUP_BUCKET: ortamdan ya da deploy/.env'den (load-secrets.sh SSM'den yazar).
# Gerekenler: docker (compose), sqlite3, gzip; S3 modunda aws CLI.
set -Eeuo pipefail
umask 077
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_TAG=backup
# shellcheck source=deploy/lib.sh
. "$DEPLOY_DIR/lib.sh"

usage() { sed -n '2,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

DRY_DIR=""
while (($#)); do
  case "$1" in
    --dry-run) DRY_DIR="${2:?--dry-run bir klasör ister}"; shift 2 ;;
    -h | --help) usage; exit 0 ;;
    *) die "bilinmeyen argüman: $1 (--help)" ;;
  esac
done

trap 'log "HATA: yedekleme başarısız (satır $LINENO, kod $?)"' ERR
need docker sqlite3 gzip
BUCKET=""
if [[ -z "$DRY_DIR" ]]; then
  need aws
  BUCKET="${BACKUP_BUCKET:-$(dotenv_get BACKUP_BUCKET)}"
  [[ -n "$BUCKET" ]] || die "BACKUP_BUCKET tanımlı değil (ortam ya da deploy/.env)"
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
NAME="newsradar-$(date -u +%Y%m%d-%H%M).db.gz"
SNAP="$WORK/newsradar.db"

log "başladı: $NAME ($([[ -n "$DRY_DIR" ]] && echo "dry-run → $DRY_DIR" || echo "s3://$BUCKET/backups/"))"
snapshot_to_stdout >"$SNAP"
[[ -s "$SNAP" ]] || die "anlık görüntü boş"
sqlite_ok "$SNAP" || die "anlık görüntü bütünlük kontrolünden geçmedi"
schema_ok "$SNAP" || die "anlık görüntü NewsRadar şemasını taşımıyor"
log "anlık görüntü tamam: $(wc -c <"$SNAP" | tr -d ' ') bayt, integrity_check=ok, $(row_summary "$SNAP")"

gzip -9 -c "$SNAP" >"$WORK/$NAME"
gzip -t "$WORK/$NAME" || die "gzip doğrulaması başarısız"
SIZE="$(wc -c <"$WORK/$NAME" | tr -d ' ')"

if [[ -n "$DRY_DIR" ]]; then
  mkdir -p "$DRY_DIR/backups"
  cp "$WORK/$NAME" "$DRY_DIR/backups/$NAME"
  DEST="$DRY_DIR/backups/$NAME"
else
  KEY="backups/$NAME"
  aws s3 cp "$WORK/$NAME" "s3://$BUCKET/$KEY" --region "$AWS_REGION" --only-show-errors
  REMOTE="$(aws s3api head-object --bucket "$BUCKET" --key "$KEY" --region "$AWS_REGION" \
    --query ContentLength --output text)"
  [[ "$REMOTE" == "$SIZE" ]] || die "S3 boyutu uyuşmuyor (yerel $SIZE, S3 $REMOTE)"
  DEST="s3://$BUCKET/$KEY"
fi
log "tamam: $DEST ($SIZE bayt)"
