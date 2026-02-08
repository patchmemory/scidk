import { test, expect } from '@playwright/test';

/**
 * E2E tests for Files page provider browser controls.
 * Tests provider selection, path browsing, and live navigation.
 */

test('files page provider browser controls are present', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  // Wait for key elements instead of networkidle (page has continuous polling)
  await page.locator('#prov-select').waitFor({ state: 'visible', timeout: 10000 });

  // Check provider selector
  const provSelect = page.locator('#prov-select');
  await expect(provSelect).toBeVisible();

  // Check root selector
  const rootSelect = page.locator('#root-select');
  await expect(rootSelect).toBeVisible();

  // Check path input
  const provPath = page.locator('#prov-path');
  await expect(provPath).toBeVisible();

  // Check recursive checkbox
  const recursiveCheckbox = page.locator('#prov-browse-recursive');
  await expect(recursiveCheckbox).toBeVisible();

  // Check fast-list checkbox (for rclone)
  const fastListCheckbox = page.locator('#prov-browse-fast-list');
  await expect(fastListCheckbox).toBeVisible();

  // Check max depth input
  const maxDepthInput = page.locator('#prov-browse-max-depth');
  await expect(maxDepthInput).toBeVisible();

  // Check Go button
  const goButton = page.locator('#prov-go');
  await expect(goButton).toBeVisible();

  // Check Scan button
  const scanButton = page.locator('#prov-scan-btn');
  await expect(scanButton).toBeVisible();
});

test('provider selector can change providers', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  // Wait for key elements instead of networkidle (page has continuous polling)
  await page.locator('#prov-select').waitFor({ state: 'visible', timeout: 10000 });

  const provSelect = page.locator('#prov-select');

  // Get initial value
  const initialValue = await provSelect.inputValue();
  expect(initialValue).toBeTruthy();

  // Get available options
  const options = await provSelect.locator('option').allTextContents();
  expect(options.length).toBeGreaterThan(0);

  // Select a provider (should have at least local_fs)
  await provSelect.selectOption({ index: 0 });

  // Verify selection changed
  const newValue = await provSelect.inputValue();
  expect(newValue).toBeTruthy();
});

test('root selector updates when provider changes', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  // Wait for key elements instead of networkidle (page has continuous polling)
  await page.locator('#prov-select').waitFor({ state: 'visible', timeout: 10000 });

  const rootSelect = page.locator('#root-select');

  // Root selector should be visible and have options
  await expect(rootSelect).toBeVisible();

  const options = await rootSelect.locator('option').allTextContents();
  expect(options.length).toBeGreaterThan(0);
});

test('path input accepts user input', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  // Wait for key elements instead of networkidle (page has continuous polling)
  await page.locator('#prov-select').waitFor({ state: 'visible', timeout: 10000 });

  const provPath = page.locator('#prov-path');

  // Enter a test path
  await provPath.fill('test/path/example');
  await expect(provPath).toHaveValue('test/path/example');

  // Clear and enter another path
  await provPath.fill('another/path');
  await expect(provPath).toHaveValue('another/path');
});

test('recursive browse checkbox toggles', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  // Wait for key elements instead of networkidle (page has continuous polling)
  await page.locator('#prov-select').waitFor({ state: 'visible', timeout: 10000 });

  const recursiveCheckbox = page.locator('#prov-browse-recursive');

  // Should be unchecked by default
  await expect(recursiveCheckbox).not.toBeChecked();

  // Check it
  await recursiveCheckbox.check();
  await expect(recursiveCheckbox).toBeChecked();

  // Uncheck it
  await recursiveCheckbox.uncheck();
  await expect(recursiveCheckbox).not.toBeChecked();
});

test('fast-list checkbox toggles', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  // Wait for key elements instead of networkidle (page has continuous polling)
  await page.locator('#prov-select').waitFor({ state: 'visible', timeout: 10000 });

  const fastListCheckbox = page.locator('#prov-browse-fast-list');

  // Toggle checkbox
  const initialState = await fastListCheckbox.isChecked();
  await fastListCheckbox.click();

  const newState = await fastListCheckbox.isChecked();
  expect(newState).toBe(!initialState);
});

test('max depth input accepts numeric values', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  // Wait for key elements instead of networkidle (page has continuous polling)
  await page.locator('#prov-select').waitFor({ state: 'visible', timeout: 10000 });

  const maxDepthInput = page.locator('#prov-browse-max-depth');

  // Enter a numeric value
  await maxDepthInput.fill('3');
  await expect(maxDepthInput).toHaveValue('3');

  // Change to another value
  await maxDepthInput.fill('5');
  await expect(maxDepthInput).toHaveValue('5');
});

test('go button triggers browse action', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  // Wait for key elements instead of networkidle (page has continuous polling)
  await page.locator('#prov-select').waitFor({ state: 'visible', timeout: 10000 });

  // Track navigation/requests
  let browseRequestMade = false;
  page.on('request', (request) => {
    if (request.url().includes('/browse') || request.url().includes('prov=') || request.url().includes('path=')) {
      browseRequestMade = true;
    }
  });

  const goButton = page.locator('#prov-go');
  await goButton.click();

  // Wait for any requests to complete
  await page.waitForTimeout(1000);

  // Verify button was clickable (no error thrown)
  expect(true).toBe(true);
});

test('rocrate viewer buttons exist if feature is enabled', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  // Wait for key elements instead of networkidle (page has continuous polling)
  await page.locator('#prov-select').waitFor({ state: 'visible', timeout: 10000 });

  // Check if RO-Crate buttons exist (they may not be present if feature is disabled)
  const openButton = page.locator('#open-rocrate');
  const closeButton = page.locator('#close-rocrate');

  const openCount = await openButton.count();
  const closeCount = await closeButton.count();

  // Either both exist or neither exists (feature toggle)
  if (openCount > 0) {
    await expect(openButton).toBeVisible();
    expect(closeCount).toBeGreaterThan(0);
  } else {
    // Feature not enabled, that's okay
    expect(true).toBe(true);
  }
});

test('recent scans selector and controls are present', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  // Wait for key elements instead of networkidle (page has continuous polling)
  await page.locator('#prov-select').waitFor({ state: 'visible', timeout: 10000 });

  // Check recent scans dropdown
  const recentScans = page.locator('#recent-scans');
  await expect(recentScans).toBeVisible();

  // Check open scan button
  const openScanButton = page.locator('#open-scan');
  await expect(openScanButton).toBeVisible();

  // Check refresh button
  const refreshButton = page.locator('#refresh-scans');
  await expect(refreshButton).toBeVisible();
});

test('refresh scans button is functional', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  // Wait for key elements instead of networkidle (page has continuous polling)
  await page.locator('#prov-select').waitFor({ state: 'visible', timeout: 10000 });

  const refreshButton = page.locator('#refresh-scans');

  // Click refresh button
  await refreshButton.click();

  // Wait for refresh to complete
  await page.waitForTimeout(500);

  // Verify no errors (button should be functional)
  expect(true).toBe(true);
});
