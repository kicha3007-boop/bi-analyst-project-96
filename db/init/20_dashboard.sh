#!/bin/sh
# Создаёт витрины дашборда (схема dashboard) запросами из dashboard.sql.
# Запускается после загрузки дампа marketingdb (10_marketingdb.sql.gz).
# Аналитические SELECT-запросы из того же файла выполняются вхолостую.
set -eu

psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -f /project/dashboard.sql -o /dev/null
