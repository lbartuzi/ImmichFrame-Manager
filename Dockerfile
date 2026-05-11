FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8099 \
    FLASK_PORT=8099 \
    SETTINGS_FILE=/config/Settings.json \
    STATE_FILE=/data/sidecar-state.json

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /config /data \
    && chown -R app:app /app /config /data

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown -R app:app /app

# Runs as root by default so host-mounted config folders created by Portainer/root remain writable.
# Put the service behind a trusted LAN/VPN and set ADMIN_PASSWORD.
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/healthz', timeout=3).read()"

ENTRYPOINT ["/entrypoint.sh"]
