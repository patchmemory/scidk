import { test, expect } from '@playwright/test';

// Basic smoke: load home page and ensure no severe console errors

test('home loads without console errors and has stable hooks', async ({ page, baseURL }) => {
  const consoleMessages: { type: string; text: string }[] = [];
  page.on('console', (msg) => {
    const type = msg.type();
    const text = msg.text();
    consoleMessages.push({ type, text });
  });

  const url = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(url);

  // Basic page sanity
  await expect(page).toHaveTitle(/SciDK/i, { timeout: 10_000 });

  // Stable selector hooks should exist
  await expect(page.getByTestId('nav-files')).toBeVisible();
  await expect(page.getByTestId('header')).toBeVisible();
  await expect(page.getByTestId('home-recent-scans')).toBeVisible();

  // Allow some network/idling time
  await page.waitForLoadState('networkidle');

  // No error-level logs
  const errors = consoleMessages.filter((m) => m.type === 'error');
  if (errors.length) {
    console.error('Console errors observed:', errors);
  }
  expect(errors.length).toBe(0);
});
