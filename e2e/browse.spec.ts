import { test, expect } from '@playwright/test';

// Browse flow: navigate to Files and ensure stable hooks are present and no console errors

test('files page loads and shows stable hooks', async ({ page, baseURL }) => {
  const consoleMessages: { type: string; text: string }[] = [];
  page.on('console', (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  const url = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(url);

  // Go to Files via stable nav hook
  await page.getByTestId('nav-files').click();

  // Expect the Files page to render
  await expect(page.getByTestId('files-title')).toBeVisible();
  await expect(page.getByTestId('files-root')).toBeVisible();

  // Let network settle and ensure no console errors
  await page.waitForLoadState('networkidle');
  const errors = consoleMessages.filter((m) => m.type === 'error');
  expect(errors.length).toBe(0);
});
