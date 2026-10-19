#!/usr/bin/env bash
# backup.sh + restore.sh uçtan uca testi — ÇALIŞAN yerel stack'e karşı (deploy/: docker compose up).
# DİKKAT: yerel DB'yi değiştirir ve geri yükler (sonunda başlangıçtaki içerik geri gelir).
# S3 yerine: --dry-run klasörü ve sahte aws (deploy/tests/aws → yerel klasör). AWS'ye dokunulmaz.
#
# Doğrular: yedek al → DB'yi boz → restore → TÜM tabloların satır sayıları yedekle aynı;
# S3 modu (sahte aws) aynı sonucu verir; bozuk yedek reddedilir ve DB'ye dokunulmaz;
# /health başarısızsa eski DB geri konur; hatalı durumlarda çıkış kodu ≠ 0.
# check() ifadeleri eval ile çalıştırır: tek tırnak (SC2016), yalnızca ifadelerde geçen
# değişkenler (SC2034) ve dolaylı çağrılan fonksiyonlar (SC2329) bilerek böyle.
# shellcheck disable=SC2016,SC2034,SC2329
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="$(dirname "$HERE")"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
export PATH="$HERE:$PATH" FAKE_S3_DIR="$T/s3" FAKE_AWS_LOG="$T/aws.log" SAFETY_DIR="$T/pre"
FAILS=0
ok() { echo "  ✓ $1"; }
bad() { echo "  ✗ $1"; FAILS=$((FAILS + 1)); }
check() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

dc() { docker compose --project-directory "$DEPLOY" -f "$DEPLOY/docker-compose.yml" "$@"; }
sql() { dc exec -T backend sqlite3 /data/newsradar.db "$1"; }
# Tüm tabloların satır sayıları tek satırda: "articles=157 entities=5 …"
counts() {
  local q
  q="$(sql "SELECT group_concat('SELECT ''' || name || '=''' || ' || count(*) FROM \"' || name || '\"', ' UNION ALL ')
            FROM (SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name);")"
  sql "$q" | sort | paste -sd ' ' -
}
healthy() { [[ "$(docker inspect -f '{{.State.Health.Status}}' "$(dc ps -q backend)")" == healthy ]]; }
run() { "$@" >"$T/last.log" 2>&1; }

dc ps --status running -q backend | grep -q . || { echo "stack çalışmıyor: cd deploy && docker compose up -d"; exit 2; }
BEFORE="$(counts)"
echo "başlangıç: $BEFORE"

echo "== 1) yedek (dry-run → yerel klasör)"
check "backup.sh --dry-run çıkış 0" 'run "$DEPLOY/backup.sh" --dry-run "$T/local"'
F="$(find "$T/local/backups" -name 'newsradar-*.db.gz' | head -n 1)"
check "dosya adı newsradar-YYYYMMDD-HHMM.db.gz ($(basename "$F"))" '[[ "$(basename "$F")" =~ ^newsradar-[0-9]{8}-[0-9]{4}\.db\.gz$ ]]'
check "gzip -t + integrity_check (yedek dosyası)" 'gzip -t "$F" && gzip -dc "$F" >"$T/check.db" && [[ "$(sqlite3 "$T/check.db" "PRAGMA integrity_check")" == ok ]]'

echo "== 2) yedek (S3 modu, sahte aws)"
check "backup.sh (BACKUP_BUCKET=test-bucket) çıkış 0" 'BACKUP_BUCKET=test-bucket run "$DEPLOY/backup.sh"'
check "s3://test-bucket/backups/ altına yüklendi" '[[ -f "$FAKE_S3_DIR/test-bucket/backups/$(basename "$F")" ]]'
check "yükleme sonrası head-object ile boyut doğrulandı" 'grep -q "^s3api head-object --bucket test-bucket --key backups/newsradar-" "$FAKE_AWS_LOG"'

echo "== 3) DB'yi değiştir → restore (dry-run, en son yedek)"
sql "CREATE TABLE _restore_probe(x); INSERT INTO _restore_probe VALUES (1);
     DELETE FROM articles WHERE id IN (SELECT id FROM articles ORDER BY id LIMIT 10);"
MUT="$(counts)"
check "DB gerçekten değişti" '[[ "$MUT" != "$BEFORE" ]]'
check "restore.sh --dry-run --yes çıkış 0" 'run "$DEPLOY/restore.sh" --dry-run "$T/local" --yes'
AFTER="$(counts)"
check "TÜM tabloların satır sayıları yedekle aynı" '[[ "$AFTER" == "$BEFORE" ]]'
[[ "$AFTER" == "$BEFORE" ]] || { echo "    önce:  $BEFORE"; echo "    sonra: $AFTER"; }
check "restore öncesi kopya alındı ve değişmiş hali taşıyor" \
  '[[ "$(sqlite3 "$(find "$SAFETY_DIR" -name "pre-restore-*.db" | sort | tail -n 1)" "SELECT count(*) FROM _restore_probe")" == 1 ]]'
check "backend healthy" healthy

echo "== 4) restore (S3 modu, sahte aws, dosya adıyla)"
sql "CREATE TABLE _restore_probe(x);"
check "restore.sh <ad> --yes çıkış 0" 'BACKUP_BUCKET=test-bucket run "$DEPLOY/restore.sh" --yes "$(basename "$F")"'
check "satır sayıları yedekle aynı" '[[ "$(counts)" == "$BEFORE" ]]'

echo "== 5) bozuk yedek reddedilir, DB'ye dokunulmaz"
head -c 40000 /dev/urandom | gzip >"$T/local/backups/newsradar-20000101-0000.db.gz"
sql "CREATE TABLE _restore_probe(x);"
STATE="$(counts)"
check "çıkış kodu ≠ 0" '! run "$DEPLOY/restore.sh" --dry-run "$T/local" --yes newsradar-20000101-0000.db.gz'
check "log: bütünlük kontrolü" 'grep -q "bütünlük kontrolünden geçmedi" "$T/last.log"'
check "DB değişmedi (probe tablosu duruyor)" '[[ "$(counts)" == "$STATE" ]]'
check "backend healthy" healthy

echo "== 6) /health başarısız → eski DB geri konur"
check "çıkış kodu ≠ 0 (Caddy kontrolü bilerek yanlış host'a)" '! DOMAIN=yok.localhost run "$DEPLOY/restore.sh" --dry-run "$T/local" --yes "$(basename "$F")"'
check "log: eski DB geri kondu" 'grep -q "servis eski DB ile ayakta" "$T/last.log"'
check "DB restore öncesi haliyle (probe tablosu duruyor)" '[[ "$(counts)" == "$STATE" ]]'
check "backend healthy" healthy

echo "== 7) diğer hata yolları"
check "backup: BACKUP_BUCKET yok → ≠ 0" '! BACKUP_BUCKET= run env -u BACKUP_BUCKET "$DEPLOY/backup.sh"'
check "backup: DB yok → ≠ 0" '! DB_IN_CONTAINER=/data/yok.db run "$DEPLOY/backup.sh" --dry-run "$T/local"'
check "restore: geçersiz ad → ≠ 0" '! run "$DEPLOY/restore.sh" --dry-run "$T/local" --yes "../../etc/passwd"'
check "restore: --yes olmadan etkileşimsiz → ≠ 0" '! run "$DEPLOY/restore.sh" --dry-run "$T/local" </dev/null'
check "restore: olmayan yedek → ≠ 0, servis ayakta" '! run "$DEPLOY/restore.sh" --dry-run "$T/local" --yes newsradar-19990101-0000.db.gz && healthy'

echo "== temizlik: başlangıç içeriğine dön"
run "$DEPLOY/restore.sh" --dry-run "$T/local" --yes "$(basename "$F")"
check "son durum = başlangıç" '[[ "$(counts)" == "$BEFORE" ]]'

echo "== $([[ $FAILS -eq 0 ]] && echo "TAMAM" || echo "$FAILS HATA")"
exit $((FAILS > 0))
