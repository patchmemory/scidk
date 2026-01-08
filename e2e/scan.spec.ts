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

test('scan a temp directory and verify it appears on Home', async ({ page, baseURL, request: pageRequest }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  const tempDir = makeTempDirWithFile();

  // Kick off a non-recursive scan via HTTP API (synchronous in current implementation)
  const api = pageRequest || (await request.newContext());
  const resp = await api.post(`${base}/api/scan`, {
    headers: { 'Content-Type': 'application/json' },
    data: { path: tempDir, recursive: false },
  });
  expect(resp.ok()).toBeTruthy();

  // Navigate to Home and check that the scanned source is listed
  await page.goto(base);
  await page.waitForLoadState('domcontentloaded');
  await page.waitForLoadState('networkidle');

  // The Home page shows a Scanned Sources list when directories exist.
  // Assert the tempDir path appears somewhere in the page. Use getByText to avoid regex parsing of slashes.
  const occurrences = await page.getByText(tempDir, { exact: false }).count();
  expect(occurrences).toBeGreaterThan(0);
});
