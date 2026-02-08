import { test, expect } from '@playwright/test';

// Basic smoke: load landing page (Settings) and ensure no severe console errors

test('landing page loads without console errors and has stable navigation', async ({ page, baseURL }) => {
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

  // Stable navigation hooks should exist (Settings is now the landing page)
  await expect(page.getByTestId('nav-files')).toBeVisible();
  await expect(page.getByTestId('header')).toBeVisible();

  // Settings page should have sidebar
  await expect(page.locator('.settings-sidebar')).toBeVisible();

  // Allow some network/idling time
  await page.waitForLoadState('networkidle');

  // No error-level logs (allow expected API 404s/405s)
  const errors = consoleMessages.filter((m) =>
    m.type === 'error' &&
    !m.text.includes('Failed to load resource') &&
    !m.text.includes('404') &&
    !m.text.includes('405')
  );
  if (errors.length) {
    console.error('Console errors observed:', errors);
  }
  expect(errors.length).toBe(0);
});
