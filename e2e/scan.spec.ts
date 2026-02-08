import { test, expect, request } from '@playwright/test';
import os from 'os';
import fs from 'fs';
import path from 'path';

// Scan flow: create a small temp directory on the runner, POST /api/scan to index it,
// then verify Home lists it under Scanned Sources.

function makeTempDirWithFile(prefix = 'scidk-e2e-'): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  fs.writeFileSync(path.join(dir, 'e2e.txt'), 'hello');
  return dir;
}

test('scan a temp directory and verify it appears in Files page', async ({ page, baseURL, request: pageRequest }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  const tempDir = makeTempDirWithFile();

  // Kick off a non-recursive scan via HTTP API (synchronous in current implementation)
  const api = pageRequest || (await request.newContext());
  const resp = await api.post(`${base}/api/scan`, {
    headers: { 'Content-Type': 'application/json' },
    data: { path: tempDir, recursive: false },
  });
  expect(resp.ok()).toBeTruthy();

  // Navigate to Files page (/datasets) and check that the scanned source is listed
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('domcontentloaded');
  // Don't wait for networkidle - /datasets page may have continuous polling for tasks
  await page.waitForTimeout(2000); // Give page time to load scans dropdown

  // The Files page shows scanned sources in the "Recent scans" dropdown
  const recentScansSelect = page.locator('#recent-scans');
  await expect(recentScansSelect).toBeVisible({ timeout: 10_000 });

  // Get all options text and verify our temp directory path appears
  const selectText = await recentScansSelect.textContent();
  expect(selectText).toContain(tempDir);
});
