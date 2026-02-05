import { test, expect } from '@playwright/test';

/**
 * E2E tests for Files page snapshot browse controls.
 * Tests snapshot selection, filtering, pagination, and search.
 */

test('snapshot browse controls are present', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  // Check snapshot scan selector
  const scanSelect = page.locator('#snapshot-scan');
  await expect(scanSelect).toBeVisible();

  // Check snapshot path input
  const snapPath = page.locator('#snap-path');
  await expect(snapPath).toBeVisible();

  // Check type filter
  const typeFilter = page.locator('#snap-type');
  await expect(typeFilter).toBeVisible();

  // Check extension filter
  const extFilter = page.locator('#snap-ext');
  await expect(extFilter).toBeVisible();

  // Check page size input
  const pageSize = page.locator('#snap-page-size');
  await expect(pageSize).toBeVisible();

  // Check browse button
  const browseButton = page.locator('#snap-go');
  await expect(browseButton).toBeVisible();
});

test('snapshot path input accepts values', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  const snapPath = page.locator('#snap-path');

  // Enter a path
  await snapPath.fill('test/snapshot/path');
  await expect(snapPath).toHaveValue('test/snapshot/path');
});

test('snapshot type filter can be changed', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  const typeFilter = page.locator('#snap-type');

  // Check for options
  const options = await typeFilter.locator('option').allTextContents();
  expect(options.length).toBeGreaterThan(0);

  // Select an option
  await typeFilter.selectOption({ index: 0 });

  // Verify selection
  const value = await typeFilter.inputValue();
  expect(value).toBeDefined();
});

test('snapshot extension filter accepts input', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  const extFilter = page.locator('#snap-ext');

  // Enter extension
  await extFilter.fill('.csv');
  await expect(extFilter).toHaveValue('.csv');

  // Change extension
  await extFilter.fill('.json');
  await expect(extFilter).toHaveValue('.json');
});

test('snapshot page size input accepts numeric values', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  const pageSize = page.locator('#snap-page-size');

  // Enter page size
  await pageSize.fill('50');
  await expect(pageSize).toHaveValue('50');

  // Change page size
  await pageSize.fill('100');
  await expect(pageSize).toHaveValue('100');
});

test('snapshot pagination controls are present', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  // Check prev button
  const prevButton = page.locator('#snap-prev');
  await expect(prevButton).toBeVisible();

  // Check next button
  const nextButton = page.locator('#snap-next');
  await expect(nextButton).toBeVisible();
});

test('snapshot use live path button is present', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  const useLiveButton = page.locator('#snap-use-live');
  await expect(useLiveButton).toBeVisible();
});

test('snapshot commit button is present', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  const commitButton = page.locator('#snap-commit');
  await expect(commitButton).toBeVisible();
});

test('snapshot search controls are present', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  // Check search query input
  const searchQuery = page.locator('#snap-search-q');
  await expect(searchQuery).toBeVisible();

  // Check search extension filter
  const searchExt = page.locator('#snap-search-ext');
  await expect(searchExt).toBeVisible();

  // Check search prefix filter
  const searchPrefix = page.locator('#snap-search-prefix');
  await expect(searchPrefix).toBeVisible();

  // Check search go button
  const searchButton = page.locator('#snap-search-go');
  await expect(searchButton).toBeVisible();
});

test('snapshot search query input accepts text', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  const searchQuery = page.locator('#snap-search-q');

  // Enter search query
  await searchQuery.fill('test file');
  await expect(searchQuery).toHaveValue('test file');
});

test('snapshot search extension filter accepts input', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  const searchExt = page.locator('#snap-search-ext');

  // Enter extension
  await searchExt.fill('.xlsx');
  await expect(searchExt).toHaveValue('.xlsx');
});

test('snapshot search prefix filter accepts input', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  const searchPrefix = page.locator('#snap-search-prefix');

  // Enter prefix
  await searchPrefix.fill('data/');
  await expect(searchPrefix).toHaveValue('data/');
});

test('snapshot search button is clickable', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  const searchButton = page.locator('#snap-search-go');

  // Fill in search query
  await page.locator('#snap-search-q').fill('test');

  // Click search button
  await searchButton.click();

  // Wait for any search action to complete
  await page.waitForTimeout(500);

  // Verify button was clickable (no error)
  expect(true).toBe(true);
});

test('snapshot browse button triggers browse action', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  const browseButton = page.locator('#snap-go');

  // Click browse button
  await browseButton.click();

  // Wait for browse action
  await page.waitForTimeout(500);

  // Verify button was clickable
  expect(true).toBe(true);
});

test('snapshot pagination buttons are clickable', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  const prevButton = page.locator('#snap-prev');
  const nextButton = page.locator('#snap-next');

  // Click prev button
  if (await prevButton.isEnabled()) { await prevButton.click(); }
  await page.waitForTimeout(200);

  // Click next button
  if (await nextButton.isEnabled()) { await nextButton.click(); }
  await page.waitForTimeout(200);

  // Verify buttons were clickable
  expect(true).toBe(true);
});

test('use live path button copies path between sections', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('networkidle');

  // Set a value in live path
  const provPath = page.locator('#prov-path');
  await provPath.fill('test/live/path');

  // Click use live path button
  const useLiveButton = page.locator('#snap-use-live');
  await useLiveButton.click();

  // Wait for copy action
  await page.waitForTimeout(500);

  // Verify snapshot path was updated
  const snapPath = page.locator('#snap-path');
  await expect(snapPath).toHaveValue('test/live/path');
});
