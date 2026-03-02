import { test, expect } from '@playwright/test';

/**
 * E2E tests for Saved Maps feature on Maps page.
 * Tests map library UI, save/load/delete operations, and persistence.
 */

test.describe('Saved Maps', () => {
  const baseURL = process.env.BASE_URL || 'http://127.0.0.1:5000';

  test.beforeEach(async ({ page }) => {
    // Navigate to Maps page
    await page.goto(`${baseURL}/map`);
    await expect(page.getByText('Saved Maps')).toBeVisible();
  });

  test('map library panel is visible', async ({ page }) => {
    // Verify left panel elements are present
    await expect(page.getByTestId('save-current-map')).toBeVisible();
    await expect(page.getByTestId('map-search')).toBeVisible();
    await expect(page.getByTestId('map-list')).toBeVisible();
  });

  test('save new map', async ({ page }) => {
    // Handle prompt dialogs
    page.on('dialog', async (dialog) => {
      if (dialog.message().includes('Enter map name')) {
        await dialog.accept('Test Map E2E');
      } else if (dialog.message().includes('description')) {
        await dialog.accept('E2E test map');
      } else if (dialog.message().includes('Saved map')) {
        await dialog.accept();
      }
    });

    // Click save button
    await page.getByTestId('save-current-map').click();

    // Wait for map to appear in list
    await page.waitForTimeout(1000);
    await expect(page.locator('.map-item').filter({ hasText: 'Test Map E2E' })).toBeVisible();
  });

  test('load saved map', async ({ page }) => {
    // First create a map
    page.on('dialog', async (dialog) => {
      if (dialog.message().includes('Enter map name')) {
        await dialog.accept('Load Test Map');
      } else if (dialog.message().includes('description')) {
        await dialog.accept('Map for load testing');
      } else {
        await dialog.accept();
      }
    });

    await page.getByTestId('save-current-map').click();
    await page.waitForTimeout(1000);

    // Find the map item and click Load button
    const mapItem = page.locator('.map-item').filter({ hasText: 'Load Test Map' });
    await expect(mapItem).toBeVisible();

    await mapItem.locator('button.load-btn').click();

    // Verify load confirmation dialog
    await expect(page.getByText(/Loaded map/)).toBeVisible({ timeout: 2000 });
  });

  test('delete saved map', async ({ page }) => {
    // First create a map
    page.on('dialog', async (dialog) => {
      if (dialog.message().includes('Enter map name')) {
        await dialog.accept('Delete Test Map');
      } else if (dialog.message().includes('description')) {
        await dialog.accept('Map for deletion');
      } else if (dialog.message().includes('Delete map')) {
        await dialog.accept(); // Confirm deletion
      } else {
        await dialog.accept();
      }
    });

    await page.getByTestId('save-current-map').click();
    await page.waitForTimeout(1000);

    // Find the map and click delete
    const mapItem = page.locator('.map-item').filter({ hasText: 'Delete Test Map' });
    await expect(mapItem).toBeVisible();

    await mapItem.locator('button.delete-btn').click();

    // Wait for deletion
    await page.waitForTimeout(1000);

    // Verify map is no longer in list
    await expect(mapItem).not.toBeVisible();
  });

  test('search filters map list', async ({ page }) => {
    // Create multiple maps
    page.on('dialog', async (dialog) => {
      const msg = dialog.message();
      if (msg.includes('Enter map name')) {
        const timestamp = Date.now();
        await dialog.accept(`Search Map ${timestamp}`);
      } else if (msg.includes('description')) {
        await dialog.accept('');
      } else {
        await dialog.accept();
      }
    });

    // Create 2 maps
    await page.getByTestId('save-current-map').click();
    await page.waitForTimeout(500);
    await page.getByTestId('save-current-map').click();
    await page.waitForTimeout(1000);

    // Count total maps
    const totalMaps = await page.locator('.map-item').count();
    expect(totalMaps).toBeGreaterThan(0);

    // Search for specific map
    await page.getByTestId('map-search').fill('Search Map');
    await page.waitForTimeout(500);

    // Verify filtered results
    const filteredMaps = await page.locator('.map-item').count();
    expect(filteredMaps).toBeGreaterThan(0);
  });

  test('map item shows metadata', async ({ page }) => {
    // Create a map
    page.on('dialog', async (dialog) => {
      if (dialog.message().includes('Enter map name')) {
        await dialog.accept('Metadata Test Map');
      } else if (dialog.message().includes('description')) {
        await dialog.accept('Test description');
      } else {
        await dialog.accept();
      }
    });

    await page.getByTestId('save-current-map').click();
    await page.waitForTimeout(1000);

    // Verify map item structure
    const mapItem = page.locator('.map-item').filter({ hasText: 'Metadata Test Map' });
    await expect(mapItem).toBeVisible();

    // Check for name
    await expect(mapItem.locator('.map-name')).toContainText('Metadata Test Map');

    // Check for metadata (timestamp)
    await expect(mapItem.locator('.map-meta')).toBeVisible();

    // Check for action buttons
    await expect(mapItem.locator('.load-btn')).toBeVisible();
    await expect(mapItem.locator('.delete-btn')).toBeVisible();
  });

  test('empty state shows when no maps', async ({ page }) => {
    // Delete all maps if any exist
    const existingMaps = await page.locator('.map-item .delete-btn').all();

    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    for (const deleteBtn of existingMaps) {
      await deleteBtn.click();
      await page.waitForTimeout(300);
    }

    // Verify empty state is shown
    await expect(page.locator('#map-library-empty')).toBeVisible();
    await expect(page.getByText('No saved maps yet')).toBeVisible();
  });

  test('active map is highlighted', async ({ page }) => {
    // Create a map
    page.on('dialog', async (dialog) => {
      if (dialog.message().includes('Enter map name')) {
        await dialog.accept('Active Map Test');
      } else if (dialog.message().includes('description')) {
        await dialog.accept('');
      } else {
        await dialog.accept();
      }
    });

    await page.getByTestId('save-current-map').click();
    await page.waitForTimeout(1000);

    // Load the map
    const mapItem = page.locator('.map-item').filter({ hasText: 'Active Map Test' });
    await mapItem.locator('.load-btn').click();
    await page.waitForTimeout(500);

    // Verify active class is applied
    await expect(mapItem).toHaveClass(/active/);
  });

  test('map saves and restores query', async ({ page }) => {
    const testQuery = 'MATCH (n:File) RETURN n LIMIT 5';

    // Wait for CodeMirror to initialize
    await page.waitForTimeout(2000);

    // Set a query in the editor
    // Note: This is a simplified approach - actual CodeMirror interaction may need adjustment
    await page.evaluate((query) => {
      const editors = (window as any).tabEditors;
      if (editors) {
        const editorId = Object.keys(editors)[0];
        if (editorId && editors[editorId]) {
          editors[editorId].setValue(query);
        }
      }
    }, testQuery);

    // Save the map
    page.on('dialog', async (dialog) => {
      if (dialog.message().includes('Enter map name')) {
        await dialog.accept('Query Save Test');
      } else if (dialog.message().includes('description')) {
        await dialog.accept('');
      } else {
        await dialog.accept();
      }
    });

    await page.getByTestId('save-current-map').click();
    await page.waitForTimeout(1000);

    // Clear the query
    await page.evaluate(() => {
      const editors = (window as any).tabEditors;
      if (editors) {
        const editorId = Object.keys(editors)[0];
        if (editorId && editors[editorId]) {
          editors[editorId].setValue('');
        }
      }
    });

    // Load the map
    const mapItem = page.locator('.map-item').filter({ hasText: 'Query Save Test' });
    await mapItem.locator('.load-btn').click();
    await page.waitForTimeout(1000);

    // Verify query was restored
    const restoredQuery = await page.evaluate(() => {
      const editors = (window as any).tabEditors;
      if (editors) {
        const editorId = Object.keys(editors)[0];
        if (editorId && editors[editorId]) {
          return editors[editorId].getValue();
        }
      }
      return '';
    });

    expect(restoredQuery).toContain('MATCH (n:File)');
  });

  test('maps persist across page reloads', async ({ page }) => {
    // Create a map
    page.on('dialog', async (dialog) => {
      if (dialog.message().includes('Enter map name')) {
        await dialog.accept('Persistence Test Map');
      } else if (dialog.message().includes('description')) {
        await dialog.accept('');
      } else {
        await dialog.accept();
      }
    });

    await page.getByTestId('save-current-map').click();
    await page.waitForTimeout(1000);

    // Verify map exists
    await expect(page.locator('.map-item').filter({ hasText: 'Persistence Test Map' })).toBeVisible();

    // Reload page
    await page.reload();
    await page.waitForTimeout(2000);

    // Verify map still exists
    await expect(page.locator('.map-item').filter({ hasText: 'Persistence Test Map' })).toBeVisible();
  });
});
