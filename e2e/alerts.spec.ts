import { test, expect } from '@playwright/test';

/**
 * E2E tests for Alerts configuration page.
 * Tests SMTP configuration, alert management, and test notifications.
 */

test('alerts section loads and displays configuration', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Navigate to Settings page
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Alerts section
  await page.locator('.settings-sidebar-item[data-section="alerts"]').click();
  await page.waitForTimeout(200);

  // Verify Alerts section is visible
  const alertsSection = page.locator('#alerts-section');
  await expect(alertsSection).toBeVisible();
  await expect(alertsSection.locator('h1')).toHaveText('Alert Configuration');

  // Verify SMTP configuration section exists
  const smtpConfig = alertsSection.locator('.smtp-config');
  await expect(smtpConfig).toBeVisible();
  await expect(smtpConfig.locator('h2')).toHaveText('SMTP Configuration');
});

test('smtp configuration form has all required inputs', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Alerts section
  await page.locator('.settings-sidebar-item[data-section="alerts"]').click();
  await page.waitForTimeout(200);

  // Check SMTP form inputs
  const hostInput = page.locator('#smtp-host');
  const portInput = page.locator('#smtp-port');
  const usernameInput = page.locator('#smtp-username');
  const passwordInput = page.locator('#smtp-password');
  const fromInput = page.locator('#smtp-from');
  const tlsCheckbox = page.locator('#smtp-use-tls');

  await expect(hostInput).toBeVisible();
  await expect(portInput).toBeVisible();
  await expect(usernameInput).toBeVisible();
  await expect(passwordInput).toBeVisible();
  await expect(fromInput).toBeVisible();
  await expect(tlsCheckbox).toBeVisible();

  // Check buttons
  const saveButton = page.locator('#btn-save-smtp');
  const testButton = page.locator('#btn-test-smtp');

  await expect(saveButton).toBeVisible();
  await expect(testButton).toBeVisible();
  await expect(saveButton).toHaveText('Save SMTP Config');
  await expect(testButton).toHaveText('Test Email');
});

test('default alerts are displayed', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Alerts section
  await page.locator('.settings-sidebar-item[data-section="alerts"]').click();
  await page.waitForTimeout(200);

  // Wait for alerts to load
  await page.waitForTimeout(1000);

  // Verify default alerts exist
  const alertsList = page.locator('#alerts-list');
  await expect(alertsList).toBeVisible();

  // Check for specific default alerts
  const alertCards = page.locator('.alert-card');
  const count = await alertCards.count();
  expect(count).toBeGreaterThanOrEqual(5); // 5 default alerts

  // Verify alert names
  const alertText = await alertsList.textContent();
  expect(alertText).toContain('Import Failed');
  expect(alertText).toContain('High Discrepancies');
  expect(alertText).toContain('Backup Failed');
  expect(alertText).toContain('Neo4j Connection Lost');
  expect(alertText).toContain('Disk Space Critical');
});

test('alert enable/disable toggle works', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Alerts section
  await page.locator('.settings-sidebar-item[data-section="alerts"]').click();
  await page.waitForTimeout(200);

  // Wait for alerts to load
  await page.waitForTimeout(1000);

  // Find first alert's enable toggle
  const firstAlertCard = page.locator('.alert-card').first();
  const enableToggle = firstAlertCard.locator('input[type="checkbox"]');

  // Get initial state
  const initialState = await enableToggle.isChecked();

  // Toggle it
  await enableToggle.click();
  await page.waitForTimeout(500); // Wait for API call

  // Verify state changed
  const newState = await enableToggle.isChecked();
  expect(newState).toBe(!initialState);

  // Toggle back
  await enableToggle.click();
  await page.waitForTimeout(500);

  // Verify it's back to original state
  const finalState = await enableToggle.isChecked();
  expect(finalState).toBe(initialState);
});

test('alert recipients can be updated', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Alerts section
  await page.locator('.settings-sidebar-item[data-section="alerts"]').click();
  await page.waitForTimeout(200);

  // Wait for alerts to load
  await page.waitForTimeout(1000);

  // Find first alert
  const firstAlertCard = page.locator('.alert-card').first();
  const recipientsInput = firstAlertCard.locator('input[id^="alert-recipients-"]');
  const updateButton = firstAlertCard.locator('button:has-text("Update")');

  // Clear and enter new recipients
  await recipientsInput.clear();
  await recipientsInput.fill('test1@example.com, test2@example.com');

  // Click update
  await updateButton.click();
  await page.waitForTimeout(500);

  // Verify success message or that value persists
  const updatedValue = await recipientsInput.inputValue();
  expect(updatedValue).toContain('test1@example.com');
});

test('alert threshold can be updated for alerts with thresholds', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Alerts section
  await page.locator('.settings-sidebar-item[data-section="alerts"]').click();
  await page.waitForTimeout(200);

  // Wait for alerts to load
  await page.waitForTimeout(1000);

  // Find "High Discrepancies" alert (has threshold)
  const alertsList = page.locator('#alerts-list');
  const highDiscrepanciesCard = alertsList.locator('.alert-card:has-text("High Discrepancies")');

  // Find threshold input
  const thresholdInput = highDiscrepanciesCard.locator('input[id^="alert-threshold-"]');

  // Only test if threshold input exists (it should for High Discrepancies)
  if (await thresholdInput.isVisible()) {
    // Update threshold
    await thresholdInput.clear();
    await thresholdInput.fill('75');

    // Click update
    const updateButton = highDiscrepanciesCard.locator('button:has-text("Update")');
    await updateButton.click();
    await page.waitForTimeout(500);

    // Verify value persists
    const updatedValue = await thresholdInput.inputValue();
    expect(updatedValue).toBe('75');
  }
});

test('smtp configuration can be saved', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Alerts section
  await page.locator('.settings-sidebar-item[data-section="alerts"]').click();
  await page.waitForTimeout(200);

  // Fill SMTP form
  await page.locator('#smtp-host').fill('smtp.test.com');
  await page.locator('#smtp-port').fill('587');
  await page.locator('#smtp-username').fill('user@test.com');
  await page.locator('#smtp-from').fill('noreply@test.com');

  // Save configuration
  await page.locator('#btn-save-smtp').click();
  await page.waitForTimeout(500);

  // Verify success message
  const messageEl = page.locator('#smtp-message');
  await expect(messageEl).toBeVisible();
  const messageText = await messageEl.textContent();
  expect(messageText).toContain('successfully');
});

test('smtp test button is clickable', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Alerts section
  await page.locator('.settings-sidebar-item[data-section="alerts"]').click();
  await page.waitForTimeout(200);

  // Test button should be present and clickable (even if it fails due to no config)
  const testButton = page.locator('#btn-test-smtp');
  await expect(testButton).toBeVisible();
  await expect(testButton).toBeEnabled();

  // Click it (will likely fail without real SMTP, but should not crash)
  await testButton.click();
  await page.waitForTimeout(500);

  // Should show some message (success or error)
  const messageEl = page.locator('#smtp-message');
  await expect(messageEl).toBeVisible();
});

test('alert test buttons are present and clickable', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Alerts section
  await page.locator('.settings-sidebar-item[data-section="alerts"]').click();
  await page.waitForTimeout(200);

  // Wait for alerts to load
  await page.waitForTimeout(1000);

  // Find first alert's test button
  const firstAlertCard = page.locator('.alert-card').first();
  const testButton = firstAlertCard.locator('button:has-text("Test")');

  await expect(testButton).toBeVisible();
  await expect(testButton).toBeEnabled();

  // Note: Actually clicking test would require SMTP config and recipients
  // So we just verify the button exists
});

test('alert history section is present', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Alerts section
  await page.locator('.settings-sidebar-item[data-section="alerts"]').click();
  await page.waitForTimeout(200);

  // Find history section (details element)
  const historyDetails = page.locator('details:has-text("Alert History")');
  await expect(historyDetails).toBeVisible();

  // Expand history
  await historyDetails.locator('summary').click();
  await page.waitForTimeout(500);

  // Verify history list exists
  const historyList = page.locator('#alert-history-list');
  await expect(historyList).toBeVisible();
});

test('alerts page handles no recipients gracefully', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Alerts section
  await page.locator('.settings-sidebar-item[data-section="alerts"]').click();
  await page.waitForTimeout(200);

  // Wait for alerts to load
  await page.waitForTimeout(1000);

  // Verify alerts with no recipients show "No recipients configured"
  const alertsList = page.locator('#alerts-list');
  const alertText = await alertsList.textContent();

  // Default alerts start with no recipients
  expect(alertText).toContain('No recipients configured');
});
