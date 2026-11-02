#!/usr/bin/env bash
# imds-guard.sh testi — sahte iptables/systemctl ile, gerçek güvenlik duvarına dokunmadan.
# Doğrular: kural doğru (Caddy IP'si compose'dan, yalnızca IMDS, DROP) ve en üstte; idempotent;
# başka kurallar korunur; check; install birimi kurar, ikinci kez daemon-reload yapmaz; iptables
# yoksa/kural eklenemezse hata; backend IP'si engellenmez; deploy.sh kuralı servisten önce kurar.
# `koşul && ok || bad`: ok() her zaman 0 döner, bu yüzden if-then-else ile eşdeğer.
# shellcheck disable=SC2015
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="$(dirname "$HERE")"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
FAILS=0
ok() { echo "  ✓ $1"; }
bad() { echo "  ✗ $1"; FAILS=$((FAILS + 1)); }

mkdir -p "$T/bin" "$T/units"
cat >"$T/bin/iptables" <<'FAKE'
#!/usr/bin/env bash
# Sahte iptables: kurallar $FAKE_RULES dosyasında, her satır "<zincir> <kural>".
[[ "$1" == -w ]] && shift 2
op="$1"; chain="$2"; shift 2
[[ -n "${FAKE_IPT_FAIL:-}" && "$op" == -I ]] && exit 4
case "$op" in
  -N) grep -q "^:$chain$" "$FAKE_RULES" && exit 1; echo ":$chain" >>"$FAKE_RULES" ;;
  -C) grep -qxF "$chain $*" "$FAKE_RULES" ;;
  -I) shift; { echo "$chain $*"; cat "$FAKE_RULES"; } >"$FAKE_RULES.new"; mv "$FAKE_RULES.new" "$FAKE_RULES" ;;
  *) exit 2 ;;
esac
FAKE
cat >"$T/bin/systemctl" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >>"$FAKE_SYSTEMCTL_LOG"
FAKE
chmod +x "$T/bin/iptables" "$T/bin/systemctl"
export PATH="$T/bin:$PATH" FAKE_RULES="$T/rules" FAKE_SYSTEMCTL_LOG="$T/systemctl.log" SYSTEMD_DIR="$T/units"
: >"$FAKE_RULES"
: >"$FAKE_SYSTEMCTL_LOG"
G="$DEPLOY/imds-guard.sh"

CADDY_IP="$(sed -n 's/^x-caddy-ip: &caddy_ip //p' "$DEPLOY/docker-compose.yml")"
WANT="DOCKER-USER -s $CADDY_IP -d 169.254.169.254 -j DROP"

echo "== compose"
[[ "$CADDY_IP" == 172.28.0.10 ]] && ok "Caddy'nin sabit IP'si: $CADDY_IP" || bad "Caddy IP'si beklenmedik: $CADDY_IP"
grep -q 'ipv4_address: \*caddy_ip' "$DEPLOY/docker-compose.yml" && ok "caddy servisi bu IP'ye bağlı" || bad "caddy servisi sabit IP kullanmıyor"
grep -q "NEWSRADAR_CADDY_IP=$CADDY_IP" "$DEPLOY/../backend/Dockerfile" && ok "Dockerfile aynı IP'yi kullanıyor" || bad "Dockerfile'daki Caddy IP'si farklı"
backend_ip="$(sed -n 's/^ *ipv4_address: \(172[0-9.]*\)$/\1/p' "$DEPLOY/docker-compose.yml")"
[[ -n "$backend_ip" && "$backend_ip" != "$CADDY_IP" ]] && ok "backend IP'si ($backend_ip) kuralın dışında" || bad "backend IP'si kuralın kapsamında"

echo "== apply"
"$G" check 2>/dev/null && bad "kural yokken check 0 döndü" || ok "kural yokken check 1"
echo "DOCKER-USER -j RETURN" >"$FAKE_RULES"
"$G" apply 2>/dev/null && ok "apply çalıştı" || bad "apply hata verdi"
[[ "$(grep -v '^:' "$FAKE_RULES" | head -1)" == "$WANT" ]] && ok "kural doğru ve en üstte" || bad "kural yanlış: $(cat "$FAKE_RULES")"
grep -q "RETURN" "$FAKE_RULES" && ok "mevcut kurallar korunur" || bad "mevcut kural silindi"
"$G" apply 2>/dev/null
"$G" apply 2>/dev/null
[[ "$(grep -cxF "$WANT" "$FAKE_RULES")" == 1 ]] && ok "idempotent: kural tek" || bad "kural çoğaldı"
"$G" check 2>/dev/null && ok "kural varken check 0" || bad "kural varken check 1"
grep -qE "172\.28\.0\.20|0\.0\.0\.0" "$FAKE_RULES" && bad "backend de engellendi" || ok "yalnızca Caddy engellenir"

echo "== hatalar"
: >"$FAKE_RULES"
FAKE_IPT_FAIL=1 "$G" apply 2>/dev/null && bad "kural eklenemedi ama 0 döndü" || ok "kural eklenemezse hata"
"$G" 2>/dev/null && bad "argümansız 0 döndü" || ok "argümansız kullanım hata"

echo "== install"
: >"$FAKE_RULES"
"$G" install 2>/dev/null && ok "install çalıştı" || bad "install hata verdi"
cmp -s "$DEPLOY/systemd/newsradar-imds-guard.service" "$T/units/newsradar-imds-guard.service" && ok "birim kuruldu" || bad "birim kurulmadı"
grep -q "daemon-reload" "$FAKE_SYSTEMCTL_LOG" && grep -q "enable --quiet newsradar-imds-guard.service" "$FAKE_SYSTEMCTL_LOG" && ok "daemon-reload + enable" || bad "systemctl çağrıları eksik: $(cat "$FAKE_SYSTEMCTL_LOG")"
grep -qxF "$WANT" "$FAKE_RULES" && ok "install kuralı da ekler" || bad "install kuralı eklemedi"
: >"$FAKE_SYSTEMCTL_LOG"
"$G" install 2>/dev/null
grep -q "daemon-reload" "$FAKE_SYSTEMCTL_LOG" && bad "değişiklik yokken daemon-reload" || ok "ikinci install'da daemon-reload yok"

echo "== birim ve deploy.sh"
U="$DEPLOY/systemd/newsradar-imds-guard.service"
grep -qx "Before=docker.service" "$U" && grep -qx "WantedBy=docker.service" "$U" && ok "birim Docker'dan önce, Docker'la birlikte" || bad "birim sırası yanlış"
grep -qx "ExecStart=/opt/newsradar/deploy/imds-guard.sh apply" "$U" && ok "birim apply çağırır" || bad "birim ExecStart yanlış"
[[ -x "$G" ]] && ok "betik çalıştırılabilir" || bad "betik çalıştırılabilir değil"
guard_line="$(grep -n 'imds-guard.sh" install' "$DEPLOY/deploy.sh" | cut -d: -f1)"
up_line="$(grep -n '^dc up -d --no-build' "$DEPLOY/deploy.sh" | head -1 | cut -d: -f1)"
[[ -n "$guard_line" && -n "$up_line" && "$guard_line" -lt "$up_line" ]] && ok "deploy.sh kuralı servisten önce kurar" || bad "deploy.sh sırası yanlış"
grep -q 'imds-guard.sh install' "$DEPLOY/aws/user-data.sh" && ok "user-data birimi kurar" || bad "user-data birimi kurmuyor"

echo "$FAILS hata"
exit $((FAILS > 0))
