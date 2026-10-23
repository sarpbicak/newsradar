# syntax=docker/dockerfile:1
# NewsRadar API — EC2 (ARM, t4g) için: docker buildx build --platform linux/arm64 .
# Python sürümü Render'daki ile aynı seri (Render varsayılanı: 3.14.x).
ARG PYTHON_VERSION=3.14

# ---------- 1) Bağımlılıklar: izole venv'e kurulur ----------
FROM python:${PYTHON_VERSION}-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
 && pip uninstall --yes pip

# ---------- 2) Çalışma image'ı: yalnızca venv + uygulama kodu ----------
FROM python:${PYTHON_VERSION}-slim
# NEWSRADAR_CADDY_IP: uvicorn'un X-Forwarded-For'una güvendiği TEK adres (Caddy container'ı;
# deploy/docker-compose.yml'deki sabit IP ile aynı olmalı).
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NEWSRADAR_DB=/data/newsradar.db \
    NEWSRADAR_TRUSTED_PROXY=caddy \
    NEWSRADAR_CADDY_IP=172.28.0.10

# sqlite3 CLI: deploy/backup.sh ve restore.sh canlı DB'yi container İÇİNDE `.backup` ile alır
# (çalışan WAL veritabanını dosya kopyalamak tutarsız yedek üretebilir).
# pip çalışma anında gerekmez ve içine gömülü eski kütüphaneler (urllib3, msgpack, setuptools)
# taramada HIGH bulgu üretir → hem sistem pip'i hem venv pip'i (builder'da) kaldırılır.
RUN apt-get update \
 && apt-get install -y --no-install-recommends sqlite3 \
 && rm -rf /var/lib/apt/lists/* \
 && python -m pip uninstall --yes pip

# Root olmayan kullanıcı. /data bu kullanıcıya ait → yeni named volume bu sahipliği devralır.
RUN groupadd --system --gid 10001 newsradar \
 && useradd --system --uid 10001 --gid newsradar --no-create-home --shell /usr/sbin/nologin newsradar \
 && mkdir /data && chown newsradar:newsradar /data

COPY --from=builder /opt/venv /opt/venv
WORKDIR /srv
# Kod root'a ait kalır (uygulama kullanıcısı kendi kodunu değiştiremez).
COPY app ./app

USER newsradar
EXPOSE 8000

# slim'de curl yok → Python ile /health.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --start-interval=2s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# --workers 1: APScheduler ve SQLite tek süreç ister (birden fazla worker = çift zamanlayıcı).
# --proxy-headers + --forwarded-allow-ips: X-Forwarded-For YALNIZCA Caddy'den kabul edilir.
# exec → uvicorn PID 1 olur, SIGTERM'i doğrudan alır (zarif kapanış: scheduler.shutdown).
CMD ["sh", "-c", "exec uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 1 --no-server-header --proxy-headers --forwarded-allow-ips=\"$NEWSRADAR_CADDY_IP\""]
