// 浏览器端 E2E 测试（Playwright）。运行前需安装：
//   npm i -D @playwright/test && npx playwright install chromium
// 并先启动服务：python3 api/server.py
// 运行：npx playwright test tests/e2e_playwright.spec.js
const { test, expect } = require('@playwright/test');

const BASE = 'http://127.0.0.1:8090/';

test('市场概览加载真实数据与导航', async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator('#nav button')).toHaveCount(7);
  await expect(page.locator('.kpi .value').first()).not.toHaveText('');
  await expect(page.locator('.fp-tile')).toHaveCount(8);
});

test('交易格局成对环形图渲染', async ({ page }) => {
  await page.goto(BASE);
  await page.locator('#nav button').filter({ hasText: '交易格局' }).click();
  await expect(page.locator('.insight').first()).toContainText('关键发现');
  await expect(page.locator('canvas').first()).toBeVisible();
});

test('交易金额粒度切换与里程碑表', async ({ page }) => {
  await page.goto(BASE);
  await page.locator('#nav button').filter({ hasText: '交易金额' }).click();
  await page.locator('#eco-gran button').filter({ hasText: 'Quarter' }).click();
  await expect(page.locator('#eco-count-yoy')).toContainText('Q');
  await expect(page.locator('#ec-milestone tbody tr').first()).toBeVisible();
});

test('交易数据库检索与交易卡片', async ({ page }) => {
  await page.goto(BASE);
  await page.locator('#nav button').filter({ hasText: '交易数据库' }).click();
  await page.locator('#ex-search').fill('PD-1');
  await expect(page.locator('#ex-table tbody tr').first()).toBeVisible();
  await page.locator('#ex-table tbody tr').first().click();
  await expect(page.locator('#modalOverlay')).toHaveClass(/open/);
});
