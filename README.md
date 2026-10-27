# Онлайн-школа

[![hexlet-check](https://github.com/kicha3007-boop/bi-analyst-project-96/actions/workflows/hexlet-check.yml/badge.svg)](https://github.com/kicha3007-boop/bi-analyst-project-96/actions)

Помогите маркетологам онлайн-школы создать систему сквозной аналитики

Учебный проект Хекслета: https://ru.hexlet.io/programs/bi-analyst
Как это должно работать: запросы строят витрину атрибуции Last Paid Click по визитам
и лидам онлайн-школы за июнь 2023, сводят с ней расходы на рекламу VK и Яндекса,
результаты выгружаются в csv, по витринам собран дашборд в Superset, а выводы
оформлены в презентацию `presentation.pdf`.

## Стек

- PostgreSQL 17 — маркетинговая база `marketingdb` (дамп в `db/init/10_marketingdb.sql.gz`)
- SQL (линтер SQLFluff, диалект postgres)
- Apache Superset 4.1 — дашборд
- Docker Compose, Make
- Playwright (Chromium) — скриншоты графиков и сборка PDF

## Что в репозитории

| Файл | Что это |
|------|---------|
| `last_paid_click.sql`, `last_paid_click.csv` | шаг 3: витрина атрибуции Last Paid Click, в csv — топ-10 строк |
| `aggregate_last_paid_click.sql`, `aggregate_last_paid_click.csv` | шаг 4: визиты, лиды, покупки, выручка и расходы по дню и меткам, в csv — топ-15 строк |
| `dashboard.sql` | шаги 5–6: витрины дашборда (схема `dashboard`) и все расчёты для презентации |
| `superset/export/dashboard.zip` | выгрузка дашборда Superset (шаг 5) |
| `presentation.pdf` | презентация с выводами (шаг 6), исходник — `presentation/slides.html` |
| `db/init/` | инициализация PostgreSQL: база Superset, дамп `marketingdb`, витрины дашборда |
| `scripts/` | выгрузка csv, перезаливка базы, сборка дашборда, скриншоты, PDF |

Данные: дамп учебной базы `marketingdb` (таблицы sessions, leads, vk_ads, ya_ads),
снятый с публичного доступа из шага 2 (`db.hexlet.app`, student/student). Всё лежит
в репозитории — сеть и внешние доступы для работы не нужны.

## Установка

Нужны Docker с Compose и GNU Make.

```bash
git clone https://github.com/kicha3007-boop/bi-analyst-project-96.git
cd bi-analyst-project-96
cp .env.example .env   # необязательно: локальные пароли и порты по умолчанию
make up                # сборка без кэша и запуск PostgreSQL + Superset
```

При первом старте PostgreSQL загружает дамп и создаёт витрины из `dashboard.sql`,
а Superset импортирует дашборд из `superset/export/dashboard.zip`.

- Дашборд: http://localhost:8089/superset/dashboard/online-school/ (логин `admin`, пароль `admin`)
- PostgreSQL: `localhost:15433`, база `marketingdb`, пользователь/пароль `postgres`/`postgres`

Порты меняются в `.env` (`POSTGRES_PORT`, `SUPERSET_PORT`).

## Использование

```bash
make reports          # выполнить запросы шагов 3–4 и перезаписать csv
make lint             # SQLFluff для всех .sql (образ автопроверки Хекслета)
make test             # тесты автопроверки Хекслета локально
make psql             # консоль базы
make load             # перезалить дамп и витрины в работающую базу
make dashboard        # повторно импортировать дашборд из zip
make dashboard-build  # собрать дашборд заново через REST API и выгрузить в zip
make screenshots      # скриншоты графиков в presentation/img/
make presentation     # собрать presentation.pdf из presentation/slides.html
make down             # остановить контейнеры (make reset — с удалением данных)
```

Полный цикл с нуля: `make reset reports dashboard-build screenshots presentation test`.

Дашборд отвечает на вопросы шага 5: посетители по дням / неделям / месяцам и источникам,
лиды, конверсия клик → лид → оплата, расходы в динамике, окупаемость каналов, сводные
таблицы с cpu, cpl, cppu и roi по utm_source и по source / medium / campaign.
Фильтры: период, utm_source, utm_medium, utm_campaign, шаг времени.

### Ключевые выводы

- Июнь 2023: 169 140 посетителей, 22,8% — по платной рекламе; расходы 6,43 млн руб. (Яндекс 88%).
- По модели Last Paid Click окупаются оба канала: Яндекс ROI +46,5%, VK +37,6%.
- 2,2 млн руб. Яндекса за 2–12 июня не связаны ни с одним визитом (визитов yandex в эти дни нет);
  с учётом этих трат ROI Яндекса −10,3% — нужно проверить UTM-разметку.
- Лучшие кампании: yandex / freemium (+423%, 25 покупок), base-python, base-frontend, vk / freemium-frontend.
- Дорогие профессии Яндекса (frontend, python, java) тратят 2,6 млн и в минусе; в VK 3 кампании
  без покупок на ~277 тыс. руб.
- 90% лидов появляются в течение 25 дней после последнего платного клика (медиана — 14 дней).
- Связь расходов и органики слабая (корреляция 0,29), органика зависит от дня недели.

---

<details>
<summary>Автоматические тесты Хекслета</summary>

Тесты запускаются на каждый коммит. За запуск отвечает файл `.github/workflows/hexlet-check.yml` — не удаляйте и не переименовывайте ни его, ни репозиторий.

</details>

## О Хекслете

[Хекслет](https://ru.hexlet.io/) — школа программирования: авторские программы обучения с практикой, поддержкой наставников и реальными проектами, которые остаются в резюме. Этот репозиторий — один из таких проектов.
