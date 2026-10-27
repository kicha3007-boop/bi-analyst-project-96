#!/bin/sh
# Первичная настройка Superset при старте контейнера и запуск веб-сервера.
set -eu

superset db upgrade
superset fab create-admin \
    --username "$SUPERSET_ADMIN_USER" \
    --password "$SUPERSET_ADMIN_PASSWORD" \
    --firstname Admin --lastname Local \
    --email admin@localhost.local || true
superset init

# Дашборд из выгрузки и подключение к маркетинговой базе «marketingdb».
/app/import_dashboard.sh

exec gunicorn \
    --bind 0.0.0.0:8088 \
    --workers 2 \
    --timeout 120 \
    --limit-request-line 0 \
    --limit-request-field_size 0 \
    "superset.app:create_app()"
