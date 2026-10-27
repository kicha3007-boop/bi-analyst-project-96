#!/bin/sh
# Перезаливает данные в работающий контейнер db: маркетинговая база из дампа
# и витрины дашборда (схема dashboard из dashboard.sql). make load
set -eu

PSQL="psql -X -q -v ON_ERROR_STOP=1 -U $POSTGRES_USER -d $POSTGRES_DB"

$PSQL -c "DROP SCHEMA IF EXISTS dashboard CASCADE;"
$PSQL -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
gunzip -c /docker-entrypoint-initdb.d/10_marketingdb.sql.gz | $PSQL
$PSQL -f /project/dashboard.sql -o /dev/null
$PSQL -c "SELECT 'sessions' AS table_name, COUNT(*) FROM public.sessions
          UNION ALL SELECT 'leads', COUNT(*) FROM public.leads
          UNION ALL SELECT 'vk_ads', COUNT(*) FROM public.vk_ads
          UNION ALL SELECT 'ya_ads', COUNT(*) FROM public.ya_ads;"
