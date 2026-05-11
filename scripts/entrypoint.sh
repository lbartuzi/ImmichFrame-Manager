#!/bin/sh
set -eu
WEB_PORT="${FLASK_PORT:-${PORT:-8099}}"
exec gunicorn --bind "0.0.0.0:${WEB_PORT}" --workers "${GUNICORN_WORKERS:-1}" --threads "${GUNICORN_THREADS:-4}" --timeout "${GUNICORN_TIMEOUT:-120}" "app.main:app"
