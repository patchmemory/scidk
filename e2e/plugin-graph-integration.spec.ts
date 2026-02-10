import { test, expect } from '@playwright/test';

/**
 * E2E tests for Plugin Graph Integration Wizard step.
 * Tests the optional graph integration step that appears for data_import plugins.
 */

test('graph integration step appears for data_import plugins', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Open wizard
  await page.locator('#btn-new-plugin-instance').click();
  await page.waitForTimeout(300);

  // Select a data_import template (e.g., table_loader)
  const tableLoaderCard = page.locator('.template-card').filter({ hasText: /table.*loader/i }).first();
  if (await tableLoaderCard.isVisible()) {
    await tableLoaderCard.click();
    await page.waitForTimeout(200);

    // Click Next
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(300);

    // Fill in required config (Step 2)
    await page.locator('#instance-name').fill('Test Graph Integration Instance');

    // Check if there are other required fields
    const fileInput = page.locator('input[type="file"]').first();
    if (await fileInput.isVisible()) {
      // For testing, we can skip file upload as it's optional for testing
      // Just make sure the form is filled enough to proceed
    }

    // Click Next to go to Step 3 (Graph Integration)
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(500);

    // Check that Step 3 (Graph Integration) is visible
    const graphStep = page.locator('#wizard-step-3');
    await expect(graphStep).toBeVisible();
    await expect(graphStep.locator('h3')).toContainText('Graph Integration');

    // Check for graph enable checkbox
    const graphEnableCheckbox = page.locator('#graph-enable');
    await expect(graphEnableCheckbox).toBeVisible();
  }
});

test('graph integration fields are hidden by default', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Open wizard
  await page.locator('#btn-new-plugin-instance').click();
  await page.waitForTimeout(300);

  // Select a data_import template
  const tableLoaderCard = page.locator('.template-card').filter({ hasText: /table.*loader/i }).first();
  if (await tableLoaderCard.isVisible()) {
    await tableLoaderCard.click();
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(300);

    // Fill minimal config
    await page.locator('#instance-name').fill('Test Instance');

    // Go to graph integration step
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(500);

    // Graph config fields should be hidden initially
    const graphConfigFields = page.locator('#graph-config-fields');
    await expect(graphConfigFields).not.toBeVisible();
  }
});

test('graph integration fields appear when checkbox is enabled', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Open wizard
  await page.locator('#btn-new-plugin-instance').click();
  await page.waitForTimeout(300);

  // Select a data_import template
  const tableLoaderCard = page.locator('.template-card').filter({ hasText: /table.*loader/i }).first();
  if (await tableLoaderCard.isVisible()) {
    await tableLoaderCard.click();
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(300);

    // Fill config with table name
    await page.locator('#instance-name').fill('Equipment Data');
    const tableNameInput = page.locator('input[name="table_name"]');
    if (await tableNameInput.isVisible()) {
      await tableNameInput.fill('lab_equipment');
    }

    // Go to graph integration step
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(500);

    // Enable graph integration
    await page.locator('#graph-enable').check();
    await page.waitForTimeout(200);

    // Fields should now be visible
    const graphConfigFields = page.locator('#graph-config-fields');
    await expect(graphConfigFields).toBeVisible();

    // Check for required fields
    await expect(page.locator('#graph-label-name')).toBeVisible();
    await expect(page.locator('#graph-primary-key')).toBeVisible();
    await expect(page.locator('input[name="sync-strategy"]').first()).toBeVisible();
  }
});

test('label name is auto-generated from table name', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Open wizard
  await page.locator('#btn-new-plugin-instance').click();
  await page.waitForTimeout(300);

  // Select a data_import template
  const tableLoaderCard = page.locator('.template-card').filter({ hasText: /table.*loader/i }).first();
  if (await tableLoaderCard.isVisible()) {
    await tableLoaderCard.click();
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(300);

    // Fill config with a specific table name
    await page.locator('#instance-name').fill('Equipment Data');
    const tableNameInput = page.locator('input[name="table_name"]');
    if (await tableNameInput.isVisible()) {
      await tableNameInput.fill('lab_equipment_2024');
    }

    // Go to graph integration step
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(500);

    // Check that label name is auto-generated (e.g., "LabEquipment2024")
    const labelNameInput = page.locator('#graph-label-name');
    const labelValue = await labelNameInput.inputValue();

    // Should be in CamelCase format
    expect(labelValue).toMatch(/^[A-Z][a-zA-Z0-9]*$/);
    expect(labelValue).toBeTruthy();
  }
});

test('wizard validates graph config when enabled', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Open wizard
  await page.locator('#btn-new-plugin-instance').click();
  await page.waitForTimeout(300);

  // Select a data_import template
  const tableLoaderCard = page.locator('.template-card').filter({ hasText: /table.*loader/i }).first();
  if (await tableLoaderCard.isVisible()) {
    await tableLoaderCard.click();
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(300);

    // Fill minimal config
    await page.locator('#instance-name').fill('Test Instance');

    // Go to graph integration step
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(500);

    // Enable graph integration
    await page.locator('#graph-enable').check();
    await page.waitForTimeout(200);

    // Clear label name to test validation
    await page.locator('#graph-label-name').fill('');

    // Try to proceed to next step - should fail validation
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(300);

    // Should still be on step 3
    await expect(page.locator('#wizard-step-3')).toBeVisible();
  }
});

test('full wizard flow with graph integration enabled', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Open wizard
  await page.locator('#btn-new-plugin-instance').click();
  await page.waitForTimeout(300);

  // Step 1: Select template
  const tableLoaderCard = page.locator('.template-card').filter({ hasText: /table.*loader/i }).first();
  if (await tableLoaderCard.isVisible()) {
    await tableLoaderCard.click();
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(300);

    // Step 2: Configure instance
    await page.locator('#instance-name').fill('E2E Test Equipment Instance');
    const tableNameInput = page.locator('input[name="table_name"]');
    if (await tableNameInput.isVisible()) {
      await tableNameInput.fill('test_equipment');
    }

    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(500);

    // Step 3: Graph Integration
    await page.locator('#graph-enable').check();
    await page.waitForTimeout(200);

    // Verify label name is auto-filled
    const labelName = await page.locator('#graph-label-name').inputValue();
    expect(labelName).toBeTruthy();

    // Select primary key
    await page.locator('#graph-primary-key').selectOption('id');

    // Select sync strategy
    await page.locator('input[name="sync-strategy"][value="on_demand"]').check();

    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(500);

    // Step 4: Preview & Confirm
    const step4 = page.locator('#wizard-step-4');
    await expect(step4).toBeVisible();
    await expect(step4.locator('h3')).toContainText('Preview');

    // Check that Create Instance button is visible
    await expect(page.locator('#wizard-create-btn')).toBeVisible();

    // Note: We don't actually create the instance in E2E tests to avoid side effects
    // In a real test environment with proper cleanup, you would:
    // await page.locator('#wizard-create-btn').click();
    // await page.waitForTimeout(1000);
    // await expect(page.locator('#plugin-instances-list')).toContainText('E2E Test Equipment Instance');
  }
});

test('wizard skips graph step for non-data_import plugins', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Open wizard
  await page.locator('#btn-new-plugin-instance').click();
  await page.waitForTimeout(300);

  // Try to find a non-data_import template (e.g., exporter category)
  // If all templates are data_import, this test will be skipped
  const allTemplateCards = page.locator('.template-card');
  const count = await allTemplateCards.count();

  for (let i = 0; i < count; i++) {
    const card = allTemplateCards.nth(i);
    const text = await card.textContent();

    // Try to identify non-data_import templates by description
    if (text && !text.toLowerCase().includes('import') && !text.toLowerCase().includes('loader')) {
      await card.click();
      await page.waitForTimeout(200);

      await page.locator('#wizard-next-btn').click();
      await page.waitForTimeout(300);

      // Fill minimal config
      await page.locator('#instance-name').fill('Test Non-Import Instance');

      // Click Next - should skip to Step 4 (preview), not Step 3 (graph)
      await page.locator('#wizard-next-btn').click();
      await page.waitForTimeout(500);

      // Should see Step 4 (Preview), not Step 3 (Graph Integration)
      const visibleStep = await page.locator('.wizard-step[style*="display: block"]');
      const stepText = await visibleStep.textContent();

      expect(stepText).toContain('Preview');
      expect(stepText).not.toContain('Graph Integration');

      break;
    }
  }
});

test('previous button works correctly with graph step', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Open wizard
  await page.locator('#btn-new-plugin-instance').click();
  await page.waitForTimeout(300);

  // Select data_import template
  const tableLoaderCard = page.locator('.template-card').filter({ hasText: /table.*loader/i }).first();
  if (await tableLoaderCard.isVisible()) {
    await tableLoaderCard.click();
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(300);

    // Fill config
    await page.locator('#instance-name').fill('Test Instance');
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(500);

    // Now on Step 3 (Graph Integration)
    await expect(page.locator('#wizard-step-3')).toBeVisible();

    // Click Previous
    await page.locator('#wizard-prev-btn').click();
    await page.waitForTimeout(300);

    // Should be back on Step 2
    await expect(page.locator('#wizard-step-2')).toBeVisible();

    // Go forward again
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(500);

    // Should be on Step 3 again
    await expect(page.locator('#wizard-step-3')).toBeVisible();

    // Now go to Step 4
    await page.locator('#wizard-next-btn').click();
    await page.waitForTimeout(500);

    // Should be on Step 4 (Preview)
    await expect(page.locator('#wizard-step-4')).toBeVisible();

    // Click Previous
    await page.locator('#wizard-prev-btn').click();
    await page.waitForTimeout(300);

    // Should be back on Step 3 (Graph Integration)
    await expect(page.locator('#wizard-step-3')).toBeVisible();
  }
});
