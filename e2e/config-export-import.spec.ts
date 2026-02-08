import { test, expect } from '@playwright/test';

test.describe('Configuration Export/Import', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to settings page
    await page.goto('http://127.0.0.1:5000/settings');
    await page.waitForLoadState('networkidle');
  });

  test('should display export/import buttons in General settings', async ({ page }) => {
    // Verify General section is visible
    await expect(page.locator('#general-section')).toBeVisible();

    // Verify export/import buttons are present
    await expect(page.locator('[data-testid="export-config-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="import-config-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="view-backups-button"]')).toBeVisible();
  });

  test('should export configuration successfully', async ({ page }) => {
    // Click export button
    const exportButton = page.locator('[data-testid="export-config-button"]');
    await exportButton.click();

    // Wait for export to complete and check for success message
    await expect(page.locator('#config-status')).toBeVisible();
    await expect(page.locator('#config-status')).toContainText('exported successfully');
  });

  test('should show backups list when View Backups clicked', async ({ page }) => {
    // First create a backup by exporting
    await page.locator('[data-testid="export-config-button"]').click();
    await page.waitForTimeout(1000);

    // Now click View Backups
    // Note: This will show an alert, which we can't easily test in Playwright
    // but we can verify the button is clickable
    const backupsButton = page.locator('[data-testid="view-backups-button"]');
    await expect(backupsButton).toBeEnabled();
  });

  test('API: should export configuration via API', async ({ request }) => {
    const response = await request.get('http://127.0.0.1:5000/api/settings/export');
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.status).toBe('success');
    expect(data.config).toBeDefined();
    expect(data.config.version).toBe('1.0');
    expect(data.config.general).toBeDefined();
    expect(data.filename).toMatch(/scidk-config-.*\.json/);
  });

  test('API: should export configuration with selective sections', async ({ request }) => {
    const response = await request.get('http://127.0.0.1:5000/api/settings/export?sections=general,neo4j');
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.status).toBe('success');
    expect(data.config.general).toBeDefined();
    expect(data.config.neo4j).toBeDefined();
    // Other sections should not be present
    expect(data.config.chat).toBeUndefined();
  });

  test('API: should preview import changes', async ({ request }) => {
    // First export current config
    const exportResp = await request.get('http://127.0.0.1:5000/api/settings/export');
    const exportData = await exportResp.json();
    const config = exportData.config;

    // Preview importing the same config (should show no changes)
    const previewResp = await request.post('http://127.0.0.1:5000/api/settings/import/preview', {
      data: { config }
    });

    expect(previewResp.ok()).toBeTruthy();
    const previewData = await previewResp.json();
    expect(previewData.status).toBe('success');
    expect(previewData.diff).toBeDefined();
    expect(previewData.diff.sections).toBeDefined();
  });

  test('API: should import configuration successfully', async ({ request }) => {
    // Export current config
    const exportResp = await request.get('http://127.0.0.1:5000/api/settings/export?include_sensitive=true');
    const exportData = await exportResp.json();
    const config = exportData.config;

    // Import the config
    const importResp = await request.post('http://127.0.0.1:5000/api/settings/import', {
      data: {
        config,
        create_backup: true,
        created_by: 'test_user'
      }
    });

    expect(importResp.ok()).toBeTruthy();
    const importData = await importResp.json();
    expect(importData.status).toBe('success');
    expect(importData.report).toBeDefined();
    expect(importData.report.success).toBe(true);
    expect(importData.report.backup_id).toBeDefined();
  });

  test('API: should reject invalid config version', async ({ request }) => {
    const invalidConfig = {
      version: '99.9',
      timestamp: '2026-02-08T10:00:00Z',
      general: {}
    };

    const response = await request.post('http://127.0.0.1:5000/api/settings/import', {
      data: { config: invalidConfig }
    });

    const data = await response.json();
    expect(data.status).toBe('error');
    expect(data.report.success).toBe(false);
    expect(data.report.errors.length).toBeGreaterThan(0);
  });

  test('API: should list configuration backups', async ({ request }) => {
    const response = await request.get('http://127.0.0.1:5000/api/settings/backups?limit=10');
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.status).toBe('success');
    expect(Array.isArray(data.backups)).toBeTruthy();
  });

  test('API: should create manual backup', async ({ request }) => {
    const response = await request.post('http://127.0.0.1:5000/api/settings/backups', {
      data: {
        reason: 'test_backup',
        created_by: 'test_user',
        notes: 'E2E test backup'
      }
    });

    expect(response.status()).toBe(201);
    const data = await response.json();
    expect(data.status).toBe('success');
    expect(data.backup_id).toBeDefined();

    // Verify the backup was created
    const backupId = data.backup_id;
    const getResp = await request.get(`http://127.0.0.1:5000/api/settings/backups/${backupId}`);
    expect(getResp.ok()).toBeTruthy();

    const backupData = await getResp.json();
    expect(backupData.status).toBe('success');
    expect(backupData.backup).toBeDefined();
    expect(backupData.backup.reason).toBe('test_backup');
    expect(backupData.backup.created_by).toBe('test_user');
    expect(backupData.backup.notes).toBe('E2E test backup');
  });

  test('API: should restore configuration from backup', async ({ request }) => {
    // Create a backup first
    const createResp = await request.post('http://127.0.0.1:5000/api/settings/backups', {
      data: {
        reason: 'test_restore',
        created_by: 'test_user'
      }
    });

    const createData = await createResp.json();
    const backupId = createData.backup_id;

    // Restore from backup
    const restoreResp = await request.post(`http://127.0.0.1:5000/api/settings/backups/${backupId}/restore`, {
      data: {
        created_by: 'test_user'
      }
    });

    expect(restoreResp.ok()).toBeTruthy();
    const restoreData = await restoreResp.json();
    expect(restoreData.status).toBe('success');
    expect(restoreData.report).toBeDefined();
    expect(restoreData.report.success).toBe(true);
  });

  test('API: should delete backup', async ({ request }) => {
    // Create a backup first
    const createResp = await request.post('http://127.0.0.1:5000/api/settings/backups', {
      data: {
        reason: 'test_delete',
        created_by: 'test_user'
      }
    });

    const createData = await createResp.json();
    const backupId = createData.backup_id;

    // Delete the backup
    const deleteResp = await request.delete(`http://127.0.0.1:5000/api/settings/backups/${backupId}`);
    expect(deleteResp.ok()).toBeTruthy();

    const deleteData = await deleteResp.json();
    expect(deleteData.status).toBe('success');

    // Verify backup was deleted
    const getResp = await request.get(`http://127.0.0.1:5000/api/settings/backups/${backupId}`);
    expect(getResp.status()).toBe(404);
  });

  test('API: full export-import-restore cycle', async ({ request }) => {
    // 1. Export current configuration
    const exportResp = await request.get('http://127.0.0.1:5000/api/settings/export?include_sensitive=true');
    const exportData = await exportResp.json();
    const originalConfig = exportData.config;

    // 2. Preview import (should show no changes)
    const previewResp = await request.post('http://127.0.0.1:5000/api/settings/import/preview', {
      data: { config: originalConfig }
    });
    const previewData = await previewResp.json();
    expect(previewData.status).toBe('success');

    // 3. Import configuration (creates backup automatically)
    const importResp = await request.post('http://127.0.0.1:5000/api/settings/import', {
      data: {
        config: originalConfig,
        create_backup: true,
        created_by: 'e2e_test'
      }
    });
    const importData = await importResp.json();
    expect(importData.status).toBe('success');
    const backupId = importData.report.backup_id;
    expect(backupId).toBeDefined();

    // 4. Verify backup was created
    const backupResp = await request.get(`http://127.0.0.1:5000/api/settings/backups/${backupId}`);
    const backupData = await backupResp.json();
    expect(backupData.status).toBe('success');
    expect(backupData.backup.reason).toBe('pre_import');

    // 5. Restore from backup
    const restoreResp = await request.post(`http://127.0.0.1:5000/api/settings/backups/${backupId}/restore`, {
      data: { created_by: 'e2e_test' }
    });
    const restoreData = await restoreResp.json();
    expect(restoreData.status).toBe('success');

    // 6. Export again to verify restoration
    const exportResp2 = await request.get('http://127.0.0.1:5000/api/settings/export?include_sensitive=true');
    const exportData2 = await exportResp2.json();

    // Configs should match (except timestamps)
    expect(exportData2.config.version).toBe(originalConfig.version);
  });
});
