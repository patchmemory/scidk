import { test, expect } from '@playwright/test';

test.describe('Settings - API Endpoints', () => {
  test.beforeEach(async ({ page, baseURL }) => {
    // Clean up test endpoints before each test
    const response = await fetch(`${baseURL}/api/admin/cleanup-test-endpoints`, { method: 'POST' });
    await response.json(); // Wait for cleanup to complete

    await page.goto(`${baseURL}/#integrations`);
    await page.waitForLoadState('domcontentloaded'); // Wait for DOM to be ready
    await page.waitForSelector('[data-testid="api-endpoint-name"]');
    await page.waitForLoadState('networkidle'); // Then wait for all API calls to complete
    await page.waitForTimeout(200); // Small delay for JS initialization
  });

  test.afterEach(async ({ baseURL }) => {
    // Clean up test endpoints after each test
    await fetch(`${baseURL}/api/admin/cleanup-test-endpoints`, { method: 'POST' });
  });

  test('should display API endpoint form @smoke', async ({ page }) => {
    // Check all form fields are present
    await expect(page.locator('[data-testid="api-endpoint-name"]')).toBeVisible();
    await expect(page.locator('[data-testid="api-endpoint-url"]')).toBeVisible();
    await expect(page.locator('[data-testid="api-endpoint-auth-method"]')).toBeVisible();
    await expect(page.locator('[data-testid="api-endpoint-auth-value"]')).toBeVisible();
    await expect(page.locator('[data-testid="api-endpoint-json-path"]')).toBeVisible();
    await expect(page.locator('[data-testid="api-endpoint-target-label"]')).toBeVisible();
    await expect(page.locator('[data-testid="btn-test-api-endpoint"]')).toBeVisible();
    await expect(page.locator('[data-testid="btn-save-api-endpoint"]')).toBeVisible();
  });

  test.skip('should create a new API endpoint @smoke', async ({ page }) => {
    // Fill in endpoint details
    await page.fill('[data-testid="api-endpoint-name"]', 'Test Users API');
    await page.fill('[data-testid="api-endpoint-url"]', 'https://jsonplaceholder.typicode.com/users');
    await page.selectOption('[data-testid="api-endpoint-auth-method"]', 'none');
    await page.fill('[data-testid="api-endpoint-json-path"]', '$[*]');

    // Save endpoint
    await page.click('[data-testid="btn-save-api-endpoint"]');

    // Wait for success message
    await expect(page.locator('#api-endpoint-message')).toContainText('Endpoint saved!');

    // Verify endpoint appears in list
    await expect(page.locator('#api-endpoints-list')).toContainText('Test Users API');
    await expect(page.locator('#api-endpoints-list')).toContainText('jsonplaceholder.typicode.com');
  });

  test('should validate required fields @smoke', async ({ page }) => {
    // Try to save without filling required fields
    await page.click('[data-testid="btn-save-api-endpoint"]');

    // Should show error message
    await expect(page.locator('#api-endpoint-message')).toContainText('Name and URL are required');
  });

  test('should test API endpoint connection', async ({ page }) => {
    // Fill in endpoint details with a real API
    await page.fill('[data-testid="api-endpoint-name"]', 'Test JSONPlaceholder');
    await page.fill('[data-testid="api-endpoint-url"]', 'https://jsonplaceholder.typicode.com/users');
    await page.selectOption('[data-testid="api-endpoint-auth-method"]', 'none');

    // Test connection
    await page.click('[data-testid="btn-test-api-endpoint"]');

    // Wait for test result (may take a moment)
    await expect(page.locator('#api-endpoint-message')).toContainText('Connection successful', { timeout: 15000 });
  });

  test.skip('should handle bearer token auth', async ({ page }) => {
    await page.fill('[data-testid="api-endpoint-name"]', 'Secure API');
    await page.fill('[data-testid="api-endpoint-url"]', 'https://api.example.com/data');
    await page.selectOption('[data-testid="api-endpoint-auth-method"]', 'bearer');
    await page.fill('[data-testid="api-endpoint-auth-value"]', 'test_token_123');

    // Save endpoint
    await page.click('[data-testid="btn-save-api-endpoint"]');

    // Verify saved
    await expect(page.locator('#api-endpoint-message')).toContainText('Endpoint saved!');
    await expect(page.locator('#api-endpoints-list')).toContainText('Secure API');
    await expect(page.locator('#api-endpoints-list')).toContainText('bearer');
  });

  test.skip('should edit an existing endpoint', async ({ page }) => {
    // First create an endpoint
    await page.fill('[data-testid="api-endpoint-name"]', 'Original API');
    await page.fill('[data-testid="api-endpoint-url"]', 'https://api.example.com/original');
    await page.click('[data-testid="btn-save-api-endpoint"]');
    await page.waitForSelector('#api-endpoints-list:has-text("Original API")');

    // Click edit button
    await page.click('#api-endpoints-list button:has-text("Edit")');

    // Wait for form to populate
    await expect(page.locator('[data-testid="api-endpoint-name"]')).toHaveValue('Original API');
    await expect(page.locator('[data-testid="btn-save-api-endpoint"]')).toContainText('Update Endpoint');

    // Modify fields
    await page.fill('[data-testid="api-endpoint-name"]', 'Updated API');
    await page.fill('[data-testid="api-endpoint-url"]', 'https://api.example.com/updated');

    // Save changes
    await page.click('[data-testid="btn-save-api-endpoint"]');

    // Verify update
    await expect(page.locator('#api-endpoint-message')).toContainText('Endpoint updated!');
    await expect(page.locator('#api-endpoints-list')).toContainText('Updated API');
    await expect(page.locator('#api-endpoints-list')).not.toContainText('Original API');
  });

  test('should delete an endpoint @smoke', async ({ page }) => {
    // Create an endpoint
    await page.fill('[data-testid="api-endpoint-name"]', 'Delete Me API');
    await page.fill('[data-testid="api-endpoint-url"]', 'https://api.example.com/deleteme');
    await page.click('[data-testid="btn-save-api-endpoint"]');
    await page.waitForSelector('#api-endpoints-list:has-text("Delete Me API")');

    // Set up dialog handler
    page.on('dialog', dialog => dialog.accept());

    // Click delete button
    await page.click('#api-endpoints-list button:has-text("Delete")');

    // Verify deletion
    await expect(page.locator('#api-endpoint-message')).toContainText('Endpoint deleted');
    await expect(page.locator('#api-endpoints-list')).not.toContainText('Delete Me API');
  });

  test('should cancel editing', async ({ page }) => {
    // Create an endpoint
    await page.fill('[data-testid="api-endpoint-name"]', 'Cancel Test API');
    await page.fill('[data-testid="api-endpoint-url"]', 'https://api.example.com/cancel');
    await page.click('[data-testid="btn-save-api-endpoint"]');
    await page.waitForSelector('#api-endpoints-list:has-text("Cancel Test API")');

    // Start editing
    await page.click('#api-endpoints-list button:has-text("Edit")');
    await expect(page.locator('[data-testid="btn-cancel-api-endpoint"]')).toBeVisible();

    // Modify a field
    await page.fill('[data-testid="api-endpoint-name"]', 'Should Not Save');

    // Cancel
    await page.click('[data-testid="btn-cancel-api-endpoint"]');

    // Verify form is reset
    await expect(page.locator('[data-testid="api-endpoint-name"]')).toHaveValue('');
    await expect(page.locator('[data-testid="btn-save-api-endpoint"]')).toContainText('Save Endpoint');
    await expect(page.locator('[data-testid="btn-cancel-api-endpoint"]')).not.toBeVisible();

    // Verify original endpoint still exists unchanged
    await expect(page.locator('#api-endpoints-list')).toContainText('Cancel Test API');
  });

  test('should display empty state when no endpoints exist', async ({ page }) => {
    // By default, no endpoints should exist
    const listContent = await page.locator('#api-endpoints-list').textContent();

    // Should show empty message or "No endpoints" text
    expect(listContent).toMatch(/No endpoints|empty/i);
  });

  test('should populate label dropdown from existing labels', async ({ page }) => {
    const labelSelect = page.locator('[data-testid="api-endpoint-target-label"]');

    // Wait for labels to load
    await page.waitForTimeout(500);

    // Check that dropdown has at least the default option
    const options = await labelSelect.locator('option').count();
    expect(options).toBeGreaterThanOrEqual(1);

    // First option should be "-- Select Label --"
    const firstOption = await labelSelect.locator('option').first().textContent();
    expect(firstOption).toContain('Select Label');
  });
});
