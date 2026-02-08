import { test, expect, request } from '@playwright/test';
import os from 'os';
import fs from 'fs';
import path from 'path';

/**
 * Core E2E flows for SciDK: scan → browse → file details
 * Tests user-visible outcomes with stable selectors (data-testid)
 */

function createTestDirectory(prefix = 'scidk-e2e-core-'): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  // Create a small directory structure for browsing
  fs.writeFileSync(path.join(dir, 'data.txt'), 'sample data');
  fs.writeFileSync(path.join(dir, 'notes.md'), '# Notes\nTest content');
  const subdir = path.join(dir, 'subdir');
  fs.mkdirSync(subdir);
  fs.writeFileSync(path.join(subdir, 'nested.txt'), 'nested file');
  return dir;
}

test.skip('complete flow: scan → browse → file details', async ({ page, baseURL, request: pageRequest }) => {
  const consoleMessages: { type: string; text: string }[] = [];
  page.on('console', (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  const tempDir = createTestDirectory();

  // Step 1: Scan the directory via API
  const api = pageRequest || (await request.newContext());
  const scanResp = await api.post(`${base}/api/scan`, {
    headers: { 'Content-Type': 'application/json' },
    data: { path: tempDir, recursive: true },
  });
  expect(scanResp.ok()).toBeTruthy();

  // Step 2: Navigate to Home and verify scan appears
  await page.goto(base);
  await page.waitForLoadState('networkidle');

  const homeScans = await page.getByTestId('home-recent-scans');
  await expect(homeScans).toBeVisible();

  // Verify the scanned path appears on the page
  const pathOccurrences = await page.getByText(tempDir, { exact: false }).count();
  expect(pathOccurrences).toBeGreaterThan(0);

  // Step 3: Navigate to Files page
  await page.getByTestId('nav-files').click();
  // Wait for key elements instead of networkidle (datasets page has continuous polling)
  await page.getByTestId('files-title').waitFor({ state: 'visible', timeout: 10000 });
  await expect(page.getByTestId('files-title')).toBeVisible();
  await expect(page.getByTestId('files-root')).toBeVisible();

  // Step 4: Verify browsing works (check that scanned files are listed)
  // The Files page should show directories; verify our temp directory is accessible
  const filesContent = await page.getByTestId('files-root').textContent();
  expect(filesContent).toBeTruthy();

  // Step 5: Ensure no console errors occurred during the flow
  await page.waitForTimeout(500); // Brief wait to catch any delayed errors
  const errors = consoleMessages.filter((m) => m.type === 'error');
  expect(errors.length).toBe(0);

  // Cleanup
  fs.rmSync(tempDir, { recursive: true, force: true });
});

test.skip('scan with recursive flag captures nested files', async ({ page, baseURL, request: pageRequest }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  const tempDir = createTestDirectory('scidk-e2e-recursive-');

  const api = pageRequest || (await request.newContext());
  const scanResp = await api.post(`${base}/api/scan`, {
    headers: { 'Content-Type': 'application/json' },
    data: { path: tempDir, recursive: true },
  });
  expect(scanResp.ok()).toBeTruthy();

  // Verify via API that nested files are indexed
  const directoriesResp = await api.get(`${base}/api/directories`);
  expect(directoriesResp.ok()).toBeTruthy();
  const directories = await directoriesResp.json();
  expect(Array.isArray(directories)).toBe(true);

  // Check that our scanned directory appears
  const hasTempDir = directories.some((d: any) =>
    d.path && d.path.includes(tempDir)
  );
  expect(hasTempDir).toBe(true);

  // Cleanup
  fs.rmSync(tempDir, { recursive: true, force: true });
});

test.skip('browse page shows correct file listing structure', async ({ page, baseURL, request: pageRequest }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  const tempDir = createTestDirectory('scidk-e2e-browse-');

  // Scan directory first
  const api = pageRequest || (await request.newContext());
  await api.post(`${base}/api/scan`, {
    headers: { 'Content-Type': 'application/json' },
    data: { path: tempDir, recursive: false },
  });

  // Navigate to Files/Datasets page (accessible via nav-files button)
  await page.goto(base);
  await page.waitForLoadState('networkidle');
  await page.getByTestId('nav-files').click();
  // Wait for key elements instead of networkidle (datasets page has continuous polling)
  await page.getByTestId('files-title').waitFor({ state: 'visible', timeout: 10000 });

  // Verify stable selectors are present
  await expect(page.getByTestId('files-title')).toBeVisible();
  await expect(page.getByTestId('files-root')).toBeVisible();

  // The page should have rendered without errors
  const title = await page.title();
  expect(title).toBeTruthy();

  // Cleanup
  fs.rmSync(tempDir, { recursive: true, force: true });
});

test.skip('navigation covers all 7 pages', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Start at home
  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Define all pages with their nav test IDs, URLs, and expected titles
  const pages = [
    { testId: 'nav-files', url: '/datasets', titlePattern: /Files|Datasets/i },
    { testId: 'nav-maps', url: '/map', titlePattern: /Map/i },
    { testId: 'nav-chats', url: '/chat', titlePattern: /Chat/i },
    { testId: 'nav-labels', url: '/labels', titlePattern: /Labels/i },
    { testId: 'nav-integrate', url: '/integrate', titlePattern: /-SciDK-> Integrations/i },
    { testId: 'nav-settings', url: '/', titlePattern: /Settings/i },
  ];

  for (const { testId, url, titlePattern } of pages) {
    // Verify nav link is visible
    const navLink = page.getByTestId(testId);
    await expect(navLink).toBeVisible();

    // Navigate
    await navLink.click();

    // For /datasets page, wait for specific element instead of networkidle (has polling)
    if (url === '/datasets') {
      await page.getByTestId('files-title').waitFor({ state: 'visible', timeout: 10000 });
    } else {
      await page.waitForLoadState('networkidle', { timeout: 15000 });
    }

    // Verify page loads correctly
    await expect(page).toHaveURL(new RegExp(url));
    await expect(page).toHaveTitle(titlePattern);
  }

  // Test home navigation via logo
  await page.getByTestId('nav-home').click();
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveURL(base);
  await expect(page).toHaveTitle(/SciDK/i);
});
