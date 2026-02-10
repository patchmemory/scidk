import { test, expect } from '@playwright/test';

/**
 * E2E Tests for Integrations Label Auto-Discovery
 *
 * Tests the automatic discovery and display of labels from all sources
 * (system, manual, plugin instances) in the Integrations page dropdowns.
 */

test.describe('Integrations Label Discovery', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to integrations page
    await page.goto('/integrations');
  });

  test('should load and display available labels in dropdowns', async ({ page }) => {
    // Click "New Integration" button
    await page.click('[data-testid="new-integration-btn"]');

    // Wait for wizard to appear
    await expect(page.locator('#link-wizard')).toBeVisible();

    // Check that source label dropdown is populated
    const sourceSelect = page.locator('#source-label-select');
    await expect(sourceSelect).toBeVisible();

    // Get all options (excluding the placeholder)
    const sourceOptions = await sourceSelect.locator('option:not([value=""])').count();
    expect(sourceOptions).toBeGreaterThan(0);
  });

  test('should display source indicators (icons) in dropdowns', async ({ page }) => {
    // Create test labels with different sources via API
    await page.request.post('/api/labels', {
      data: {
        name: 'TestManualLabel',
        properties: [],
        relationships: [],
        source_type: 'manual'
      }
    });

    await page.request.post('/api/labels', {
      data: {
        name: 'TestSystemLabel',
        properties: [],
        relationships: [],
        source_type: 'system'
      }
    });

    await page.request.post('/api/labels', {
      data: {
        name: 'TestPluginLabel',
        properties: [],
        relationships: [],
        source_type: 'plugin_instance',
        source_id: 'test_instance_123'
      }
    });

    // Reload page to fetch new labels
    await page.reload();

    // Click "New Integration"
    await page.click('[data-testid="new-integration-btn"]');

    // Check source label dropdown contains icons
    const sourceSelect = page.locator('#source-label-select');
    const sourceHtml = await sourceSelect.innerHTML();

    // Verify icons are present (emojis)
    expect(sourceHtml).toContain('✏️'); // Manual
    expect(sourceHtml).toContain('🔧'); // System
    expect(sourceHtml).toContain('📦'); // Plugin

    // Verify label names are present
    expect(sourceHtml).toContain('TestManualLabel');
    expect(sourceHtml).toContain('TestSystemLabel');
    expect(sourceHtml).toContain('TestPluginLabel');
  });

  test('should display node counts in dropdowns', async ({ page }) => {
    // Create a test label
    await page.request.post('/api/labels', {
      data: {
        name: 'TestLabelWithCount',
        properties: [],
        relationships: [],
        source_type: 'manual'
      }
    });

    // Reload page
    await page.reload();

    // Click "New Integration"
    await page.click('[data-testid="new-integration-btn"]');

    // Check dropdown contains node count information
    const sourceSelect = page.locator('#source-label-select');
    const sourceHtml = await sourceSelect.innerHTML();

    // Should show either "(X nodes)" or "(empty)"
    expect(sourceHtml).toMatch(/\((\d+\s+nodes|empty)\)/);
  });

  test('should display plugin instance names for plugin-sourced labels', async ({ page }) => {
    // Create a plugin-sourced label
    await page.request.post('/api/labels', {
      data: {
        name: 'PluginEquipment',
        properties: [],
        relationships: [],
        source_type: 'plugin_instance',
        source_id: 'ilab_equipment_001'
      }
    });

    // Reload page
    await page.reload();

    // Click "New Integration"
    await page.click('[data-testid="new-integration-btn"]');

    // Check dropdown shows plugin info
    const sourceSelect = page.locator('#source-label-select');
    const sourceHtml = await sourceSelect.innerHTML();

    // Should contain "Plugin:" indicator
    expect(sourceHtml).toContain('Plugin:');
    expect(sourceHtml).toContain('PluginEquipment');
  });

  test('should allow selecting labels with 0 nodes', async ({ page }) => {
    // Create a label with no nodes
    await page.request.post('/api/labels', {
      data: {
        name: 'EmptyLabel',
        properties: [],
        relationships: [],
        source_type: 'manual'
      }
    });

    // Reload page
    await page.reload();

    // Click "New Integration"
    await page.click('[data-testid="new-integration-btn"]');

    // Select the empty label as source
    await page.selectOption('#source-label-select', 'EmptyLabel');

    // Verify selection worked
    const selectedValue = await page.locator('#source-label-select').inputValue();
    expect(selectedValue).toBe('EmptyLabel');

    // Navigate to step 2
    await page.click('#btn-next');

    // Navigate to step 3
    await page.click('#btn-next');

    // Select the empty label as target
    await page.selectOption('#target-label-select', 'EmptyLabel');

    // Verify target selection worked
    const targetValue = await page.locator('#target-label-select').inputValue();
    expect(targetValue).toBe('EmptyLabel');
  });

  test('should populate both source and target dropdowns identically', async ({ page }) => {
    // Create test labels
    await page.request.post('/api/labels', {
      data: {
        name: 'LabelA',
        properties: [],
        relationships: [],
        source_type: 'manual'
      }
    });

    await page.request.post('/api/labels', {
      data: {
        name: 'LabelB',
        properties: [],
        relationships: [],
        source_type: 'system'
      }
    });

    // Reload page
    await page.reload();

    // Click "New Integration"
    await page.click('[data-testid="new-integration-btn"]');

    // Get source dropdown options
    const sourceSelect = page.locator('#source-label-select');
    const sourceOptions = await sourceSelect.locator('option:not([value=""])').allTextContents();

    // Navigate to step 3 to see target dropdown
    await page.click('#btn-next'); // to step 2
    await page.click('#btn-next'); // to step 3

    // Get target dropdown options
    const targetSelect = page.locator('#target-label-select');
    const targetOptions = await targetSelect.locator('option:not([value=""])').allTextContents();

    // Both dropdowns should have the same options
    expect(sourceOptions.length).toBe(targetOptions.length);
    expect(sourceOptions).toEqual(targetOptions);
  });

  test('should handle API fetch errors gracefully', async ({ page }) => {
    // Block the labels API endpoint
    await page.route('/api/labels/list', route => route.abort());

    // Reload page (will fail to fetch labels)
    await page.reload();

    // Click "New Integration"
    await page.click('[data-testid="new-integration-btn"]');

    // Dropdown should still exist with just placeholder
    const sourceSelect = page.locator('#source-label-select');
    await expect(sourceSelect).toBeVisible();

    const options = await sourceSelect.locator('option').count();
    expect(options).toBe(1); // Only the placeholder option
  });

  test('should refresh labels when navigating away and back', async ({ page }) => {
    // Create initial label
    await page.request.post('/api/labels', {
      data: {
        name: 'InitialLabel',
        properties: [],
        relationships: [],
        source_type: 'manual'
      }
    });

    // Reload page
    await page.reload();

    // Click "New Integration"
    await page.click('[data-testid="new-integration-btn"]');

    // Verify InitialLabel is present
    let sourceHtml = await page.locator('#source-label-select').innerHTML();
    expect(sourceHtml).toContain('InitialLabel');

    // Navigate away to Files page
    await page.goto('/files');

    // Create another label while on different page
    await page.request.post('/api/labels', {
      data: {
        name: 'NewLabel',
        properties: [],
        relationships: [],
        source_type: 'manual'
      }
    });

    // Navigate back to Integrations
    await page.goto('/integrations');

    // Click "New Integration"
    await page.click('[data-testid="new-integration-btn"]');

    // Verify both labels are present (labels reloaded)
    sourceHtml = await page.locator('#source-label-select').innerHTML();
    expect(sourceHtml).toContain('InitialLabel');
    expect(sourceHtml).toContain('NewLabel');
  });

  test('should display correct source display text format', async ({ page }) => {
    // Create labels with different sources
    await page.request.post('/api/labels', {
      data: {
        name: 'ManualLabel',
        properties: [],
        relationships: [],
        source_type: 'manual'
      }
    });

    await page.request.post('/api/labels', {
      data: {
        name: 'SystemLabel',
        properties: [],
        relationships: [],
        source_type: 'system'
      }
    });

    await page.request.post('/api/labels', {
        data: {
        name: 'PluginLabel',
        properties: [],
        relationships: [],
        source_type: 'plugin_instance',
        source_id: 'test_plugin'
      }
    });

    // Reload page
    await page.reload();

    // Click "New Integration"
    await page.click('[data-testid="new-integration-btn"]');

    // Check source display text
    const sourceHtml = await page.locator('#source-label-select').innerHTML();

    // Manual label should show " - Manual"
    expect(sourceHtml).toContain('ManualLabel');
    expect(sourceHtml).toMatch(/ManualLabel.*Manual/);

    // System label should show " - System"
    expect(sourceHtml).toContain('SystemLabel');
    expect(sourceHtml).toMatch(/SystemLabel.*System/);

    // Plugin label should show " - Plugin:"
    expect(sourceHtml).toContain('PluginLabel');
    expect(sourceHtml).toMatch(/PluginLabel.*Plugin:/);
  });

  test('should include data attributes for source and count', async ({ page }) => {
    // Create a test label
    await page.request.post('/api/labels', {
      data: {
        name: 'DataAttributeTest',
        properties: [],
        relationships: [],
        source_type: 'manual'
      }
    });

    // Reload page
    await page.reload();

    // Click "New Integration"
    await page.click('[data-testid="new-integration-btn"]');

    // Find the option for our test label
    const option = page.locator('#source-label-select option[value="DataAttributeTest"]');

    // Verify data attributes exist
    await expect(option).toHaveAttribute('data-source');
    await expect(option).toHaveAttribute('data-count');

    // Verify data attribute values
    const source = await option.getAttribute('data-source');
    const count = await option.getAttribute('data-count');

    expect(source).toBe('manual');
    expect(count).toBeDefined();
    expect(parseInt(count)).toBeGreaterThanOrEqual(0);
  });
});
