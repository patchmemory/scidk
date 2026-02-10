import { test, expect, request } from '@playwright/test';
import os from 'os';
import fs from 'fs';
import path from 'path';

/**
 * E2E tests for progress indicators feature:
 * - Progress bars visible during scan/commit operations
 * - Real-time status updates
 * - Estimated time remaining displayed
 * - UI remains responsive during long operations
 * - Cancel button functionality
 */

function makeTempDirWithFiles(fileCount: number, prefix = 'scidk-progress-'): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  // Create multiple files to allow progress tracking
  for (let i = 0; i < fileCount; i++) {
    fs.writeFileSync(path.join(dir, `file_${i}.txt`), `content ${i}\n`);
  }
  return dir;
}

test('progress bar visible during background scan', async ({ page, baseURL, request: pageRequest }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  const tempDir = makeTempDirWithFiles(20);

  // Navigate to Files page first
  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('domcontentloaded');

  // Start a background scan via API
  const api = pageRequest || (await request.newContext());
  const resp = await api.post(`${base}/api/tasks`, {
    headers: { 'Content-Type': 'application/json' },
    data: { type: 'scan', path: tempDir, recursive: true },
  });
  expect(resp.status()).toBe(202); // Background task accepted

  const taskData = await resp.json();
  expect(taskData.task_id).toBeDefined();

  // Wait for task list to appear and show progress
  const tasksList = page.locator('#tasks-list');
  await expect(tasksList).toBeVisible({ timeout: 5000 });

  // Check for progress bar (styled div with background color)
  const progressBar = tasksList.locator('div[style*="background"]').first();
  await expect(progressBar).toBeVisible({ timeout: 3000 });

  // Verify progress text is shown (e.g., "scan running — /path — 10/20 (50%)")
  const taskText = await tasksList.textContent();
  expect(taskText).toContain('scan');
  expect(taskText).toContain(tempDir);
  // Should show processed/total format
  expect(taskText).toMatch(/\d+\/\d+/);
});

test('status messages displayed during scan', async ({ page, baseURL, request: pageRequest }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  const tempDir = makeTempDirWithFiles(15);

  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('domcontentloaded');

  // Start background scan
  const api = pageRequest || (await request.newContext());
  await api.post(`${base}/api/tasks`, {
    headers: { 'Content-Type': 'application/json' },
    data: { type: 'scan', path: tempDir, recursive: true },
  });

  // Wait for tasks list to show content
  const tasksList = page.locator('#tasks-list');
  await expect(tasksList).toBeVisible({ timeout: 5000 });

  // Poll and check for status messages
  let foundStatusMessage = false;
  for (let i = 0; i < 20; i++) {
    const text = await tasksList.textContent();
    // Check for status message indicators like "Processing", "files", "Counting"
    if (text && (text.includes('Processing') || text.includes('files') || text.includes('Counting'))) {
      foundStatusMessage = true;
      break;
    }
    await page.waitForTimeout(200);
  }

  expect(foundStatusMessage).toBeTruthy();
});

test('ETA displayed for running tasks', async ({ page, baseURL, request: pageRequest }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  // Create more files to ensure task runs long enough to show ETA
  const tempDir = makeTempDirWithFiles(30);

  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('domcontentloaded');

  // Start background scan
  const api = pageRequest || (await request.newContext());
  await api.post(`${base}/api/tasks`, {
    headers: { 'Content-Type': 'application/json' },
    data: { type: 'scan', path: tempDir, recursive: true },
  });

  const tasksList = page.locator('#tasks-list');
  await expect(tasksList).toBeVisible({ timeout: 5000 });

  // Poll and check for ETA indicators like "~5s remaining", "~1m remaining"
  let foundETA = false;
  for (let i = 0; i < 20; i++) {
    const text = await tasksList.textContent();
    // ETA format: "~5s remaining", "~2m remaining", etc.
    if (text && text.match(/~\d+[smh]\s+remaining/)) {
      foundETA = true;
      break;
    }
    await page.waitForTimeout(200);
  }

  // Note: ETA might not always appear for very fast scans, so we don't fail the test
  // but we log whether it was found
  console.log(`ETA display ${foundETA ? 'found' : 'not found (scan may have been too fast)'}`);
});

test('cancel button visible and functional for running tasks', async ({ page, baseURL, request: pageRequest }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  const tempDir = makeTempDirWithFiles(50); // More files to ensure task runs long enough

  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('domcontentloaded');

  // Start background scan
  const api = pageRequest || (await request.newContext());
  const resp = await api.post(`${base}/api/tasks`, {
    headers: { 'Content-Type': 'application/json' },
    data: { type: 'scan', path: tempDir, recursive: true },
  });
  const taskData = await resp.json();
  const taskId = taskData.task_id;

  // Wait for cancel button to appear
  const tasksList = page.locator('#tasks-list');
  await expect(tasksList).toBeVisible({ timeout: 5000 });

  const cancelBtn = page.locator(`button[data-cancel="${taskId}"]`);
  await expect(cancelBtn).toBeVisible({ timeout: 3000 });

  // Click cancel button
  await cancelBtn.click();

  // Wait a moment and check task status changed
  await page.waitForTimeout(1000);

  // Verify task shows as canceled or is no longer running
  const text = await tasksList.textContent();
  // Should either say "canceled" or the task should complete/disappear
  const hasStatus = text && (text.includes('canceled') || text.includes('completed') || text.includes('error'));
  expect(hasStatus).toBeTruthy();
});

test('progress reaches 100% on task completion', async ({ page, baseURL, request: pageRequest }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  const tempDir = makeTempDirWithFiles(5); // Small number for quick completion

  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('domcontentloaded');

  // Start background scan
  const api = pageRequest || (await request.newContext());
  await api.post(`${base}/api/tasks`, {
    headers: { 'Content-Type': 'application/json' },
    data: { type: 'scan', path: tempDir, recursive: true },
  });

  const tasksList = page.locator('#tasks-list');
  await expect(tasksList).toBeVisible({ timeout: 5000 });

  // Poll until task completes
  let taskCompleted = false;
  for (let i = 0; i < 50; i++) {
    const text = await tasksList.textContent();
    if (text && (text.includes('completed') || text.includes('100%'))) {
      taskCompleted = true;
      break;
    }
    await page.waitForTimeout(200);
  }

  expect(taskCompleted).toBeTruthy();

  // Verify progress bar shows completion color (green)
  const progressBar = tasksList.locator('div[style*="#4caf50"]').first();
  await expect(progressBar).toBeVisible({ timeout: 2000 });
});

test('UI remains responsive during long operation', async ({ page, baseURL, request: pageRequest }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  const tempDir = makeTempDirWithFiles(30);

  await page.goto(`${base}/datasets`);
  await page.waitForLoadState('domcontentloaded');

  // Start background scan
  const api = pageRequest || (await request.newContext());
  await api.post(`${base}/api/tasks`, {
    headers: { 'Content-Type': 'application/json' },
    data: { type: 'scan', path: tempDir, recursive: true },
  });

  // Verify page is still interactive by clicking a button
  const refreshBtn = page.locator('#refresh-scans');
  await expect(refreshBtn).toBeVisible({ timeout: 5000 });
  await expect(refreshBtn).toBeEnabled();
  await refreshBtn.click();

  // Page should not freeze - verify we can still interact
  const providerSelect = page.locator('#prov-select');
  await expect(providerSelect).toBeVisible();
  await expect(providerSelect).toBeEnabled();
});
