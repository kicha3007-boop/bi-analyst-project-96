# Локальный стенд проекта «Онлайн-школа»: PostgreSQL с маркетинговой базой,
# Superset с дашбордом и инструменты для выгрузок, скриншотов и презентации.

COMPOSE = docker compose
CHECK_IMAGE = hexletprojects/data_analytics_l2_project_ru:latest
SUPERSET_PORT ?= 8089

.PHONY: up build down reset load reports psql dashboard \
	dashboard-build dashboard-export screenshots presentation lint test

build:
	$(COMPOSE) build --no-cache superset

up: build
	$(COMPOSE) up -d --wait db superset
	@echo "Дашборд: http://localhost:$(SUPERSET_PORT)/superset/dashboard/online-school/ (admin / admin)"

down:
	$(COMPOSE) --profile tools down

# Полный сброс: удалить тома и поднять стенд с нуля.
reset:
	$(COMPOSE) --profile tools down -v
	$(MAKE) up

# Перезалить данные в работающую базу (дамп marketingdb и витрины дашборда).
load:
	$(COMPOSE) exec -T db sh /project/scripts/reload_db.sh

# Пересчитать csv-выгрузки запросами last_paid_click.sql
# и aggregate_last_paid_click.sql.
reports:
	$(COMPOSE) exec -T db sh /project/scripts/export_reports.sh

psql:
	$(COMPOSE) exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

# Импортировать готовый дашборд из superset/export/dashboard.zip
# (при старте контейнера superset это происходит автоматически).
dashboard:
	$(COMPOSE) exec -T superset /app/import_dashboard.sh
	@echo "Дашборд: http://localhost:$(SUPERSET_PORT)/superset/dashboard/online-school/"

# Собрать дашборд заново через REST API Superset и выгрузить его в zip.
dashboard-build:
	$(COMPOSE) --profile tools build --no-cache tools
	$(COMPOSE) --profile tools run --rm tools python scripts/build_dashboard.py
	$(MAKE) dashboard-export

dashboard-export:
	$(COMPOSE) exec -T superset superset export-dashboards \
		-f /app/export/dashboard.zip

# Скриншоты дашборда и графиков для презентации (presentation/img/).
screenshots:
	$(COMPOSE) --profile tools run --rm tools python scripts/screenshots.py

# Собрать presentation.pdf из presentation/slides.html.
presentation:
	$(COMPOSE) --profile tools run --rm tools python scripts/render_pdf.py

# Линтер SQL автопроверки Хекслета: все .sql файлы репозитория.
lint:
	docker run --rm -v "$(CURDIR):/project/code" --entrypoint sh $(CHECK_IMAGE) \
		-c "python3 -m sqlfluff lint /project/code/"

# Автопроверка Хекслета локально: сверка csv и наличие файлов.
test:
	docker run --rm -v "$(CURDIR):/project/code" --entrypoint sh $(CHECK_IMAGE) \
		-c "make setup >/dev/null 2>&1; make test"
