import { test, expect } from '@playwright/test';

/**
 * E2E tests for Maps visualization modes feature.
 * Tests mode switching (Schema/Instance/Hybrid) and export functionality.
 */

test.describe('Maps Visualization Modes', () => {
  const baseURL = process.env.BASE_URL || 'http://127.0.0.1:5000';

  test.beforeEach(async ({ page }) => {
    await page.goto(`${baseURL}/map`);
    await expect(page.getByText('Visualization Mode')).toBeVisible();
  });

  test('default mode is schema', async ({ page }) => {
    // Verify schema mode is checked by default
    await expect(page.getByTestId('mode-schema')).toBeChecked();
    await expect(page.getByTestId('mode-instance')).not.toBeChecked();
    await expect(page.getByTestId('mode-hybrid')).not.toBeChecked();

    // Instance and hybrid settings should be hidden
    await expect(page.locator('#instance-settings')).not.toBeVisible();
    await expect(page.locator('#hybrid-settings')).not.toBeVisible();
  });

  test('switch to instance mode shows settings', async ({ page }) => {
    // Click instance mode radio
    await page.getByTestId('mode-instance').check();

    // Verify instance mode is selected
    await expect(page.getByTestId('mode-instance')).toBeChecked();

    // Instance settings should be visible
    await expect(page.locator('#instance-settings')).toBeVisible();
    await expect(page.locator('#node-limit')).toBeVisible();

    // Hybrid settings should be hidden
    await expect(page.locator('#hybrid-settings')).not.toBeVisible();
  });

  test('switch to hybrid mode shows settings', async ({ page }) => {
    // Click hybrid mode radio
    await page.getByTestId('mode-hybrid').check();

    // Verify hybrid mode is selected
    await expect(page.getByTestId('mode-hybrid')).toBeChecked();

    // Hybrid settings should be visible
    await expect(page.locator('#hybrid-settings')).toBeVisible();
    await expect(page.getByTestId('hybrid-label')).toBeVisible();
    await expect(page.getByTestId('hybrid-property')).toBeVisible();

    // Instance settings should be hidden
    await expect(page.locator('#instance-settings')).not.toBeVisible();
  });

  test('node limit input shows warning for large values', async ({ page }) => {
    // Switch to instance mode
    await page.getByTestId('mode-instance').check();

    // Set up dialog handler
    page.once('dialog', async (dialog) => {
      expect(dialog.message()).toContain('performance');
      expect(dialog.message()).toContain('1500');
      await dialog.accept();
    });

    // Change node limit to high value
    await page.getByTestId('node-limit').fill('1500');
    await page.getByTestId('node-limit').blur(); // Trigger change event
  });

  test('hybrid label selector populates with options', async ({ page }) => {
    // Switch to hybrid mode
    await page.getByTestId('mode-hybrid').check();

    // Verify label selector has options
    const labelSelect = page.getByTestId('hybrid-label');
    const options = await labelSelect.locator('option').count();
    expect(options).toBeGreaterThan(1); // At least placeholder + some options
  });

  test('selecting hybrid label enables property selector', async ({ page }) => {
    // Switch to hybrid mode
    await page.getByTestId('mode-hybrid').check();

    // Initially property selector should have just placeholder
    const propertySelect = page.getByTestId('hybrid-property');
    let propertyOptions = await propertySelect.locator('option').count();
    expect(propertyOptions).toBe(1); // Just "Select property..."

    // Select a label
    await page.getByTestId('hybrid-label').selectOption({ index: 1 });
    await page.waitForTimeout(300);

    // Property selector should now have options
    propertyOptions = await propertySelect.locator('option').count();
    expect(propertyOptions).toBeGreaterThan(1);
  });

  test('export PNG button is visible and clickable', async ({ page }) => {
    const exportPngBtn = page.getByTestId('export-png');
    await expect(exportPngBtn).toBeVisible();
    await expect(exportPngBtn).toBeEnabled();

    // Note: Actual download test would require graph data
    // For now just verify button is functional
  });

  test('export JSON button is visible and clickable', async ({ page }) => {
    const exportJsonBtn = page.getByTestId('export-json');
    await expect(exportJsonBtn).toBeVisible();
    await expect(exportJsonBtn).toBeEnabled();
  });

  test('export Cypher button is visible and clickable', async ({ page }) => {
    const exportCypherBtn = page.getByTestId('export-cypher');
    await expect(exportCypherBtn).toBeVisible();
    await expect(exportCypherBtn).toBeEnabled();
  });

  test('mode switching preserves other settings', async ({ page }) => {
    // Set node limit in instance mode
    await page.getByTestId('mode-instance').check();
    await page.getByTestId('node-limit').fill('750');

    // Switch to hybrid mode
    await page.getByTestId('mode-hybrid').check();
    await page.getByTestId('hybrid-label').selectOption({ index: 1 });

    // Switch back to instance mode
    await page.getByTestId('mode-instance').check();

    // Node limit should be preserved
    const nodeLimitValue = await page.getByTestId('node-limit').inputValue();
    expect(nodeLimitValue).toBe('750');
  });

  test('all three modes can be switched between', async ({ page }) => {
    // Start with schema (default)
    await expect(page.getByTestId('mode-schema')).toBeChecked();

    // Switch to instance
    await page.getByTestId('mode-instance').check();
    await expect(page.getByTestId('mode-instance')).toBeChecked();
    await expect(page.locator('#instance-settings')).toBeVisible();

    // Switch to hybrid
    await page.getByTestId('mode-hybrid').check();
    await expect(page.getByTestId('mode-hybrid')).toBeChecked();
    await expect(page.locator('#hybrid-settings')).toBeVisible();
    await expect(page.locator('#instance-settings')).not.toBeVisible();

    // Switch back to schema
    await page.getByTestId('mode-schema').check();
    await expect(page.getByTestId('mode-schema')).toBeChecked();
    await expect(page.locator('#instance-settings')).not.toBeVisible();
    await expect(page.locator('#hybrid-settings')).not.toBeVisible();
  });

  test('visualization mode section is in right panel', async ({ page }) => {
    // Verify the mode selector is in the visualization panel
    const vizPanel = page.locator('.map-controls-panel');
    await expect(vizPanel).toBeVisible();

    // Mode radios should be within this panel
    const schemaRadio = vizPanel.getByTestId('mode-schema');
    await expect(schemaRadio).toBeVisible();
  });

  test('export buttons are grouped together', async ({ page }) => {
    // All export buttons should be visible in export section
    const exportSection = page.locator('.control-group', { hasText: 'Export Graph' });
    await expect(exportSection).toBeVisible();

    await expect(exportSection.getByTestId('export-png')).toBeVisible();
    await expect(exportSection.getByTestId('export-json')).toBeVisible();
    await expect(exportSection.getByTestId('export-cypher')).toBeVisible();
  });
});

test.describe('Maps Export Functionality', () => {
  const baseURL = process.env.BASE_URL || 'http://127.0.0.1:5000';

  test.beforeEach(async ({ page }) => {
    await page.goto(`${baseURL}/map`);
  });

  test('export buttons show appropriate alert when no graph', async ({ page }) => {
    // Set up dialog handler for "no graph" alert
    page.once('dialog', async (dialog) => {
      expect(dialog.message()).toContain('No graph');
      await dialog.accept();
    });

    // Click export button (should show alert since no graph loaded)
    await page.getByTestId('export-png').click();
  });

  test('all export format buttons are present', async ({ page }) => {
    // Verify all three export formats are available
    await expect(page.getByTestId('export-png')).toContainText('PNG');
    await expect(page.getByTestId('export-json')).toContainText('JSON');
    await expect(page.getByTestId('export-cypher')).toContainText('Cypher');
  });
});
