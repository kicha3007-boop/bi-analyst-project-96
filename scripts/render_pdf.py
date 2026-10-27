"""Собирает presentation.pdf из presentation/slides.html (Chromium).

Запуск: make presentation (контейнер tools). Картинки графиков берутся
из presentation/img/ — их готовит make screenshots.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

SLIDES = Path("presentation/slides.html").resolve()
OUTPUT = Path("presentation.pdf")


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(SLIDES.as_uri())
        page.wait_for_load_state("load")
        page.pdf(path=str(OUTPUT), prefer_css_page_size=True,
                 print_background=True)
        browser.close()
    print(f"{OUTPUT}: {OUTPUT.stat().st_size} байт")


if __name__ == "__main__":
    main()
