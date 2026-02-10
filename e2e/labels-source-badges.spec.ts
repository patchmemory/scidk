import { test, expect } from '@playwright/test';

/**
 * E2E Tests for Labels Page Source Badges
 *
 * Tests the display of source badges (plugin, manual, system) on the Labels page
 * to indicate where each label originates from.
 */

test.describe('Labels Source Badges', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to labels page
    await page.goto('/labels');
    await page.waitForLoadState('networkidle');
  });

  test('should display source badges for all labels', async ({ page }) => {
    // Wait for labels to load
    await page.waitForSelector('[data-testid="label-item"]', { timeout: 5000 });

    // Count label items
    const labelItems = page.locator('[data-testid="label-item"]');
    const labelCount = await labelItems.count();
    expect(labelCount).toBeGreaterThan(0);

    // Count source badges
    const sourceBadges = page.locator('.source-badge');
    const badgeCount = await sourceBadges.count();

    // Each label should have exactly one badge
    expect(badgeCount).toBe(labelCount);
  });

  test('should display correct badge types with icons', async ({ page }) => {
    // Create test labels with different source types
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
        source_id: 'test_plugin_instance'
      }
    });

    // Reload page to see new labels
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Check for badge types
    const manualBadges = page.locator('.source-badge.manual');
    const systemBadges = page.locator('.source-badge.system');
    const pluginBadges = page.locator('.source-badge.plugin');

    // Verify each type exists
    await expect(manualBadges.first()).toBeVisible();
    await expect(systemBadges.first()).toBeVisible();
    await expect(pluginBadges.first()).toBeVisible();

    // Check for emoji icons in the HTML
    const pageContent = await page.content();
    expect(pageContent).toContain('✏️'); // Manual icon
    expect(pageContent).toContain('🔧'); // System icon
    expect(pageContent).toContain('📦'); // Plugin icon
  });

  test('should show plugin instance name in badge', async ({ page }) => {
    // Create a plugin-sourced label
    await page.request.post('/api/labels', {
      data: {
        name: 'PluginEquipmentLabel',
        properties: [],
        relationships: [],
        source_type: 'plugin_instance',
        source_id: 'ilab_equipment_2024'
      }
    });

    // Reload page
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Find the plugin badge
    const pluginBadge = page.locator('.source-badge.plugin').filter({ hasText: 'Plugin:' });
    await expect(pluginBadge.first()).toBeVisible();

    // Badge should contain "Plugin:" text
    const badgeText = await pluginBadge.first().textContent();
    expect(badgeText).toContain('Plugin:');
    expect(badgeText).toContain('ilab_equipment_2024');
  });

  test('should have hover tooltips with full source info', async ({ page }) => {
    // Create a test label
    await page.request.post('/api/labels', {
      data: {
        name: 'TestTooltipLabel',
        properties: [],
        relationships: [],
        source_type: 'manual'
      }
    });

    // Reload page
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Find a source badge
    const sourceBadge = page.locator('.source-badge').first();
    await expect(sourceBadge).toBeVisible();

    // Check for title attribute (tooltip)
    const title = await sourceBadge.getAttribute('title');
    expect(title).toBeTruthy();
    expect(title.length).toBeGreaterThan(0);

    // Hover to trigger tooltip
    await sourceBadge.hover();
    await page.waitForTimeout(200);

    // Title should contain descriptive text
    expect(title).toMatch(/(Plugin Instance|Built-in System|Manually Created|Unknown Source)/);
  });

  test('should make plugin badges clickable', async ({ page }) => {
    // Create a plugin-sourced label
    await page.request.post('/api/labels', {
      data: {
        name: 'ClickablePluginLabel',
        properties: [],
        relationships: [],
        source_type: 'plugin_instance',
        source_id: 'test_instance_123'
      }
    });

    // Reload page
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Find the plugin badge
    const pluginBadge = page.locator('.source-badge.plugin').first();
    const badgeCount = await pluginBadge.count();

    if (badgeCount > 0) {
      // Plugin badge should have cursor pointer style
      const cursorStyle = await pluginBadge.evaluate(el => window.getComputedStyle(el).cursor);
      expect(cursorStyle).toBe('pointer');

      // Click the plugin badge
      await pluginBadge.click();
      await page.waitForTimeout(500);

      // Should navigate to Settings > Plugins
      expect(page.url()).toContain('/settings');
    }
  });

  test('should not make manual and system badges clickable', async ({ page }) => {
    // Manual badges should not be clickable
    const manualBadge = page.locator('.source-badge.manual').first();
    const manualCount = await manualBadge.count();

    if (manualCount > 0) {
      const onclick = await manualBadge.getAttribute('onclick');
      expect(onclick).toBeNull();
    }

    // System badges should not be clickable
    const systemBadge = page.locator('.source-badge.system').first();
    const systemCount = await systemBadge.count();

    if (systemCount > 0) {
      const onclick = await systemBadge.getAttribute('onclick');
      expect(onclick).toBeNull();
    }
  });

  test('should have correct badge colors', async ({ page }) => {
    // Create labels of each type
    await page.request.post('/api/labels', {
      data: { name: 'ColorTestManual', properties: [], relationships: [], source_type: 'manual' }
    });
    await page.request.post('/api/labels', {
      data: { name: 'ColorTestSystem', properties: [], relationships: [], source_type: 'system' }
    });
    await page.request.post('/api/labels', {
      data: { name: 'ColorTestPlugin', properties: [], relationships: [], source_type: 'plugin_instance', source_id: 'test' }
    });

    // Reload page
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Check plugin badge color (blue)
    const pluginBadge = page.locator('.source-badge.plugin').first();
    if (await pluginBadge.count() > 0) {
      const bgColor = await pluginBadge.evaluate(el => window.getComputedStyle(el).backgroundColor);
      // Should be some shade of blue (#e3f2fd)
      expect(bgColor).toMatch(/rgb\(227, 242, 253\)/); // #e3f2fd in RGB
    }

    // Check system badge color (green)
    const systemBadge = page.locator('.source-badge.system').first();
    if (await systemBadge.count() > 0) {
      const bgColor = await systemBadge.evaluate(el => window.getComputedStyle(el).backgroundColor);
      // Should be some shade of green (#e8f5e9)
      expect(bgColor).toMatch(/rgb\(232, 245, 233\)/); // #e8f5e9 in RGB
    }

    // Check manual badge color (gray)
    const manualBadge = page.locator('.source-badge.manual').first();
    if (await manualBadge.count() > 0) {
      const bgColor = await manualBadge.evaluate(el => window.getComputedStyle(el).backgroundColor);
      // Should be some shade of gray (#f5f5f5)
      expect(bgColor).toMatch(/rgb\(245, 245, 245\)/); // #f5f5f5 in RGB
    }
  });

  test('should display badges alongside label names', async ({ page }) => {
    // Create a test label
    await page.request.post('/api/labels', {
      data: {
        name: 'LayoutTestLabel',
        properties: [],
        relationships: [],
        source_type: 'manual'
      }
    });

    // Reload page
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Find the label item
    const labelItem = page.locator('[data-testid="label-item"]').filter({ hasText: 'LayoutTestLabel' });
    await expect(labelItem).toBeVisible();

    // Check that label-header div exists (contains both name and badge)
    const labelHeader = labelItem.locator('.label-header');
    await expect(labelHeader).toBeVisible();

    // Both the label name and badge should be in the header
    await expect(labelHeader.locator('strong')).toHaveText('LayoutTestLabel');
    await expect(labelHeader.locator('.source-badge')).toBeVisible();
  });

  test('should handle unknown source types gracefully', async ({ page }) => {
    // Create a label with unknown source type (via direct API manipulation)
    await page.request.post('/api/labels', {
      data: {
        name: 'UnknownSourceLabel',
        properties: [],
        relationships: [],
        source_type: 'unknown_type'
      }
    });

    // Reload page
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Should still display a badge (unknown type)
    const unknownBadge = page.locator('.source-badge.unknown');
    const unknownCount = await unknownBadge.count();

    if (unknownCount > 0) {
      await expect(unknownBadge.first()).toBeVisible();
      // Should have question mark icon
      const badgeText = await unknownBadge.first().textContent();
      expect(badgeText).toContain('❓');
    }
  });

  test('should update badges when label source changes', async ({ page }) => {
    // Create a manual label
    await page.request.post('/api/labels', {
      data: {
        name: 'ChangingSourceLabel',
        properties: [],
        relationships: [],
        source_type: 'manual'
      }
    });

    // Reload and verify manual badge
    await page.reload();
    await page.waitForLoadState('networkidle');

    let badge = page.locator('[data-testid="label-item"]')
      .filter({ hasText: 'ChangingSourceLabel' })
      .locator('.source-badge');
    await expect(badge).toHaveClass(/manual/);

    // Update label to system source
    await page.request.post('/api/labels', {
      data: {
        name: 'ChangingSourceLabel',
        properties: [],
        relationships: [],
        source_type: 'system'
      }
    });

    // Reload and verify system badge
    await page.reload();
    await page.waitForLoadState('networkidle');

    badge = page.locator('[data-testid="label-item"]')
      .filter({ hasText: 'ChangingSourceLabel' })
      .locator('.source-badge');
    await expect(badge).toHaveClass(/system/);
  });
});
