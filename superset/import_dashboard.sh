#!/bin/sh
# Импорт дашборда из /app/export/dashboard.zip и настройка подключения marketingdb.
# В выгрузке пароль базы замаскирован (XXXXXXXXXX), а импорт без пароля
# не проходит проверку, поэтому перед импортом пароль подставляется
# во временную копию архива из переменных окружения.
set -eu

DASHBOARD_ZIP=/app/export/dashboard.zip
PREPARED_ZIP=/tmp/dashboard_import.zip
DATABASE_URI="postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}"

if [ -f "$DASHBOARD_ZIP" ]; then
    python - "$DASHBOARD_ZIP" "$PREPARED_ZIP" <<'PY'
import os
import sys
import zipfile

source, target = sys.argv[1], sys.argv[2]
mask = "XXXXXXXXXX"
with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, "w") as dst:
    for item in src.infolist():
        data = src.read(item.filename)
        if "/databases/" in item.filename:
            data = data.replace(
                mask.encode(), os.environ["POSTGRES_PASSWORD"].encode()
            )
        dst.writestr(item, data)
PY
    superset import-dashboards -p "$PREPARED_ZIP" -u "$SUPERSET_ADMIN_USER"
    rm -f "$PREPARED_ZIP"
fi
superset set-database-uri --database_name marketingdb --uri "$DATABASE_URI"
