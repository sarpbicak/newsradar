#!/usr/bin/env bash
# NewsRadar geri yükleme: S3'teki bir yedeği canlı DB'nin yerine koyar.
#
#   ./restore.sh                                   # en son yedek (onay sorar)
#   ./restore.sh newsradar-20261019-0315.db.gz     # belirli bir yedek
#   ./restore.sh --yes [AD]                        # onaysız (otomasyon)
#   ./restore.sh --dry-run DIR [--yes] [AD]        # S3 yerine DIR/backups/ (yerel test;
#                                                  #   DB yine GERÇEKTEN değiştirilir)
#
# Sıra: backend'i durdur → mevcut DB'nin yerel kopyası (SAFETY_DIR) → yedeği indir →
# doğrula (gzip -t, integrity_check, şema) → yerine koy → başlat → /health (container + Caddy).
# Doğrulama başarısızsa mevcut DB'ye dokunulmaz; /health başarısızsa eski DB geri konur.
# Her iki durumda da servis yeniden başlatılır ve sıfır olmayan kodla çıkılır.
set -Eeuo pipefail
umask 077
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_TAG=restore
# shellcheck source=deploy/lib.sh
. "$DEPLOY_DIR/lib.sh"

usage() { sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

DRY_DIR=""
YES=0
NAME=""
while (($#)); do
  case "$1" in
    --dry-run) DRY_DIR="${2:?--dry-run bir klasör ister}"; shift 2 ;;
    --yes) YES=1; shift ;;
    -h | --help) usage; exit 0 ;;
    -*) die "bilinmeyen argüman: $1 (--help)" ;;
    *) [[ -z "$NAME" ]] || die "tek bir yedek adı verin"; NAME="${1#backups/}"; shift ;;
  esac
done

SAFETY_DIR="${SAFETY_DIR:-$DEPLOY_DIR/local-backups/pre-restore}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"
need docker sqlite3 gzip curl
BUCKET=""
if [[ -z "$DRY_DIR" ]]; then
  need aws
  BUCKET="${BACKUP_BUCKET:-$(dotenv_get BACKUP_BUCKET)}"
  [[ -n "$BUCKET" ]] || die "BACKUP_BUCKET tanımlı değil (ortam ya da deploy/.env)"
fi

list_names() {
  if [[ -n "$DRY_DIR" ]]; then
    find "$DRY_DIR/backups" -maxdepth 1 -type f -name 'newsradar-*.db.gz' -exec basename {} \; 2>/dev/null
  else
    aws s3api list-objects-v2 --bucket "$BUCKET" --prefix backups/newsradar- --region "$AWS_REGION" \
      --query 'Contents[].Key' --output text | tr '\t' '\n' | sed 's|^backups/||'
  fi
}

# Container sağlığı (Dockerfile HEALTHCHECK) → "healthy" olana dek bekler.
wait_healthy() {
  local i id status
  for ((i = 0; i < HEALTH_TIMEOUT; i += 2)); do
    id="$(dc ps -q "$SERVICE")"
    status="$(docker inspect -f '{{.State.Health.Status}}' "$id" 2>/dev/null || echo none)"
    [[ "$status" == healthy ]] && return 0
    sleep 2
  done
  log "backend $HEALTH_TIMEOUT sn içinde healthy olmadı (son durum: ${status:-?})"
  return 1
}

# Dışarıdan, Caddy üzerinden /health (DOMAIN: ortam ya da deploy/.env).
edge_healthy() {
  local domain host i
  domain="${DOMAIN:-$(dotenv_get DOMAIN)}"
  if [[ -z "$domain" ]]; then
    log "DOMAIN yok; Caddy üzerinden kontrol atlandı"
    return 0
  fi
  host="api.$domain"
  local args=(-fsS --max-time 10 -o /dev/null)
  [[ "$host" == *localhost ]] && args+=(-k --resolve "$host:443:127.0.0.1")
  for i in 1 2 3 4 5; do
    curl "${args[@]}" "https://$host/health" 2>/dev/null && return 0
    sleep "$i"
  done
  log "https://$host/health yanıt vermedi"
  return 1
}

# Host dosyasını /data/newsradar.db yapar (backend DURMUŞKEN). WAL/SHM artıkları silinir:
# eski DB'nin WAL'ı yeni dosyaya uygulanırsa veritabanı bozulur.
put_db() {
  # shellcheck disable=SC2016  # $1 container kabuğunda açılır
  dc run --rm -T --no-deps "$SERVICE" sh -c 'set -e; db="$1"
    cat >"$db.restore"; rm -f "$db-wal" "$db-shm"; mv -f "$db.restore" "$db"' sh "$DB_IN_CONTAINER" <"$1"
}

STAGE=init # init → stopped (DB aynı) → replaced (DB değişti) → finished
PRE=""
WORK=""

recover() {
  set +e
  case "$STAGE" in
    stopped)
      log "mevcut DB'ye dokunulmadı; backend yeniden başlatılıyor"
      dc up -d "$SERVICE" && wait_healthy && log "servis eski DB ile ayakta"
      ;;
    replaced)
      if [[ -n "$PRE" ]]; then
        log "eski DB geri konuyor: $PRE"
        if dc stop "$SERVICE" && put_db "$PRE" && dc up -d "$SERVICE" && wait_healthy; then
          log "servis eski DB ile ayakta"
        else
          log "KRİTİK: geri alma başarısız — elle müdahale gerekli (kopya: $PRE)"
        fi
      else
        log "KRİTİK: restore öncesi DB yoktu; backend olduğu gibi başlatılıyor"
        dc up -d "$SERVICE"
      fi
      ;;
  esac
}

on_exit() {
  local rc=$?
  if ((rc != 0)); then
    log "HATA: geri yükleme başarısız (aşama: $STAGE, kod $rc)"
    recover
  fi
  [[ -n "$WORK" ]] && rm -rf "$WORK"
  exit "$rc"
}
trap on_exit EXIT
trap 'log "HATA: komut başarısız (satır $LINENO, kod $?)"' ERR

# --- 0) Hangi yedek? ---
if [[ -z "$NAME" ]]; then
  NAME="$(list_names | grep -E "$BACKUP_NAME_RE" | sort | tail -n 1 || true)"
  [[ -n "$NAME" ]] || die "yedek bulunamadı ($([[ -n "$DRY_DIR" ]] && echo "$DRY_DIR/backups" || echo "s3://$BUCKET/backups/"))"
  log "en son yedek seçildi: $NAME"
fi
[[ "$NAME" =~ $BACKUP_NAME_RE ]] || die "geçersiz yedek adı: $NAME (beklenen newsradar-YYYYMMDD-HHMM.db.gz)"
if ((YES == 0)); then
  [[ -t 0 ]] || die "onay gerekli: etkileşimsiz çalıştırmada --yes verin"
  read -r -p "Canlı veritabanı '$NAME' ile DEĞİŞTİRİLECEK. Devam için 'evet' yazın: " answer
  [[ "$answer" == evet ]] || die "iptal edildi"
fi
WORK="$(mktemp -d)"
mkdir -p "$SAFETY_DIR"

# --- 1) Servisi durdur ---
log "backend durduruluyor"
dc stop "$SERVICE"
STAGE=stopped

# --- 2) Mevcut DB'nin yerel kopyası ---
if in_backend test -s "$DB_IN_CONTAINER"; then
  PRE="$SAFETY_DIR/pre-restore-$(date -u +%Y%m%d-%H%M%S).db"
  snapshot_to_stdout >"$PRE"
  sqlite_ok "$PRE" || log "UYARI: mevcut DB bütünlük kontrolünden geçmedi (kopya yine saklandı)"
  log "mevcut DB kopyalandı: $PRE ($(row_summary "$PRE"))"
else
  log "mevcut DB yok (boş volume) — kopya alınmadı"
fi

# --- 3) Yedeği indir ---
if [[ -n "$DRY_DIR" ]]; then
  [[ -f "$DRY_DIR/backups/$NAME" ]] || die "yedek yok: $DRY_DIR/backups/$NAME"
  cp "$DRY_DIR/backups/$NAME" "$WORK/$NAME"
else
  aws s3 cp "s3://$BUCKET/backups/$NAME" "$WORK/$NAME" --region "$AWS_REGION" --only-show-errors
fi
log "yedek indirildi: $NAME ($(wc -c <"$WORK/$NAME" | tr -d ' ') bayt)"

# --- 4) Doğrula ---
gzip -t "$WORK/$NAME" 2>/dev/null || die "yedek gzip doğrulamasından geçmedi"
gzip -dc "$WORK/$NAME" >"$WORK/restore.db"
sqlite_ok "$WORK/restore.db" || die "yedek bütünlük kontrolünden geçmedi"
schema_ok "$WORK/restore.db" || die "yedek NewsRadar şemasını taşımıyor"
log "yedek doğrulandı: integrity_check=ok, $(row_summary "$WORK/restore.db")"

# --- 5) Yerine koy ---
STAGE=replaced
put_db "$WORK/restore.db"
log "yedek yerine kondu"

# --- 6) Başlat + 7) /health ---
dc up -d "$SERVICE"
wait_healthy || die "backend sağlıklı başlamadı"
edge_healthy || die "Caddy üzerinden /health başarısız"
STAGE=finished
log "tamam: $NAME geri yüklendi, /health 200$([[ -n "$PRE" ]] && echo "; önceki DB: $PRE")"
