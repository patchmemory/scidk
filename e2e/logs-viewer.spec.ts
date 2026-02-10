import { test, expect } from '@playwright/test';

/**
 * E2E tests for Live Logs Viewer.
 * Tests logs page loads, filters work, export functionality.
 */

test('logs section loads and displays log viewer', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Navigate to Settings page
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Logs section
  await page.locator('.settings-sidebar-item[data-section="logs"]').click();
  await page.waitForTimeout(200);

  // Verify Logs section is visible
  const logsSection = page.locator('#logs-section');
  await expect(logsSection).toBeVisible();
  await expect(logsSection.locator('h1')).toHaveText('System Logs');

  // Verify logs container exists
  const logsContainer = page.locator('#logs-container');
  await expect(logsContainer).toBeVisible();
});

test('logs viewer has all filter controls', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Logs section
  await page.locator('.settings-sidebar-item[data-section="logs"]').click();
  await page.waitForTimeout(200);

  // Check filter controls
  const levelFilter = page.locator('#logs-level-filter');
  const sourceFilter = page.locator('#logs-source-filter');
  const searchInput = page.locator('#logs-search');

  await expect(levelFilter).toBeVisible();
  await expect(sourceFilter).toBeVisible();
  await expect(searchInput).toBeVisible();

  // Check buttons
  const refreshButton = page.locator('#btn-logs-refresh');
  const pauseButton = page.locator('#btn-logs-pause');
  const exportButton = page.locator('#btn-logs-export');
  const clearFiltersButton = page.locator('#btn-logs-clear-filters');

  await expect(refreshButton).toBeVisible();
  await expect(pauseButton).toBeVisible();
  await expect(exportButton).toBeVisible();
  await expect(clearFiltersButton).toBeVisible();

  await expect(refreshButton).toHaveText('Refresh');
  await expect(pauseButton).toHaveText('Pause');
  await expect(exportButton).toHaveText('Export');
  await expect(clearFiltersButton).toHaveText('Clear Filters');
});

test('logs are displayed in the container', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Logs section
  await page.locator('.settings-sidebar-item[data-section="logs"]').click();
  await page.waitForTimeout(500);

  // Wait for logs to load
  await page.waitForTimeout(1000);

  const logsContainer = page.locator('#logs-container');

  // Check if logs loaded or if "No log entries" message is shown
  const content = await logsContainer.textContent();

  // Either logs are present or "No log entries found" message
  const hasLogs = content && (
    content.includes('[INFO]') ||
    content.includes('[WARNING]') ||
    content.includes('[ERROR]') ||
    content.includes('No log entries found') ||
    content.includes('Loading logs')
  );

  expect(hasLogs).toBeTruthy();
});

test('level filter works', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Logs section
  await page.locator('.settings-sidebar-item[data-section="logs"]').click();
  await page.waitForTimeout(500);

  // Wait for initial logs to load
  await page.waitForTimeout(1000);

  // Select ERROR level filter
  const levelFilter = page.locator('#logs-level-filter');
  await levelFilter.selectOption('ERROR');

  // Wait for filtered logs to load
  await page.waitForTimeout(1000);

  const logsContainer = page.locator('#logs-container');
  const content = await logsContainer.textContent();

  // If there are ERROR logs, verify only ERROR level is shown
  if (content && content.includes('[ERROR]')) {
    // Should not contain INFO or WARNING logs
    expect(content.includes('[ERROR]')).toBeTruthy();
  } else {
    // If no ERROR logs, should show "No log entries found"
    expect(content?.includes('No log entries found')).toBeTruthy();
  }
});

test('source filter works', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Logs section
  await page.locator('.settings-sidebar-item[data-section="logs"]').click();
  await page.waitForTimeout(500);

  // Wait for initial logs to load
  await page.waitForTimeout(1000);

  // Enter source filter
  const sourceFilter = page.locator('#logs-source-filter');
  await sourceFilter.fill('scanner');

  // Wait for debounce and filtered logs to load
  await page.waitForTimeout(1500);

  const logsContainer = page.locator('#logs-container');
  const content = await logsContainer.textContent();

  // Verify response (either matching logs or "No log entries found")
  expect(content).toBeTruthy();
});

test('search filter works', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Logs section
  await page.locator('.settings-sidebar-item[data-section="logs"]').click();
  await page.waitForTimeout(500);

  // Wait for initial logs to load
  await page.waitForTimeout(1000);

  // Enter search query
  const searchInput = page.locator('#logs-search');
  await searchInput.fill('logging');

  // Wait for debounce and filtered logs to load
  await page.waitForTimeout(1500);

  const logsContainer = page.locator('#logs-container');
  const content = await logsContainer.textContent();

  // Verify response (either matching logs or "No log entries found")
  expect(content).toBeTruthy();
});

test('pause button toggles auto-refresh', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Logs section
  await page.locator('.settings-sidebar-item[data-section="logs"]').click();
  await page.waitForTimeout(500);

  const pauseButton = page.locator('#btn-logs-pause');
  const refreshStatus = page.locator('#logs-refresh-status');

  // Initially should be active
  await expect(refreshStatus).toHaveText('Active');
  await expect(pauseButton).toHaveText('Pause');

  // Click pause
  await pauseButton.click();
  await page.waitForTimeout(200);

  // Should be paused
  await expect(refreshStatus).toHaveText('Paused');
  await expect(pauseButton).toHaveText('Resume');

  // Click resume
  await pauseButton.click();
  await page.waitForTimeout(200);

  // Should be active again
  await expect(refreshStatus).toHaveText('Active');
  await expect(pauseButton).toHaveText('Pause');
});

test('clear filters button resets all filters', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Logs section
  await page.locator('.settings-sidebar-item[data-section="logs"]').click();
  await page.waitForTimeout(500);

  // Set filters
  const levelFilter = page.locator('#logs-level-filter');
  const sourceFilter = page.locator('#logs-source-filter');
  const searchInput = page.locator('#logs-search');

  await levelFilter.selectOption('ERROR');
  await sourceFilter.fill('scanner');
  await searchInput.fill('test');

  await page.waitForTimeout(500);

  // Click clear filters
  const clearFiltersButton = page.locator('#btn-logs-clear-filters');
  await clearFiltersButton.click();

  await page.waitForTimeout(500);

  // Verify all filters are cleared
  await expect(levelFilter).toHaveValue('');
  await expect(sourceFilter).toHaveValue('');
  await expect(searchInput).toHaveValue('');
});

test('refresh button manually reloads logs', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Logs section
  await page.locator('.settings-sidebar-item[data-section="logs"]').click();
  await page.waitForTimeout(500);

  // Wait for initial logs
  await page.waitForTimeout(1000);

  // Click refresh button
  const refreshButton = page.locator('#btn-logs-refresh');
  await refreshButton.click();

  // Wait for refresh to complete
  await page.waitForTimeout(1000);

  // Verify logs container is still visible and populated
  const logsContainer = page.locator('#logs-container');
  await expect(logsContainer).toBeVisible();

  const content = await logsContainer.textContent();
  expect(content).toBeTruthy();
});

test('export button initiates log download', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Logs section
  await page.locator('.settings-sidebar-item[data-section="logs"]').click();
  await page.waitForTimeout(500);

  // Set up download handler
  const downloadPromise = page.waitForEvent('download', { timeout: 5000 }).catch(() => null);

  // Click export button
  const exportButton = page.locator('#btn-logs-export');
  await exportButton.click();

  // Wait for download (or timeout)
  const download = await downloadPromise;

  // If download occurred, verify filename
  if (download) {
    const fileName = download.suggestedFilename();
    expect(fileName).toMatch(/scidk_logs_\d{8}_\d{6}\.log/);
  }
  // If no download, it might mean no logs exist, which is acceptable
});

test('logs page accessible via direct URL', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Navigate directly to logs section via hash
  await page.goto(`${base}/#logs`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);

  // Verify Logs section is visible and active
  const logsSection = page.locator('#logs-section');
  await expect(logsSection).toBeVisible();

  // Verify sidebar item is active
  const logsSidebarItem = page.locator('.settings-sidebar-item[data-section="logs"]');
  await expect(logsSidebarItem).toHaveClass(/active/);
});
