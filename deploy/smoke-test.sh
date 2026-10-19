#!/usr/bin/env bash
# Caddy + backend duman testi. Kullanım (deploy/ içinden, stack ayaktayken):
#   ./smoke-test.sh                  # yerel: https://api.localhost (Caddy yerel CA → -k)
#   ./smoke-test.sh api.newsradarapp.com
#   ./smoke-test.sh api.localhost --ip-test
# --ip-test: sahte X-Forwarded-For ile 6 başarısız giriş → 429 ve kilit GERÇEK bağlantı
#            adresinde mi (backend log'unda sahte adres yok). Test eden IP'yi 15 dk giriş
#            için kilitler; canlıda dikkatli kullanın.
set -u
HOST="${1:-api.localhost}"
IP_TEST="${2:-}"
CURL=(curl -s --max-time 15)
if [[ "$HOST" == *localhost ]]; then
  CURL+=(-k --resolve "$HOST:443:127.0.0.1" --resolve "$HOST:80:127.0.0.1")
fi
FAILS=0
ok()   { echo "  ✓ $1"; }
bad()  { echo "  ✗ $1"; FAILS=$((FAILS + 1)); }
# report <önceki komutun kodu> <başarı mesajı> <hata mesajı>
report() { if (($1 == 0)); then ok "$2"; else bad "$3"; fi; }
expect() { if [[ "$2" == "$3" ]]; then ok "$1 ($2)"; else bad "$1: beklenen $3, gelen $2"; fi; }

echo "== $HOST"
expect "/health" "$("${CURL[@]}" -o /dev/null -w '%{http_code}' "https://$HOST/health")" 200

HDRS="$("${CURL[@]}" -o /dev/null -D - "https://$HOST/health" | tr -d '\r' | tr '[:upper:]' '[:lower:]')"
for h in "strict-transport-security: max-age=31536000" "x-content-type-options: nosniff" "referrer-policy: no-referrer"; do
  grep -q "^$h" <<<"$HDRS"; report $? "başlık: $h" "başlık eksik: $h"
done
! grep -qE "^(server|via):" <<<"$HDRS"; report $? "Server/Via başlığı yok" "Server/Via başlığı sızıyor"

expect "http → https" "$("${CURL[@]}" -o /dev/null -w '%{http_code}' "http://$HOST/health")" 308

BIG="$(mktemp)"; head -c 2000000 /dev/zero | tr '\0' a >"$BIG"
expect "2MB gövde reddi" "$("${CURL[@]}" -o /dev/null -w '%{http_code}' -X POST \
  -H 'Content-Type: application/json' --data-binary @"$BIG" "https://$HOST/feedback")" 413
rm -f "$BIG"

if [[ "$HOST" == *localhost ]]; then
  code="$(curl -s --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)"
  if [[ "$code" == "000" ]]; then ok "backend portu dışarıya kapalı"; else bad "backend 8000 dışarıdan erişilebilir ($code)"; fi
fi

if [[ "$IP_TEST" == "--ip-test" ]]; then
  user="smoke_$RANDOM"; codes=""
  for i in 1 2 3 4 5 6; do
    codes+=" $("${CURL[@]}" -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
      -H "X-Forwarded-For: 6.6.6.$i" -d "{\"username\":\"$user\",\"password\":\"x\"}" "https://$HOST/users/login")"
  done
  if [[ "$codes" == *429 ]]; then ok "sahte XFF'e rağmen IP kilidi (kodlar:$codes)"; else bad "IP kilidi yok (kodlar:$codes)"; fi
  if command -v docker >/dev/null && docker compose ps -q backend >/dev/null 2>&1; then
    ! docker compose logs backend 2>/dev/null | grep -q "6\.6\.6\."
    report $? "backend sahte adresi hiç görmedi" "sahte adres backend'e ulaştı"
  fi
fi

echo "== $([[ $FAILS -eq 0 ]] && echo "TAMAM" || echo "$FAILS HATA")"
exit $((FAILS > 0))
