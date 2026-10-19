#!/bin/bash
# NewsRadar EC2 ilk açılış betiği (Amazon Linux 2023, arm64; root olarak bir kez çalışır).
# Çift alt çizgili yer tutucular deploy/aws/render.py ile doldurulur (docs/DEPLOY_AWS.md, adım 13).
# Log: /var/log/newsradar-user-data.log · Bitti işareti: /var/lib/newsradar/user-data.done
set -euo pipefail
exec > >(tee -a /var/log/newsradar-user-data.log) 2>&1

REGION="__REGION__"
REPO_URL="__REPO_URL__"
REPO_BRANCH="__REPO_BRANCH__"
LOG_GROUP="__LOG_GROUP__"
DEPLOY_KEY_PARAM="/newsradar/bootstrap/github-deploy-key"
APP_DIR=/opt/newsradar
DOCKER_MIN_MAJOR=25
# Resmi statik Docker paketi — yalnızca dnf'teki sürüm < 25 ise (AL2023'te şu an 25.0.x).
DOCKER_STATIC_VERSION=29.9.1
# Eklentiler: GitHub release'leri, sha256 sabit (sürüm değişirse ikisi birlikte güncellenir).
COMPOSE_VERSION=v5.6.0
COMPOSE_SHA256=733ec76717ceb59052a9609b9dadfb523b2df8eab57a54212872d10a58078ea2
BUILDX_VERSION=v0.38.0
BUILDX_SHA256=38e890e1a162bfdbf32fbe91404991dc4fc28e55b0de901b34374a061bab4d2c
# GitHub'ın yayımlanmış SSH host anahtarı (docs.github.com → "GitHub's SSH key fingerprints").
GITHUB_HOST_KEY="github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"

log() { echo "[user-data] $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
trap 'log "HATA: satır $LINENO (kod $?) — ayrıntı yukarıda"' ERR

# 0) Dış bağlantı: instance genel IP'siz açılır, Elastic IP birkaç saniye sonra bağlanır.
for i in $(seq 1 120); do
  if curl -fsS -m 5 -o /dev/null https://github.com; then break; fi
  log "internet bekleniyor ($i/120)"
  sleep 5
done

# 1) Paketler (awscli-2, curl ve python3 AL2023 AMI'sinde hazır; yoksa kurulur).
dnf -y install docker git sqlite gzip tar python3
command -v aws >/dev/null || dnf -y install awscli-2
systemctl enable --now docker

install_docker_static() {
  log "Docker $1 < $DOCKER_MIN_MAJOR → resmi statik paket $DOCKER_STATIC_VERSION (download.docker.com)"
  systemctl disable --now docker.socket docker || true
  dnf -y remove docker
  dnf -y install iptables-nft
  curl -fsSL "https://download.docker.com/linux/static/stable/aarch64/docker-${DOCKER_STATIC_VERSION}.tgz" -o /tmp/docker.tgz
  tar -xzf /tmp/docker.tgz -C /usr/local/bin --strip-components=1
  groupadd -f docker
  cat >/etc/systemd/system/docker.service <<'UNIT'
[Unit]
Description=Docker Engine (statik paket)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/dockerd
Restart=always
Delegate=yes
KillMode=process
LimitNOFILE=infinity

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable --now docker
}

major="$(docker version --format '{{.Server.Version}}' | cut -d. -f1)"
if ((major < DOCKER_MIN_MAJOR)); then
  install_docker_static "$major"
  major="$(docker version --format '{{.Server.Version}}' | cut -d. -f1)"
  ((major >= DOCKER_MIN_MAJOR)) || { log "HATA: Docker $DOCKER_MIN_MAJOR+ kurulamadı"; exit 1; }
fi
log "docker sunucu sürümü: $(docker version --format '{{.Server.Version}}')"

# 2) compose + buildx eklentileri (sha256 tutmazsa kurulum durur).
plugins=/usr/local/lib/docker/cli-plugins
install -d "$plugins"
fetch_plugin() { # url sha256 hedef — çağrı bağlamından (set -e) bağımsız: tutmazsa kurmaz
  curl -fsSL "$1" -o "$3.tmp" || return 1
  if ! echo "$2  $3.tmp" | sha256sum -c -; then
    rm -f "$3.tmp"
    log "HATA: sha256 tutmadı: $1"
    return 1
  fi
  install -m 755 "$3.tmp" "$3" && rm -f "$3.tmp"
}
fetch_plugin "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-aarch64" \
  "$COMPOSE_SHA256" "$plugins/docker-compose"
fetch_plugin "https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/buildx-${BUILDX_VERSION}.linux-arm64" \
  "$BUILDX_SHA256" "$plugins/docker-buildx"
log "$(docker compose version) · $(docker buildx version)"

# 3) Container log'ları → CloudWatch Logs (awslogs; kimlik: instance rolü, IMDSv2 host'tan).
# Log grubu runbook'ta önceden 7 gün saklamayla oluşturulur. non-blocking: CloudWatch'a
# ulaşılamazsa uygulama yavaşlamaz, tampon dolarsa en eski satırlar düşer.
install -d /etc/docker
cat >/etc/docker/daemon.json <<JSON
{
  "log-driver": "awslogs",
  "log-opts": {
    "awslogs-region": "${REGION}",
    "awslogs-group": "${LOG_GROUP}",
    "tag": "{{.Name}}",
    "mode": "non-blocking",
    "max-buffer-size": "4m"
  }
}
JSON
systemctl restart docker

# 4) Repo → /opt/newsradar (private repo: SSM'deki salt okunur deploy key ile SSH).
if [[ "$REPO_URL" == git@* ]]; then
  install -d -m 700 /root/.ssh
  aws ssm get-parameter --region "$REGION" --name "$DEPLOY_KEY_PARAM" --with-decryption \
    --query Parameter.Value --output text >/root/.ssh/newsradar_deploy_key
  chmod 600 /root/.ssh/newsradar_deploy_key
  grep -qxF "$GITHUB_HOST_KEY" /root/.ssh/known_hosts 2>/dev/null || echo "$GITHUB_HOST_KEY" >>/root/.ssh/known_hosts
  cat >/root/.ssh/config <<'SSH'
Host github.com
  IdentityFile /root/.ssh/newsradar_deploy_key
  IdentitiesOnly yes
  StrictHostKeyChecking yes
SSH
  chmod 600 /root/.ssh/config
fi
if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone --branch "$REPO_BRANCH" "$REPO_URL" "$APP_DIR"
fi
log "repo: $(git -C "$APP_DIR" log -1 --format='%h %s')"

# 5) systemd: gece yedeği (deploy/.env, load-secrets.sh çalışınca oluşur; öncesinde
# tetiklenirse yalnızca log'a hata yazar).
install -m 644 "$APP_DIR"/deploy/systemd/newsradar-backup.service "$APP_DIR"/deploy/systemd/newsradar-backup.timer \
  /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now newsradar-backup.timer

install -d /var/lib/newsradar
date -u +%Y-%m-%dT%H:%M:%SZ >/var/lib/newsradar/user-data.done
log "tamam"
