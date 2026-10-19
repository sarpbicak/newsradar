# shellcheck shell=bash
# backup.sh / restore.sh / load-secrets.sh ortak yardımcıları (doğrudan çalıştırılmaz).
# Çağıran betik DEPLOY_DIR ve LOG_TAG'i tanımlar.

AWS_REGION="${AWS_REGION:-eu-central-1}"
SERVICE=backend
DB_IN_CONTAINER="${DB_IN_CONTAINER:-/data/newsradar.db}"
# Yedek adı: newsradar-YYYYMMDD-HHMM.db.gz (UTC). Başka her ad reddedilir (yol enjeksiyonu yok).
# shellcheck disable=SC2034  # restore.sh kullanır
BACKUP_NAME_RE='^newsradar-[0-9]{8}-[0-9]{4}\.db\.gz$'

# Zaman damgalı log: stderr (systemd → journald) + LOG_FILE (tanımlıysa).
log() {
  local line
  line="$(date -u +%Y-%m-%dT%H:%M:%SZ) [${LOG_TAG:-newsradar}] $*"
  printf '%s\n' "$line" >&2
  if [[ -n "${LOG_FILE:-}" ]]; then
    printf '%s\n' "$line" >>"$LOG_FILE" 2>/dev/null || true
  fi
}

die() {
  log "HATA: $*"
  exit 1
}

need() {
  local c
  for c in "$@"; do
    command -v "$c" >/dev/null 2>&1 || die "gerekli komut yok: $c"
  done
}

# deploy/.env'den TEK bir anahtarın değeri (tırnaklar soyulur). Dosya source EDİLMEZ:
# sırlar kabuk değişkenine/ortama gereksiz yere açılmasın.
dotenv_get() {
  local line
  line="$(grep -E "^$1=" "$DEPLOY_DIR/.env" 2>/dev/null | tail -n 1)" || true
  line="${line#*=}"
  if [[ "$line" == \'*\' || "$line" == \"*\" ]]; then
    line="${line:1:${#line}-2}"
  fi
  printf '%s' "$line"
}

dc() {
  docker compose --project-directory "$DEPLOY_DIR" -f "$DEPLOY_DIR/docker-compose.yml" "$@"
}

backend_running() {
  [[ -n "$(dc ps -q --status running "$SERVICE" 2>/dev/null)" ]]
}

# Komutu backend container'ında çalıştırır: çalışıyorsa exec, durmuşsa aynı volume'lü
# tek seferlik container (uid 10001 → /data'daki dosyaların sahipliği doğru kalır).
in_backend() {
  if backend_running; then
    dc exec -T "$SERVICE" "$@"
  else
    dc run --rm -T --no-deps "$SERVICE" "$@"
  fi
}

# Canlı DB'nin tutarlı anlık görüntüsünü (sqlite3 .backup — çevrimiçi yedek API'si) stdout'a yazar.
# Geçici dosya /data'da (aynı dosya sistemi; tmpfs RAM'i şişmez) ve her durumda silinir.
snapshot_to_stdout() {
  # shellcheck disable=SC2016  # $1/$2 container kabuğunda açılır
  # DB yoksa sqlite3 sessizce BOŞ bir DB yaratırdı → "sağlam ama boş" yedek. Önce varlık kontrolü.
  in_backend sh -c 'set -e; tmp="$1"; trap "rm -f \"$tmp\"" EXIT
    [ -s "$2" ] || { echo "DB yok ya da boş: $2" >&2; exit 3; }
    sqlite3 "$2" ".backup \"$tmp\""; cat "$tmp"' sh "/data/.snapshot-$$.db" "$DB_IN_CONTAINER"
}

# Host'taki bir SQLite dosyasını PRAGMA integrity_check ile doğrular ("ok" dışı = hata).
sqlite_ok() {
  local out
  out="$(sqlite3 "$1" 'PRAGMA integrity_check;' 2>&1)" || {
    log "integrity_check çalışmadı ($1): ${out:0:300}"
    return 1
  }
  if [[ "$out" != "ok" ]]; then
    log "integrity_check başarısız ($1): ${out:0:300}"
    return 1
  fi
}

# Dosya NewsRadar şemasını taşıyor mu (boş/yanlış DB'yi geri yüklemeyi/yüklemeyi engeller).
schema_ok() {
  local n
  n="$(sqlite3 "$1" "SELECT count(*) FROM sqlite_master WHERE type='table'
    AND name IN ('users','entities','articles','entity_analyses');" 2>/dev/null)" || n=0
  [[ "$n" == 4 ]] || { log "beklenen tablolar yok ($1): NewsRadar veritabanı değil"; return 1; }
}

# Özet satır sayıları (log için; değer içermez).
row_summary() {
  sqlite3 "$1" "SELECT 'users=' || (SELECT count(*) FROM users) || ' entities=' || (SELECT count(*) FROM entities)
    || ' articles=' || (SELECT count(*) FROM articles) || ' analyses=' || (SELECT count(*) FROM entity_analyses);" 2>/dev/null \
    || echo "özet okunamadı"
}
