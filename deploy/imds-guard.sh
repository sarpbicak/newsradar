#!/usr/bin/env bash
# Caddy container'ının IMDS'e (169.254.169.254, instance rolü) ulaşmasını engeller. SES için hop
# limiti 2'dir: backend rol kimliğini IMDS'ten alır; internete açık Caddy alamaz.
#
#   deploy/imds-guard.sh install   systemd birimini kurar ve kuralı ekler (deploy.sh, user-data)
#   deploy/imds-guard.sh apply     yalnızca kuralı ekler (systemd birimi, açılışta)
#   deploy/imds-guard.sh check     kural yoksa çıkış 1
#
# Hepsi idempotent. Kural DOCKER-USER zincirinde: container trafiği FORWARD'dan geçer, kaynak IP
# henüz NAT'lanmamıştır. Birim Docker'dan ÖNCE çalışır (zinciri yoksa kendi açar; Docker var olan
# DOCKER-USER'ı silmez), böylece açılışta Caddy korumasız kalmaz. Caddy'nin IP'si tek yerden:
# docker-compose.yml (x-caddy-ip). compose ağı yalnızca IPv4; IMDS'in IPv6 adresine yol yok.
set -Eeuo pipefail
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_TAG=imds-guard
# shellcheck source=deploy/lib.sh
. "$DEPLOY_DIR/lib.sh"

IMDS=169.254.169.254
CHAIN=DOCKER-USER
UNIT=newsradar-imds-guard.service
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"

CADDY_IP="$(sed -n 's/^x-caddy-ip: &caddy_ip //p' "$DEPLOY_DIR/docker-compose.yml")"
[[ "$CADDY_IP" =~ ^[0-9]+(\.[0-9]+){3}$ ]] || die "Caddy IP'si docker-compose.yml'den okunamadı: '$CADDY_IP'"
RULE=(-s "$CADDY_IP" -d "$IMDS" -j DROP)

ipt() { iptables -w 10 "$@"; }
present() { ipt -C "$CHAIN" "${RULE[@]}" 2>/dev/null; }

apply() {
  need iptables
  ipt -N "$CHAIN" 2>/dev/null || true   # varsa hata verir; Docker yoksa/başlamadıysa zinciri açar
  if present; then
    log "kural zaten var: $CADDY_IP → $IMDS DROP"
  else
    ipt -I "$CHAIN" 1 "${RULE[@]}"
    log "kural eklendi: $CADDY_IP → $IMDS DROP"
  fi
  present || die "kural eklendikten sonra bulunamadı"
}

install_unit() {
  if ! command -v systemctl >/dev/null 2>&1; then
    log "systemctl yok: birim kurulmadı (yeniden başlatmada kural kaybolur)"
    return 0
  fi
  if ! cmp -s "$DEPLOY_DIR/systemd/$UNIT" "$SYSTEMD_DIR/$UNIT"; then
    install -m 644 "$DEPLOY_DIR/systemd/$UNIT" "$SYSTEMD_DIR/$UNIT"
    systemctl daemon-reload
    log "systemd birimi kuruldu: $UNIT"
  fi
  systemctl enable --quiet "$UNIT"
}

case "${1:-}" in
  apply) apply ;;
  install) install_unit; apply ;;
  check)
    need iptables
    if present; then log "kural var: $CADDY_IP → $IMDS DROP"; else log "KURAL YOK: $CADDY_IP → $IMDS"; exit 1; fi
    ;;
  *) die "kullanım: imds-guard.sh install|apply|check" ;;
esac
