# -*- coding: utf-8 -*-
"""浏览器端 E2E 测试（Playwright + pytest）。

前置：pip install playwright pytest && playwright install chromium
服务需已启动：python3 api/server.py
运行：python3 -m pytest tests/test_e2e.py -v
"""
import os
import pytest
from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8090/")

@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()

@pytest.fixture
def page(browser):
    pg = browser.new_page()
    yield pg
    pg.close()

def test_overview_loads(page):
    page.goto(BASE)
    page.locator(".kpi .value").first.wait_for()
    assert page.locator("#nav button").count() == 7
    assert page.locator(".kpi .value").first.inner_text().strip() != ""
    assert page.locator(".fp-tile").count() == 8

def test_landscape_paired_donuts(page):
    page.goto(BASE)
    page.locator("#nav button").filter(has_text="交易格局").click()
    page.locator(".insight").first.wait_for()
    page.wait_for_function("document.querySelector('.insight').textContent.includes('关键发现')")

def test_economics_granularity_and_milestones(page):
    page.goto(BASE)
    page.locator("#nav button").filter(has_text="交易金额").click()
    page.locator("#eco-gran button").filter(has_text="Quarter").click()
    page.wait_for_function("document.getElementById('eco-count-yoy').textContent.includes('Q')")
    assert page.locator("#ec-milestone tbody tr").count() > 0

def test_explorer_pagination_and_deal_card(page):
    page.goto(BASE)
    page.locator("#nav button").filter(has_text="交易数据库").click()
    page.locator("#ex-table tbody tr").first.wait_for()
    assert page.locator("#ex-prev").is_disabled()
    assert not page.locator("#ex-next").is_disabled()
    page.locator("#ex-table tbody tr").first.click()
    page.wait_for_selector("#modalOverlay.open")
    page.locator("#modal .x").click()

def test_filter_persists_in_url(page):
    page.goto(BASE)
    page.locator(".kpi .value").first.wait_for()
    page.wait_for_function("location.href.includes('year_from=')")
    page.locator("#nav button").filter(has_text="交易金额").click()
    page.locator(".kpi .value").first.wait_for()
    assert "year_from=" in page.url
