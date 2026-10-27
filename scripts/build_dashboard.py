"""Собирает дашборд «Онлайн-школа» в локальном Superset через REST API.

Источник данных — витрины схемы dashboard (создаются запросами из
dashboard.sql). Повторный запуск пересоздаёт датасеты, графики и дашборд.
Запуск: make dashboard-build (контейнер tools).
"""

import io
import json
import os
import uuid
import zipfile

import requests

SUPERSET_URL = os.environ.get("SUPERSET_URL", "http://localhost:8089")
USERNAME = os.environ.get("SUPERSET_ADMIN_USER", "admin")
PASSWORD = os.environ.get("SUPERSET_ADMIN_PASSWORD", "admin")
DATABASE_NAME = "marketingdb"
SCHEMA = "dashboard"
DASHBOARD_SLUG = "online-school"
DASHBOARD_TITLE = "Онлайн-школа: сквозная аналитика рекламы"

# Датасеты: имя витрины -> основной столбец даты (по нему работает
# фильтр периода).
DATASETS = {
    "sessions": "visit_date",
    "last_paid_click": "visit_date",
    "aggregate_last_paid_click": "visit_date",
    "ads_costs": "campaign_date",
}


def sql_metric(expression, label):
    return {
        "expressionType": "SQL",
        "sqlExpression": expression,
        "label": label,
        "optionName": f"metric_{uuid.uuid4().hex[:12]}",
    }


def sql_column(expression, label):
    return {
        "expressionType": "SQL",
        "sqlExpression": expression,
        "label": label,
    }


def sql_filter(expression):
    return {
        "expressionType": "SQL",
        "clause": "WHERE",
        "sqlExpression": expression,
        "filterOptionName": f"filter_{uuid.uuid4().hex[:12]}",
    }


# Метрики сводной таблицы — формулы из шага 5. Деление на ноль: NULLIF
# возвращает NULL, строка канала остаётся в таблице, метрика пустая (N/A).
VISITORS = sql_metric("SUM(visitors_count)", "visitors_count")
LEADS = sql_metric("SUM(leads_count)", "leads_count")
PURCHASES = sql_metric("SUM(purchases_count)", "purchases_count")
COST = sql_metric("SUM(total_cost)", "total_cost")
REVENUE = sql_metric("COALESCE(SUM(revenue), 0)", "revenue")
CPU = sql_metric(
    "ROUND(SUM(total_cost)::numeric / NULLIF(SUM(visitors_count), 0), 2)",
    "cpu",
)
CPL = sql_metric(
    "ROUND(SUM(total_cost)::numeric / NULLIF(SUM(leads_count), 0), 2)",
    "cpl",
)
CPPU = sql_metric(
    "ROUND(SUM(total_cost)::numeric / NULLIF(SUM(purchases_count), 0), 2)",
    "cppu",
)
ROI = sql_metric(
    "ROUND((COALESCE(SUM(revenue), 0) - SUM(total_cost)) * 100.0"
    " / NULLIF(SUM(total_cost), 0), 2)",
    "roi, %",
)
CONV_LEAD = sql_metric(
    "ROUND(SUM(leads_count) * 100.0 / NULLIF(SUM(visitors_count), 0), 2)",
    "Клик → лид, %",
)
CONV_PURCHASE = sql_metric(
    "ROUND(SUM(purchases_count) * 100.0 / NULLIF(SUM(leads_count), 0), 2)",
    "Лид → оплата, %",
)
UNIQUE_VISITORS = sql_metric("COUNT(DISTINCT visitor_id)", "Посетители")
# Каналы с расходами: условие на итог по группе (HAVING), чтобы визиты
# и выручка дней без расходов тоже вошли в расчёт метрик.
PAID_ONLY = {**sql_filter("SUM(total_cost) > 0"), "clause": "HAVING"}


def timeseries_params(x_column, metrics, time_grain, x_title, y_title,
                      number_format, groupby=None, stack=False,
                      series_limit=0, filters=None, rotate=False):
    params = {
        "x_axis": x_column,
        "time_grain_sqla": time_grain,
        "metrics": metrics,
        "groupby": groupby or [],
        "adhoc_filters": filters or [],
        "row_limit": 10000,
        "series_limit": series_limit,
        "series_limit_metric": metrics[0] if series_limit else None,
        "order_desc": True,
        "show_value": True,
        "only_total": stack,
        "stack": "Stack" if stack else None,
        "show_legend": bool(groupby),
        "legendOrientation": "top",
        "legendType": "scroll",
        "rich_tooltip": True,
        "y_axis_format": number_format,
        "x_axis_time_format": "%d.%m" if time_grain != "P1M" else "%m.%Y",
        "x_axis_title": x_title,
        "x_axis_title_margin": 30,
        "y_axis_title": y_title,
        "y_axis_title_margin": 50,
        "y_axis_title_position": "Left",
        "xAxisLabelRotation": 45 if rotate else 0,
        "truncateXAxis": True,
        "color_scheme": "supersetColors",
        "comparison_type": "values",
    }
    return params


def bar_params(x_column, metrics, x_title, y_title, number_format,
               groupby=None, filters=None, horizontal=False,
               sort_asc=False, row_limit=1000):
    return {
        "x_axis": x_column,
        "metrics": metrics,
        "groupby": groupby or [],
        "adhoc_filters": filters or [],
        "row_limit": row_limit,
        "orientation": "horizontal" if horizontal else "vertical",
        "show_value": True,
        "show_legend": len(metrics) > 1 or bool(groupby),
        "legendOrientation": "top",
        "rich_tooltip": True,
        "y_axis_format": number_format,
        "x_axis_title": x_title,
        "x_axis_title_margin": 200 if horizontal else 30,
        "y_axis_title": y_title,
        "y_axis_title_margin": 30 if horizontal else 50,
        "y_axis_title_position": "Left",
        "x_axis_sort": metrics[0]["label"],
        "x_axis_sort_asc": sort_asc,
        "truncateXAxis": True,
        "color_scheme": "supersetColors",
    }


def temporal_filter(column):
    return {
        "expressionType": "SIMPLE",
        "clause": "WHERE",
        "subject": column,
        "operator": "TEMPORAL_RANGE",
        "comparator": "No filter",
        "filterOptionName": f"filter_{uuid.uuid4().hex[:12]}",
    }


def big_number(metric, subheader, number_format=",d"):
    return {
        "metric": metric,
        "subheader": subheader,
        "y_axis_format": number_format,
        "adhoc_filters": [],
    }


def summary_table(groupby, filters=None, row_limit=1000, sort_metric=VISITORS):
    return {
        "query_mode": "aggregate",
        "groupby": groupby,
        "metrics": [VISITORS, LEADS, PURCHASES, COST, REVENUE,
                    CPU, CPL, CPPU, ROI, CONV_LEAD, CONV_PURCHASE],
        "all_columns": [],
        "percent_metrics": [],
        "adhoc_filters": filters or [],
        "order_by_cols": [],
        "timeseries_limit_metric": sort_metric,
        "order_desc": True,
        "row_limit": row_limit,
        "server_page_length": 50,
        "table_timestamp_format": "%Y-%m-%d",
        "show_totals": True,
        "include_search": True,
        "show_cell_bars": False,
        "color_pn": True,
        "allow_rearrange_columns": False,
        "conditional_formatting": [],
        "column_config": {
            "visitors_count": {"d3NumberFormat": ",d"},
            "total_cost": {"d3NumberFormat": ",d"},
            "revenue": {"d3NumberFormat": ",d"},
            "cpu": {"d3NumberFormat": ",.2f"},
            "cpl": {"d3NumberFormat": ",.2f"},
            "cppu": {"d3NumberFormat": ",.2f"},
            "roi, %": {"d3NumberFormat": ",.2f"},
        },
    }


def chart_specs():
    channel = sql_column(
        "utm_source || ' / ' || utm_medium || ' / ' || utm_campaign",
        "Кампания (source / medium / campaign)",
    )
    return [
        {
            "key": "kpi_visitors",
            "name": "Уникальные посетители",
            "dataset": "sessions",
            "viz_type": "big_number_total",
            "params": big_number(UNIQUE_VISITORS,
                                 "посетителей сайта за период"),
        },
        {
            "key": "kpi_leads",
            "name": "Лиды",
            "dataset": "last_paid_click",
            "viz_type": "big_number_total",
            "params": big_number(sql_metric("COUNT(lead_id)", "Лиды"),
                                 "лидов после платного клика"),
        },
        {
            "key": "kpi_purchases",
            "name": "Покупки",
            "dataset": "last_paid_click",
            "viz_type": "big_number_total",
            "params": big_number(
                sql_metric("COUNT(lead_id) FILTER (WHERE is_purchase)",
                           "Покупки"),
                "успешно закрытых лидов",
            ),
        },
        {
            "key": "kpi_revenue",
            "name": "Выручка",
            "dataset": "last_paid_click",
            "viz_type": "big_number_total",
            "params": big_number(
                sql_metric("SUM(amount) FILTER (WHERE is_purchase)",
                           "Выручка"),
                "выручка с покупок, руб.",
            ),
        },
        {
            "key": "kpi_cost",
            "name": "Расходы на рекламу",
            "dataset": "ads_costs",
            "viz_type": "big_number_total",
            "params": big_number(sql_metric("SUM(total_cost)", "Расходы"),
                                 "расходы VK и Яндекса, руб."),
        },
        {
            "key": "visitors_daily",
            "name": "Посетители по дням: платный и бесплатный трафик",
            "dataset": "sessions",
            "viz_type": "echarts_timeseries_bar",
            "params": timeseries_params(
                "visit_date", [UNIQUE_VISITORS], "P1D", "День",
                "Посетители", ",d", groupby=["traffic_type"], stack=True,
                rotate=True,
            ),
        },
        {
            "key": "visitors_weekly",
            "name": "Посетители по неделям: топ-5 источников",
            "dataset": "sessions",
            "viz_type": "echarts_timeseries_bar",
            "params": timeseries_params(
                "visit_date", [UNIQUE_VISITORS], "P1W", "Неделя (начало)",
                "Посетители", ",d", groupby=["utm_source"], series_limit=5,
            ),
        },
        {
            "key": "visitors_monthly",
            "name": "Посетители по месяцам: топ-8 источников",
            "dataset": "sessions",
            "viz_type": "echarts_timeseries_bar",
            "params": timeseries_params(
                "visit_date", [UNIQUE_VISITORS], "P1M", "Месяц",
                "Посетители", ",d", groupby=["utm_source"], series_limit=8,
            ),
        },
        {
            "key": "visitors_share",
            "name": "Доля источников в посетителях",
            "dataset": "sessions",
            "viz_type": "pie",
            "params": {
                "groupby": ["utm_source"],
                "metric": UNIQUE_VISITORS,
                "adhoc_filters": [],
                "row_limit": 6,
                "sort_by_metric": True,
                "show_labels": True,
                "label_type": "key_percent",
                "number_format": ",d",
                "labels_outside": True,
                "label_line": True,
                "show_legend": True,
                "legendOrientation": "top",
                "donut": True,
                "show_total": True,
                "innerRadius": 35,
                "outerRadius": 70,
                "color_scheme": "supersetColors",
            },
        },
        {
            "key": "leads_daily",
            "name": "Лиды и покупки по дням создания лида",
            "dataset": "last_paid_click",
            "time_column": "created_at",
            "viz_type": "echarts_timeseries_bar",
            "params": timeseries_params(
                "created_at",
                [sql_metric("COUNT(lead_id)", "Лиды"),
                 sql_metric("COUNT(lead_id) FILTER (WHERE is_purchase)",
                            "Покупки")],
                "P1D", "День создания лида", "Количество", ",d",
                filters=[sql_filter("lead_id IS NOT NULL")], rotate=True,
            ),
        },
        {
            "key": "conversion_by_source",
            "name": "Конверсия из клика в лид и из лида в оплату, %",
            "dataset": "aggregate_last_paid_click",
            "viz_type": "echarts_timeseries_bar",
            "params": bar_params(
                "utm_source", [CONV_LEAD, CONV_PURCHASE], "Источник",
                "Конверсия, %", ",.2f",
                # Источники, давшие хотя бы 500 визитов за период
                filters=[{**sql_filter("SUM(visitors_count) >= 500"),
                          "clause": "HAVING"}],
            ),
        },
        {
            "key": "cost_daily",
            "name": "Расходы на рекламу по дням, руб.",
            "dataset": "ads_costs",
            "viz_type": "echarts_timeseries_bar",
            "params": timeseries_params(
                "campaign_date", [sql_metric("SUM(total_cost)", "Расходы")],
                "P1D", "День", "Расходы, руб.", ",d",
                groupby=["utm_source"], stack=True, rotate=True,
            ),
        },
        {
            "key": "cost_weekly",
            "name": "Расходы на рекламу по неделям, руб.",
            "dataset": "ads_costs",
            "viz_type": "echarts_timeseries_bar",
            "params": timeseries_params(
                "campaign_date", [sql_metric("SUM(total_cost)", "Расходы")],
                "P1W", "Неделя (начало)", "Расходы, руб.", ",d",
                groupby=["utm_source"],
            ),
        },
        {
            "key": "roi_by_source",
            "name": "Окупаемость (ROI) по источникам, %",
            "dataset": "aggregate_last_paid_click",
            "viz_type": "echarts_timeseries_bar",
            "params": bar_params(
                "utm_source", [ROI], "Источник", "ROI, %", ",.1f",
                filters=[PAID_ONLY],
            ),
        },
        {
            "key": "roi_by_campaign",
            "name": "Окупаемость (ROI) по кампаниям, %",
            "dataset": "aggregate_last_paid_click",
            "viz_type": "echarts_timeseries_bar",
            "params": bar_params(
                channel, [ROI], "Кампания", "ROI, %", ",.0f",
                filters=[PAID_ONLY], horizontal=True,
                sort_asc=True,
            ) | {
                # Запас по оси, чтобы подпись самого длинного столбца
                # не обрезалась.
                "truncateYAxis": True,
                "y_axis_bounds": [-200, 5600],
            },
        },
        {
            "key": "metrics_by_source",
            "name": "Сводная таблица по utm_source",
            "dataset": "aggregate_last_paid_click",
            "viz_type": "table",
            "params": summary_table(["utm_source"], row_limit=50),
        },
        {
            "key": "metrics_by_campaign",
            "name": "Метрики по source / medium / campaign",
            "dataset": "aggregate_last_paid_click",
            "viz_type": "table",
            "params": summary_table(
                ["utm_source", "utm_medium", "utm_campaign"], sort_metric=COST,
                filters=[PAID_ONLY],
            ),
        },
    ]


DASHBOARD_NOTE = (
    "# Онлайн-школа: сквозная аналитика\n"
    "Июнь 2023, база marketingdb. Атрибуция — **Last Paid Click**: лид "
    "засчитывается последнему платному визиту посетителя. Расходы в сводных "
    "таблицах сопоставлены визитам по дате и меткам utm; график расходов "
    "показывает все траты рекламных кабинетов. Фильтры сверху: период, "
    "utm_source, utm_medium, utm_campaign, шаг времени (день / неделя / месяц)."
)

FORMULAS_NOTE = (
    "**Метрики:** cpu = total_cost / visitors_count · "
    "cpl = total_cost / leads_count · cppu = total_cost / purchases_count · "
    "roi = (revenue − total_cost) / total_cost × 100%. "
    "Если делитель равен нулю, метрика пустая (N/A), строка канала остаётся."
)

# Раскладка дашборда: строки из (ключ графика | markdown, ширина, высота).
LAYOUT = [
    [("md:" + DASHBOARD_NOTE, 12, 22)],
    [("kpi_visitors", 3, 30), ("kpi_leads", 2, 30), ("kpi_purchases", 2, 30),
     ("kpi_revenue", 2, 30), ("kpi_cost", 3, 30)],
    [("md:## Сколько посетителей и какие каналы их приводят", 12, 8)],
    [("visitors_daily", 12, 60)],
    [("visitors_weekly", 12, 60)],
    [("visitors_monthly", 6, 60),
     ("visitors_share", 6, 60)],
    [("md:## Лиды и конверсия", 12, 8)],
    [("leads_daily", 7, 60), ("conversion_by_source", 5, 60)],
    [("md:## Расходы на рекламу", 12, 8)],
    [("cost_daily", 7, 60), ("cost_weekly", 5, 60)],
    [("md:## Окупаемость каналов", 12, 8)],
    [("roi_by_source", 4, 80), ("roi_by_campaign", 8, 80)],
    [("md:" + FORMULAS_NOTE, 12, 10)],
    [("metrics_by_source", 12, 60)],
    [("metrics_by_campaign", 12, 100)],
]


class Superset:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def login(self, username, password):
        response = self.session.post(
            f"{self.base_url}/api/v1/security/login",
            json={"username": username, "password": password,
                  "provider": "db", "refresh": True},
            timeout=30,
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        self.session.headers["Authorization"] = f"Bearer {token}"

    def request(self, method, path, **kwargs):
        response = self.session.request(
            method, f"{self.base_url}/api/v1/{path}", timeout=60, **kwargs
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"{method} {path}: {response.status_code} {response.text}"
            )
        return response.json() if response.text else {}

    def list_all(self, resource):
        return self.request(
            "GET", f"{resource}/", params={"q": "(page_size:100)"}
        )["result"]


def delete_previous(api, chart_names):
    for dashboard in api.list_all("dashboard"):
        if dashboard.get("slug") == DASHBOARD_SLUG:
            api.request("DELETE", f"dashboard/{dashboard['id']}")
    for chart in api.list_all("chart"):
        if chart["slice_name"] in chart_names:
            api.request("DELETE", f"chart/{chart['id']}")
    for dataset in api.list_all("dataset"):
        if dataset["table_name"] in DATASETS:
            api.request("DELETE", f"dataset/{dataset['id']}")


def create_datasets(api, database_id):
    ids = {}
    for name, time_column in DATASETS.items():
        dataset_id = api.request("POST", "dataset/", json={
            "database": database_id, "schema": SCHEMA, "table_name": name,
        })["id"]
        api.request("PUT", f"dataset/{dataset_id}",
                    json={"main_dttm_col": time_column})
        ids[name] = dataset_id
    return ids


def chart_uuids(api, chart_ids):
    """uuid графиков нужен в раскладке: по нему импорт связывает графики.

    REST API отдаёт uuid только в выгрузке, поэтому берём его из zip-архива
    экспорта графиков (файл charts/<имя>_<id>.yaml).
    """
    ids = ",".join(str(chart_id) for chart_id in chart_ids.values())
    response = api.session.get(
        f"{api.base_url}/api/v1/chart/export/",
        params={"q": f"!({ids})"}, timeout=60,
    )
    response.raise_for_status()
    uuids = {}
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        for name in archive.namelist():
            if "/charts/" not in name:
                continue
            chart_id = int(name.rsplit("/", 1)[1].rsplit("_", 1)[-1][:-5])
            for line in archive.read(name).decode().splitlines():
                if line.startswith("uuid: "):
                    uuids[chart_id] = line.split(": ", 1)[1].strip()
    return uuids


def build_position(chart_ids, chart_names, uuids):
    position = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID",
                    "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [],
                    "parents": ["ROOT_ID"]},
        "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER",
                      "meta": {"text": DASHBOARD_TITLE}},
    }
    for row_index, row in enumerate(LAYOUT, start=1):
        row_id = f"ROW-{row_index}"
        position["GRID_ID"]["children"].append(row_id)
        position[row_id] = {
            "type": "ROW", "id": row_id, "children": [],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
        for item_index, (key, width, height) in enumerate(row, start=1):
            parents = ["ROOT_ID", "GRID_ID", row_id]
            if key.startswith("md:"):
                item_id = f"MARKDOWN-{row_index}-{item_index}"
                position[item_id] = {
                    "type": "MARKDOWN", "id": item_id, "children": [],
                    "parents": parents,
                    "meta": {"width": width, "height": height,
                             "code": key[len("md:"):]},
                }
            else:
                item_id = f"CHART-{key}"
                position[item_id] = {
                    "type": "CHART", "id": item_id, "children": [],
                    "parents": parents,
                    "meta": {"width": width, "height": height,
                             "chartId": chart_ids[key],
                             "uuid": uuids[chart_ids[key]],
                             "sliceName": chart_names[key]},
                }
            position[row_id]["children"].append(item_id)
    return position


def native_filter(filter_id, name, filter_type, chart_ids, target=None,
                  control_values=None):
    return {
        "id": filter_id,
        "name": name,
        "filterType": filter_type,
        "targets": [target] if target else [{}],
        "controlValues": control_values or {},
        "defaultDataMask": {"extraFormData": {}, "filterState": {},
                            "ownState": {}},
        "cascadeParentIds": [],
        "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
        "type": "NATIVE_FILTER",
        "description": "",
        "chartsInScope": chart_ids,
        "tabsInScope": [],
    }


def native_filters(dataset_ids, chart_ids):
    all_charts = sorted(chart_ids.values())
    select_values = {
        "enableEmptyFilter": False,
        "defaultToFirstItem": False,
        "multiSelect": True,
        "searchAllOptions": False,
        "inverseSelection": False,
    }
    utm_dataset = dataset_ids["aggregate_last_paid_click"]
    filters = [
        native_filter("NATIVE_FILTER-period", "Период", "filter_time",
                      all_charts),
        native_filter(
            "NATIVE_FILTER-time-grain", "Шаг времени", "filter_timegrain",
            all_charts, target={"datasetId": dataset_ids["sessions"]},
        ),
    ]
    for column in ("utm_source", "utm_medium", "utm_campaign"):
        filters.append(native_filter(
            f"NATIVE_FILTER-{column.replace('_', '-')}", column,
            "filter_select", all_charts,
            target={"datasetId": utm_dataset, "column": {"name": column}},
            control_values=select_values,
        ))
    return filters


def main():
    api = Superset(SUPERSET_URL)
    api.login(USERNAME, PASSWORD)

    database_id = next(
        db["id"] for db in api.list_all("database")
        if db["database_name"] == DATABASE_NAME
    )
    specs = chart_specs()
    chart_names = {spec["key"]: spec["name"] for spec in specs}

    delete_previous(api, set(chart_names.values()))
    dataset_ids = create_datasets(api, database_id)

    dashboard_id = api.request("POST", "dashboard/", json={
        "dashboard_title": DASHBOARD_TITLE,
        "slug": DASHBOARD_SLUG,
        "published": True,
    })["id"]

    chart_ids = {}
    for spec in specs:
        dataset_id = dataset_ids[spec["dataset"]]
        params = {
            "datasource": f"{dataset_id}__table",
            "viz_type": spec["viz_type"],
            "time_range": "No filter",
            **spec["params"],
        }
        # Фильтр периода дашборда подставляет диапазон в этот фильтр
        # TEMPORAL_RANGE по столбцу даты графика.
        time_column = spec.get("time_column", DATASETS[spec["dataset"]])
        params["adhoc_filters"] = [
            temporal_filter(time_column), *params.get("adhoc_filters", []),
        ]
        chart_ids[spec["key"]] = api.request("POST", "chart/", json={
            "slice_name": spec["name"],
            "viz_type": spec["viz_type"],
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "params": json.dumps(params, ensure_ascii=False),
            "dashboards": [dashboard_id],
        })["id"]

    api.request("PUT", f"dashboard/{dashboard_id}", json={
        "position_json": json.dumps(
            build_position(chart_ids, chart_names,
                           chart_uuids(api, chart_ids)),
            ensure_ascii=False
        ),
        "json_metadata": json.dumps({
            "color_scheme": "supersetColors",
            "refresh_frequency": 0,
            "native_filter_configuration": native_filters(dataset_ids,
                                                          chart_ids),
        }, ensure_ascii=False),
    })

    print(f"Дашборд {dashboard_id}: {SUPERSET_URL}/superset/dashboard/"
          f"{DASHBOARD_SLUG}/")
    for key, chart_id in chart_ids.items():
        print(f"  {chart_id}: {chart_names[key]}")


if __name__ == "__main__":
    main()
