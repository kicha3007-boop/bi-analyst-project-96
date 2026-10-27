"""Настройки локального Superset для проекта «Онлайн-школа»."""

import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]

SQLALCHEMY_DATABASE_URI = (
    "postgresql+psycopg2://{user}:{password}@db:5432/superset".format(
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
)

# Локальный стенд без HTTPS: упрощаем CSRF для REST API-скриптов.
WTF_CSRF_ENABLED = False
TALISMAN_ENABLED = False

BABEL_DEFAULT_LOCALE = "ru"
LANGUAGES = {
    "ru": {"flag": "ru", "name": "Русский"},
    "en": {"flag": "us", "name": "English"},
}

FEATURE_FLAGS = {
    "DASHBOARD_RBAC": False,
}
