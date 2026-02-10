import { test, expect } from '@playwright/test';

/**
 * E2E tests for Plugin Instances management in Settings > Plugins.
 * Tests creating, configuring, syncing, and deleting plugin instances.
 */

test('plugin instances section loads correctly', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Check that Plugin Instances section is visible
  const pluginInstancesSection = page.locator('#plugin-instances-list');
  await expect(pluginInstancesSection).toBeVisible();

  // Check for "New Plugin Instance" button
  const newInstanceBtn = page.locator('#btn-new-plugin-instance');
  await expect(newInstanceBtn).toBeVisible();
});

test('new plugin instance wizard opens and displays templates', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Click "New Plugin Instance" button
  await page.locator('#btn-new-plugin-instance').click();
  await page.waitForTimeout(300);

  // Check that wizard modal is visible
  const wizardModal = page.locator('#plugin-instance-wizard-modal');
  await expect(wizardModal).toBeVisible();

  // Check that Step 1 (template selection) is visible
  const step1 = page.locator('#wizard-step-1');
  await expect(step1).toBeVisible();
  await expect(step1.locator('h3')).toContainText('Step 1');

  // Check for template list container
  const templateList = page.locator('#template-list');
  await expect(templateList).toBeVisible();
});

test('wizard navigation works correctly', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Open wizard
  await page.locator('#btn-new-plugin-instance').click();
  await page.waitForTimeout(300);

  // Check that Next button is visible, but Previous is not (on step 1)
  await expect(page.locator('#wizard-next-btn')).toBeVisible();
  await expect(page.locator('#wizard-prev-btn')).not.toBeVisible();
  await expect(page.locator('#wizard-create-btn')).not.toBeVisible();

  // Try to click Next without selecting a template - should show error
  await page.locator('#wizard-next-btn').click();
  await page.waitForTimeout(200);

  // Should still be on step 1 (validation failed)
  await expect(page.locator('#wizard-step-1')).toBeVisible();
});

test('wizard can be cancelled', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Open wizard
  await page.locator('#btn-new-plugin-instance').click();
  await page.waitForTimeout(300);

  const wizardModal = page.locator('#plugin-instance-wizard-modal');
  await expect(wizardModal).toBeVisible();

  // Click Cancel button
  await page.locator('.modal-footer button.btn-secondary').last().click();
  await page.waitForTimeout(200);

  // Modal should be hidden
  await expect(wizardModal).not.toBeVisible();
});

test('plugin instance cards display correctly', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Wait for instances to load
  await page.waitForTimeout(1000);

  const instancesList = page.locator('#plugin-instances-list');
  const instanceCards = instancesList.locator('.plugin-instance-card');

  // Check if any instances exist
  const count = await instanceCards.count();

  if (count > 0) {
    // If instances exist, check that first card has expected structure
    const firstCard = instanceCards.first();
    await expect(firstCard.locator('.instance-header h4')).toBeVisible();
    await expect(firstCard.locator('.badge')).toBeVisible();
    await expect(firstCard.locator('.instance-meta')).toBeVisible();
    await expect(firstCard.locator('.instance-actions')).toBeVisible();

    // Check for action buttons
    await expect(firstCard.locator('button').filter({ hasText: 'Configure' })).toBeVisible();
    await expect(firstCard.locator('button').filter({ hasText: 'Sync Now' })).toBeVisible();
    await expect(firstCard.locator('button').filter({ hasText: /Enable|Disable/ })).toBeVisible();
    await expect(firstCard.locator('button').filter({ hasText: 'Delete' })).toBeVisible();
  } else {
    // If no instances, should show empty state message
    await expect(instancesList).toContainText('No plugin instances configured');
  }
});

test('instance action buttons are interactive', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Wait for instances to load
  await page.waitForTimeout(1000);

  const instancesList = page.locator('#plugin-instances-list');
  const instanceCards = instancesList.locator('.plugin-instance-card');
  const count = await instanceCards.count();

  if (count > 0) {
    const firstCard = instanceCards.first();

    // Test Configure button
    const configureBtn = firstCard.locator('button').filter({ hasText: 'Configure' });
    await expect(configureBtn).toBeEnabled();

    // Click Configure and verify alert/modal appears
    page.once('dialog', dialog => {
      expect(dialog.message()).toContain('Edit modal');
      dialog.accept();
    });
    await configureBtn.click();
    await page.waitForTimeout(200);

    // Test Sync Now button (with confirmation)
    const syncBtn = firstCard.locator('button').filter({ hasText: 'Sync Now' });
    const isSyncDisabled = await syncBtn.isDisabled();

    if (!isSyncDisabled) {
      page.once('dialog', dialog => {
        expect(dialog.message()).toContain('Sync this plugin instance');
        dialog.dismiss(); // Cancel the sync
      });
      await syncBtn.click();
      await page.waitForTimeout(200);
    }

    // Test Delete button (with confirmation)
    const deleteBtn = firstCard.locator('button').filter({ hasText: 'Delete' });
    page.once('dialog', dialog => {
      expect(dialog.message()).toContain('delete this plugin instance');
      dialog.dismiss(); // Cancel the deletion
    });
    await deleteBtn.click();
    await page.waitForTimeout(200);
  }
});

test('wizard step 2 shows configuration form', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // This test requires that at least one template exists
  // We'll mock the API response for template list
  await page.route('**/api/plugins/templates', route => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'success',
        templates: [
          {
            id: 'test_template',
            name: 'Test Template',
            description: 'A test template for E2E testing',
            config_schema: {
              table_name: {
                type: 'text',
                label: 'Table Name',
                required: true,
                placeholder: 'e.g., test_table'
              }
            }
          }
        ]
      })
    });
  });

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Open wizard
  await page.locator('#btn-new-plugin-instance').click();
  await page.waitForTimeout(500);

  // Select first template
  const firstTemplate = page.locator('.template-card').first();
  await firstTemplate.click();
  await page.waitForTimeout(200);

  // Check that template is selected
  await expect(firstTemplate).toHaveClass(/selected/);

  // Click Next
  await page.locator('#wizard-next-btn').click();
  await page.waitForTimeout(300);

  // Should now be on Step 2
  const step2 = page.locator('#wizard-step-2');
  await expect(step2).toBeVisible();
  await expect(step2.locator('h3')).toContainText('Step 2');

  // Check that instance name field is present
  const instanceNameInput = page.locator('#instance-name');
  await expect(instanceNameInput).toBeVisible();
  await expect(instanceNameInput).toHaveAttribute('required');

  // Check that dynamic config fields are present (based on mocked template)
  const tableNameInput = page.locator('#config-table_name');
  await expect(tableNameInput).toBeVisible();

  // Check that Previous button is now visible
  await expect(page.locator('#wizard-prev-btn')).toBeVisible();
  await expect(page.locator('#wizard-next-btn')).toBeVisible();
});

test('wizard validates required fields on step 2', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Mock template API
  await page.route('**/api/plugins/templates', route => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'success',
        templates: [
          {
            id: 'test_template',
            name: 'Test Template',
            description: 'A test template',
            config_schema: {}
          }
        ]
      })
    });
  });

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Open wizard
  await page.locator('#btn-new-plugin-instance').click();
  await page.waitForTimeout(500);

  // Select template and go to step 2
  await page.locator('.template-card').first().click();
  await page.locator('#wizard-next-btn').click();
  await page.waitForTimeout(300);

  // Try to proceed without filling instance name (required field)
  await page.locator('#wizard-next-btn').click();
  await page.waitForTimeout(300);

  // Should still be on step 2 (validation failed)
  await expect(page.locator('#wizard-step-2')).toBeVisible();

  // Fill in instance name
  await page.locator('#instance-name').fill('Test Instance');

  // Now click Next should work
  await page.locator('#wizard-next-btn').click();
  await page.waitForTimeout(300);

  // Should now be on Step 3
  await expect(page.locator('#wizard-step-3')).toBeVisible();
});

test('wizard step 3 shows configuration summary', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Mock template API
  await page.route('**/api/plugins/templates', route => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'success',
        templates: [
          {
            id: 'test_template',
            name: 'Test Template',
            description: 'A test template',
            config_schema: {}
          }
        ]
      })
    });
  });

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Plugins section
  await page.locator('.settings-sidebar-item[data-section="plugins"]').click();
  await page.waitForTimeout(500);

  // Open wizard and navigate to step 3
  await page.locator('#btn-new-plugin-instance').click();
  await page.waitForTimeout(500);

  await page.locator('.template-card').first().click();
  await page.locator('#wizard-next-btn').click();
  await page.waitForTimeout(300);

  await page.locator('#instance-name').fill('Test Instance');
  await page.locator('#wizard-next-btn').click();
  await page.waitForTimeout(300);

  // Should be on Step 3
  const step3 = page.locator('#wizard-step-3');
  await expect(step3).toBeVisible();
  await expect(step3.locator('h3')).toContainText('Step 3');

  // Check for configuration summary
  const configSummary = page.locator('.config-summary');
  await expect(configSummary).toBeVisible();

  const summaryDetails = page.locator('#config-summary-details');
  await expect(summaryDetails).toBeVisible();
  await expect(summaryDetails).toContainText('Test Template');
  await expect(summaryDetails).toContainText('Test Instance');

  // Check that Create Instance button is visible
  await expect(page.locator('#wizard-create-btn')).toBeVisible();
  await expect(page.locator('#wizard-next-btn')).not.toBeVisible();
});
