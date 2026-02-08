import { test, expect } from '@playwright/test';

// TODO: Update tests after settings modularization (task:ui/settings/modularization)
// Table formats section now in settings/_integrations.html

test.describe('Settings - Table Format Registry', () => {
  test.beforeEach(async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/#integrations`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForSelector('[data-testid="table-format-name"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(200); // Small delay for JS initialization
  });

  test('should display table format form @smoke', async ({ page }) => {
    // Check all form fields are present
    await expect(page.locator('[data-testid="table-format-name"]')).toBeVisible();
    await expect(page.locator('[data-testid="table-format-file-type"]')).toBeVisible();
    await expect(page.locator('[data-testid="table-format-delimiter"]')).toBeVisible();
    await expect(page.locator('[data-testid="table-format-encoding"]')).toBeVisible();
    await expect(page.locator('[data-testid="table-format-target-label"]')).toBeVisible();
    await expect(page.locator('[data-testid="table-format-has-header"]')).toBeVisible();
    await expect(page.locator('[data-testid="table-format-description"]')).toBeVisible();
    await expect(page.locator('[data-testid="btn-save-table-format"]')).toBeVisible();
  });

  test('should display preprogrammed formats @smoke', async ({ page }) => {
    // Check that preprogrammed formats are listed
    const formatsList = page.locator('#table-formats-list');

    // Should show at least the preprogrammed formats
    await expect(formatsList).toContainText('CSV (Standard)');
    await expect(formatsList).toContainText('TSV (Standard)');
    await expect(formatsList).toContainText('Excel (Standard)');
    await expect(formatsList).toContainText('Parquet (Standard)');

    // Preprogrammed formats should be marked as read-only
    await expect(formatsList).toContainText('Preprogrammed');
  });

  test('should create a new custom format @smoke', async ({ page }) => {
    const uniqueName = `Test Custom CSV ${Date.now()}`;
    // Fill in format details
    await expect(page.locator('[data-testid="table-format-name"]')).toBeVisible();
    await page.fill('[data-testid="table-format-name"]', uniqueName);
    await page.selectOption('[data-testid="table-format-file-type"]', 'csv');
    await page.fill('[data-testid="table-format-delimiter"]', ';');
    await page.selectOption('[data-testid="table-format-encoding"]', 'utf-8');
    await page.fill('[data-testid="table-format-description"]', 'Test semicolon-separated format');

    // Save format
    await expect(page.locator('[data-testid="btn-save-table-format"]')).toBeVisible();
    await page.click('[data-testid="btn-save-table-format"]');

    // Wait for format to appear in list (more reliable than message)
    await expect(page.locator('#table-formats-list')).toContainText(uniqueName, { timeout: 5000 });
    await expect(page.locator('#table-formats-list')).toContainText(';');
  });

  test('should validate required fields @smoke', async ({ page }) => {
    // Try to save without filling required fields
    await page.click('[data-testid="btn-save-table-format"]');

    // Should show error message
    await expect(page.locator('#table-format-message')).toContainText('Name is required');
  });

  test('should update delimiter based on file type', async ({ page }) => {
    // Select CSV
    await page.selectOption('[data-testid="table-format-file-type"]', 'csv');
    await expect(page.locator('[data-testid="table-format-delimiter"]')).toHaveValue(',');

    // Select TSV
    await page.selectOption('[data-testid="table-format-file-type"]', 'tsv');
    await expect(page.locator('[data-testid="table-format-delimiter"]')).toHaveValue('\t');

    // Select Excel - delimiter should be disabled
    await page.selectOption('[data-testid="table-format-file-type"]', 'excel');
    await expect(page.locator('[data-testid="table-format-delimiter"]')).toBeDisabled();
  });

  test('should delete custom format', async ({ page }) => {
    const uniqueName = `Format To Delete ${Date.now()}`;
    // First create a format
    await page.fill('[data-testid="table-format-name"]', uniqueName);
    await page.selectOption('[data-testid="table-format-file-type"]', 'csv');
    await page.click('[data-testid="btn-save-table-format"]');
    await page.waitForTimeout(500);
    await page.waitForSelector(`#table-formats-list:has-text("${uniqueName}")`);

    // Find the row containing our format and click its delete button
    const formatRow = page.locator(`#table-formats-list tr:has-text("${uniqueName}")`);
    const deleteButton = formatRow.locator('button:has-text("Delete")');

    // Set up dialog handler before clicking
    page.once('dialog', dialog => dialog.accept());
    await deleteButton.click();

    // Wait a moment for deletion to complete
    await page.waitForTimeout(1500);

    // Verify format is removed from list
    await expect(page.locator('#table-formats-list')).not.toContainText(uniqueName);
  });

  test('should not allow deletion of preprogrammed formats', async ({ page }) => {
    const formatsList = page.locator('#table-formats-list');

    // Check that preprogrammed formats don't have delete buttons
    const preprogrammedRow = page.locator('#table-formats-list tr:has-text("CSV (Standard)")');
    await expect(preprogrammedRow).toContainText('Read-only');

    // Should not have Edit or Delete buttons for preprogrammed formats
    const deleteButtons = preprogrammedRow.locator('button:has-text("Delete")');
    await expect(deleteButtons).toHaveCount(0);
  });

  test('should edit custom format', async ({ page }) => {
    const originalName = `Original Format ${Date.now()}`;
    const updatedName = `Updated Format ${Date.now()}`;
    // First create a format
    await page.fill('[data-testid="table-format-name"]', originalName);
    await page.selectOption('[data-testid="table-format-file-type"]', 'csv');
    await page.fill('[data-testid="table-format-delimiter"]', ',');
    await page.click('[data-testid="btn-save-table-format"]');
    await page.waitForTimeout(500);
    await page.waitForSelector(`#table-formats-list:has-text("${originalName}")`);

    // Find the row containing our format and click its edit button
    const formatRow = page.locator(`#table-formats-list tr:has-text("${originalName}")`);
    const editButton = formatRow.locator('button:has-text("Edit")');
    await editButton.click();
    await page.waitForTimeout(300);

    // Wait for form to populate
    await expect(page.locator('[data-testid="table-format-name"]')).toHaveValue(originalName);
    await expect(page.locator('[data-testid="btn-save-table-format"]')).toContainText('Update Format');

    // Edit the name
    await page.fill('[data-testid="table-format-name"]', updatedName);
    await page.fill('[data-testid="table-format-delimiter"]', ';');

    // Save changes
    await page.click('[data-testid="btn-save-table-format"]');
    await page.waitForTimeout(500);

    // Verify changes appear in list (more reliable than message)
    await expect(page.locator('#table-formats-list')).toContainText(updatedName, { timeout: 5000 });
    await expect(page.locator('#table-formats-list')).toContainText(';');
  });

  test('should show cancel button when editing', async ({ page }) => {
    // Create a format first
    await page.fill('[data-testid="table-format-name"]', 'Edit Test');
    await page.click('[data-testid="btn-save-table-format"]');
    await page.waitForSelector('#table-formats-list:has-text("Edit Test")');

    // Click edit
    await page.locator('#table-formats-list button:has-text("Edit")').first().click();

    // Cancel button should now be visible
    await expect(page.locator('[data-testid="btn-cancel-table-format"]')).toBeVisible();

    // Click cancel
    await page.click('[data-testid="btn-cancel-table-format"]');

    // Form should be reset
    await expect(page.locator('[data-testid="table-format-name"]')).toHaveValue('');
    await expect(page.locator('[data-testid="btn-save-table-format"]')).toContainText('Save Format');
    await expect(page.locator('[data-testid="btn-cancel-table-format"]')).not.toBeVisible();
  });
});
