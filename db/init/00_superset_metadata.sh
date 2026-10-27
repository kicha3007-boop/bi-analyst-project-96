#!/bin/sh
# Отдельная база для служебных данных Superset (пользователи, графики, дашборды).
set -eu

psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "CREATE DATABASE superset;"
