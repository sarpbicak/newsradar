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
expect() { [[ "$2" == "$3" ]] && ok "$1 ($2)" || bad "$1: beklenen $3, gelen $2"; }

echo "== $HOST"
expect "/health" "$("${CURL[@]}" -o /dev/null -w '%{http_code}' "https://$HOST/health")" 200

HDRS="$("${CURL[@]}" -o /dev/null -D - "https://$HOST/health" | tr -d '\r' | tr 'A-Z' 'a-z')"
for h in "strict-transport-security: max-age=31536000" "x-content-type-options: nosniff" "referrer-policy: no-referrer"; do
  grep -q "^$h" <<<"$HDRS" && ok "başlık: $h" || bad "başlık eksik: $h"
done
grep -qE "^(server|via):" <<<"$HDRS" && bad "Server/Via başlığı sızıyor" || ok "Server/Via başlığı yok"

expect "http → https" "$("${CURL[@]}" -o /dev/null -w '%{http_code}' "http://$HOST/health")" 308

BIG="$(mktemp)"; head -c 2000000 /dev/zero | tr '\0' a >"$BIG"
expect "2MB gövde reddi" "$("${CURL[@]}" -o /dev/null -w '%{http_code}' -X POST \
  -H 'Content-Type: application/json' --data-binary @"$BIG" "https://$HOST/feedback")" 413
rm -f "$BIG"

if [[ "$HOST" == *localhost ]]; then
  code="$(curl -s --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)"
  [[ "$code" == "000" ]] && ok "backend portu dışarıya kapalı" || bad "backend 8000 dışarıdan erişilebilir ($code)"
fi

if [[ "$IP_TEST" == "--ip-test" ]]; then
  user="smoke_$RANDOM"; codes=""
  for i in 1 2 3 4 5 6; do
    codes+=" $("${CURL[@]}" -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
      -H "X-Forwarded-For: 6.6.6.$i" -d "{\"username\":\"$user\",\"password\":\"x\"}" "https://$HOST/users/login")"
  done
  [[ "$codes" == *429 ]] && ok "sahte XFF'e rağmen IP kilidi (kodlar:$codes)" || bad "IP kilidi yok (kodlar:$codes)"
  if command -v docker >/dev/null && docker compose ps -q backend >/dev/null 2>&1; then
    docker compose logs backend 2>/dev/null | grep -q "6\.6\.6\." && bad "sahte adres backend'e ulaştı" \
      || ok "backend sahte adresi hiç görmedi"
  fi
fi

echo "== $([[ $FAILS -eq 0 ]] && echo "TAMAM" || echo "$FAILS HATA")"
exit $((FAILS > 0))
