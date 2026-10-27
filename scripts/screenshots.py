"""Снимает скриншоты дашборда «Онлайн-школа» и его графиков для презентации.

Результат — presentation/img/dashboard.png и presentation/img/<график>.png.
Запуск: make screenshots (контейнер tools, Superset должен быть поднят).
"""

import os
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from build_dashboard import chart_specs

SUPERSET_URL = os.environ.get("SUPERSET_URL", "http://localhost:8089")
USERNAME = os.environ.get("SUPERSET_ADMIN_USER", "admin")
PASSWORD = os.environ.get("SUPERSET_ADMIN_PASSWORD", "admin")
OUTPUT_DIR = Path("presentation/img")
VIEWPORT = {"width": 1600, "height": 1000}
RENDER_PAUSE_MS = 6000


def settle(page):
    """Ждёт, пока стихнут запросы; Superset иногда опрашивает сервер дольше."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        pass


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2,
                                locale="ru-RU")

        page.goto(f"{SUPERSET_URL}/login/")
        page.fill("#username", USERNAME)
        page.fill("#password", PASSWORD)
        page.click("[type=submit]")
        settle(page)

        page.goto(f"{SUPERSET_URL}/superset/dashboard/online-school/?standalone=1")
        settle(page)
        # Прокрутка до конца, чтобы отрисовались все ленивые графики.
        # Прокручиваем окно, а не колесом мыши: колесо прокручивает
        # таблицы внутри графиков и сдвигает их содержимое.
        for step in range(1, 11):
            page.evaluate(
                f"window.scrollTo(0, document.body.scrollHeight * {step} / 10)"
            )
            page.wait_for_timeout(500)
        page.evaluate("window.scrollTo(0, 0)")
        settle(page)
        page.wait_for_timeout(RENDER_PAUSE_MS)

        # Окно высотой во весь дашборд: снимок без «склейки» при прокрутке.
        height = page.evaluate("document.documentElement.scrollHeight")
        page.set_viewport_size({"width": VIEWPORT["width"], "height": height})
        page.wait_for_timeout(RENDER_PAUSE_MS)
        page.screenshot(path=str(OUTPUT_DIR / "dashboard.png"))

        keys_by_name = {spec["name"]: spec["key"] for spec in chart_specs()}

        holders = page.locator("[data-test-chart-id]")
        for index in range(holders.count()):
            holder = holders.nth(index)
            chart_id = holder.get_attribute("data-test-chart-id")
            container = holder.locator(
                "xpath=ancestor::div[contains(@class,"
                "'dashboard-component-chart-holder')]"
            ).first
            target = container if container.count() else holder
            target.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            chart = page.request.get(
                f"{SUPERSET_URL}/api/v1/chart/{chart_id}"
            ).json()["result"]
            key = keys_by_name.get(chart["slice_name"], f"chart_{chart_id}")
            path = OUTPUT_DIR / f"{key}.png"
            target.screenshot(path=str(path))
            print(f"{path}")

        browser.close()


if __name__ == "__main__":
    main()
