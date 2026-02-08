import { test, expect } from '@playwright/test';

/**
 * E2E tests for Links page functionality.
 * Tests the complete workflow: create link definition → configure source → configure target → define relationship → preview → execute
 */

test.skip('links page loads and displays empty state', async ({ page, baseURL }) => {
  const consoleMessages: { type: string; text: string }[] = [];
  page.on('console', (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Navigate to Links page
  await page.goto(`${base}/integrate`);
  await page.waitForLoadState('networkidle');

  // Verify page loads
  await expect(page).toHaveTitle(/-SciDK-> Integrations/i, { timeout: 10_000 });

  // Check for new link button
  await expect(page.getByTestId('new-integration-btn')).toBeVisible();

  // Check for link list
  await expect(page.getByTestId('integration-list')).toBeVisible();

  // No console errors
  const errors = consoleMessages.filter((m) => m.type === 'error');
  expect(errors.length).toBe(0);
});

test.skip('links navigation link is visible in header', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Check that Links link exists in navigation
  const linksLink = page.getByTestId('nav-integrate');
  await expect(linksLink).toBeVisible();

  // Click it and verify we navigate to links page
  await linksLink.click();
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveTitle(/-SciDK-> Integrations/i);
});

test.skip('wizard navigation: can navigate through all 3 steps (Label→Label refactor)', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Create labels needed for this test
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('WizTestLabel1');
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(500);

  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('WizTestLabel2');
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(500);

  await page.goto(`${base}/integrate`);
  await page.waitForLoadState('networkidle');

  // Click "New Link" button
  await page.getByTestId('new-integration-btn').click();

  // Verify wizard is visible
  await expect(page.locator('#link-wizard')).toBeVisible();

  // Step 1 should be active (Source Label)
  await expect(page.locator('.wizard-step[data-step="1"]')).toHaveClass(/active/);

  // Enter link name and select source label
  await page.getByTestId('integration-name').fill('Test Link');
  await page.getByTestId('source-label-select').selectOption({ index: 1 }); // Select first label

  // Click Next to go to step 2 (Match Strategy)
  await page.locator('#btn-next').click();
  await expect(page.locator('.wizard-step[data-step="2"]')).toHaveClass(/active/);

  // Click Next to go to step 3 (Target & Relationship)
  await page.locator('#btn-next').click();
  await expect(page.locator('.wizard-step[data-step="3"]')).toHaveClass(/active/);

  // Select target label and enter relationship type
  await page.getByTestId('target-label-select').selectOption({ index: 1 });
  await page.getByTestId('rel-type').fill('TEST_REL');

  // Verify Back button is visible
  await expect(page.locator('#btn-prev')).toBeVisible();

  // Click Back to go to step 2
  await page.locator('#btn-prev').click();
  await expect(page.locator('.wizard-step[data-step="2"]')).toHaveClass(/active/);
});

test.skip('can create table import link definition (Label→Label refactor)', async ({ page, baseURL }) => {
  const consoleMessages: { type: string; text: string }[] = [];
  page.on('console', (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // First create labels we'll use
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Create Author label
  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('Author');
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(500);

  // Create File label
  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('File');
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(500);

  // Now go to Links page
  await page.goto(`${base}/integrate`);
  await page.waitForLoadState('networkidle');

  // Click "New Link" button
  await page.getByTestId('new-integration-btn').click();

  // Step 1: Select Source Label
  await page.getByTestId('integration-name').fill('Import Authors to Files');
  await page.getByTestId('source-label-select').selectOption('Author');

  // Go to Step 2
  await page.locator('#btn-next').click();

  // Step 2: Configure Match Strategy (table_import)
  await page.locator('.match-strategy-btn[data-strategy="table_import"]').click();

  // Enter table data
  const csvData = 'name,email,file_path\nAlice,alice@ex.com,file1.txt\nBob,bob@ex.com,file2.txt';
  await page.locator('#table-data').fill(csvData);

  // Go to Step 3
  await page.locator('#btn-next').click();

  // Step 3: Target Label & Relationship
  await page.getByTestId('target-label-select').selectOption('File');
  await page.getByTestId('rel-type').fill('AUTHORED');

  // Add a relationship property
  await page.locator('#btn-add-rel-prop').click();
  const propRows = page.locator('#rel-props-container .property-row');
  await expect(propRows).toHaveCount(1);
  await propRows.locator('[data-prop-key]').fill('date');
  await propRows.locator('[data-prop-value]').fill('2024-01-15');

  // Save the definition
  await page.locator('#btn-save-def').click();
  await page.waitForTimeout(1500); // Wait for save

  // Verify link appears in list
  const linkItems = page.locator('.link-item');
  await expect(linkItems.first()).toBeVisible();
  const linkText = await linkItems.first().textContent();
  expect(linkText).toContain('Import Authors to Files');
  expect(linkText).toContain('Author');
  expect(linkText).toContain('File');
  expect(linkText).toContain('AUTHORED');

  // No console errors
  const errors = consoleMessages.filter((m) => m.type === 'error');
  expect(errors.length).toBe(0);
});

test.skip('can create Label to Label link definition with property matching', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // First create labels we'll use
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Create Person label
  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('Person');
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(500);

  // Create Document label
  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('Document');
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(500);

  // Now go to Links page
  await page.goto(`${base}/integrate`);
  await page.waitForLoadState('networkidle');

  // Click "New Link" button
  await page.getByTestId('new-integration-btn').click();

  // Step 1: Select Source Label
  await page.getByTestId('integration-name').fill('Person to Document Link');
  await page.getByTestId('source-label-select').selectOption('Person');

  // Go to Step 2
  await page.locator('#btn-next').click();

  // Step 2: Configure Match Strategy (property matching - default)
  await page.locator('#match-source-field').fill('email');
  await page.locator('#match-target-field').fill('author_email');

  // Go to Step 3
  await page.locator('#btn-next').click();

  // Step 3: Target Label & Relationship
  await page.getByTestId('target-label-select').selectOption('Document');
  await page.getByTestId('rel-type').fill('AUTHORED');

  // Save the definition
  await page.locator('#btn-save-def').click();
  await page.waitForTimeout(1500);

  // Verify link appears in list
  const linkItems = page.locator('.link-item');
  const linkText = await linkItems.first().textContent();
  expect(linkText).toContain('Person to Document Link');
  expect(linkText).toContain('Person');
  expect(linkText).toContain('Document');
  expect(linkText).toContain('AUTHORED');
});

test.skip('can save and load link definition', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  const uniqueName = `Test Save Load ${Date.now()}`;

  // First create labels
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('SaveLoadSource');
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(500);

  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('SaveLoadTarget');
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(500);

  // Now go to Links
  await page.goto(`${base}/integrate`);
  await page.waitForLoadState('networkidle');

  // Create a link definition
  await page.getByTestId('new-integration-btn').click();
  await page.getByTestId('integration-name').fill(uniqueName);
  await page.getByTestId('source-label-select').selectOption('SaveLoadSource');
  await page.locator('#btn-next').click();
  await page.locator('.match-strategy-btn[data-strategy="property"]').click();
  await page.locator('#match-source-field').fill('col1');
  await page.locator('#match-target-field').fill('field1');
  await page.locator('#btn-next').click();
  await page.getByTestId('target-label-select').selectOption('SaveLoadTarget');
  await page.getByTestId('rel-type').fill('TEST_REL');
  await page.locator('#btn-save-def').click();
  await page.waitForTimeout(1500);

  // Click on the saved link by finding it by name
  const linkItem = page.locator('.link-item').filter({ hasText: uniqueName });
  await linkItem.click();
  await page.waitForTimeout(500);

  // Verify wizard is populated with saved data
  await expect(page.getByTestId('integration-name')).toHaveValue(uniqueName);

  // Check that source label is selected
  await expect(page.getByTestId('source-label-select')).toHaveValue('SaveLoadSource');

  // Navigate to step 2 and verify match strategy
  await page.locator('#btn-next').click();
  await expect(page.locator('#match-source-field')).toHaveValue('col1');
  await expect(page.locator('#match-target-field')).toHaveValue('field1');

  // Navigate to step 3 and verify target and relationship
  await page.locator('#btn-next').click();
  await expect(page.getByTestId('target-label-select')).toHaveValue('SaveLoadTarget');
  await expect(page.getByTestId('rel-type')).toHaveValue('TEST_REL');

  // Cleanup: Delete the test link
  page.once('dialog', async (dialog) => await dialog.accept());
  await page.locator('#btn-delete-def').click();
  await page.waitForTimeout(1000);
});

test.skip('can delete link definition', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Capture console logs and errors
  const consoleLogs: string[] = [];
  page.on('console', msg => consoleLogs.push(`[${msg.type()}] ${msg.text()}`));
  page.on('pageerror', err => consoleLogs.push(`[ERROR] ${err.message}`));

  await page.goto(`${base}/integrate`);
  await page.waitForLoadState('networkidle');

  const uniqueName = `To Delete ${Date.now()}`;

  // First create labels
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');
  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('DeleteTest');
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(500);

  // Now create a link definition
  await page.goto(`${base}/integrate`);
  await page.waitForLoadState('networkidle');
  await page.getByTestId('new-integration-btn').click();
  await page.getByTestId('integration-name').fill(uniqueName);
  await page.getByTestId('source-label-select').selectOption('DeleteTest');
  await page.locator('#btn-next').click();
  await page.locator('#btn-next').click();
  await page.getByTestId('target-label-select').selectOption('DeleteTest');
  await page.getByTestId('rel-type').fill('DELETE_ME');
  await page.locator('#btn-save-def').click();
  await page.waitForTimeout(1500);

  // Load the link by finding it by name
  const linkItem = page.locator('.link-item').filter({ hasText: uniqueName });
  await linkItem.click();
  await page.waitForTimeout(500);

  // Delete button should be visible
  const deleteBtn = page.locator('#btn-delete-def');
  await expect(deleteBtn).toBeVisible();

  // Handle confirmation dialog
  page.once('dialog', async (dialog) => {
    expect(dialog.type()).toBe('confirm');
    await dialog.accept();
  });

  await deleteBtn.click();

  // Wait for wizard to hide (indicates delete completed)
  try {
    await expect(page.locator('#link-wizard')).toBeHidden({ timeout: 5000 });
  } catch (e) {
    console.log('Console logs:', consoleLogs.join('\n'));
    throw e;
  }

  // Wait a bit more for list to update
  await page.waitForTimeout(1000);

  // Verify link is removed from list - it should not appear anywhere
  const listItems = await page.locator('.link-item').all();
  const listTexts = await Promise.all(listItems.map(item => item.textContent()));
  const found = listTexts.some(text => text?.includes(uniqueName));

  if (found) {
    console.log('Console logs:', consoleLogs.join('\n'));
  }

  expect(found).toBe(false);
});

test.skip('validation: cannot save without name', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/integrate`);
  await page.waitForLoadState('networkidle');

  // Create new link but don't enter name
  await page.getByTestId('new-integration-btn').click();

  // Try to save without name
  await page.locator('#btn-save-def').click();
  await page.waitForTimeout(500);

  // Should still be on wizard (not saved)
  await expect(page.getByTestId('integration-name')).toBeVisible();
  const value = await page.getByTestId('integration-name').inputValue();
  expect(value).toBe('');
});

test.skip('validation: cannot save without relationship type', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/integrate`);
  await page.waitForLoadState('networkidle');

  // Create new link with name but no relationship type
  await page.getByTestId('new-integration-btn').click();
  await page.getByTestId('integration-name').fill('No Rel Type');

  // Navigate to step 3
  await page.locator('#btn-next').click();
  await page.locator('#btn-next').click();

  // Don't enter relationship type

  // Try to save
  await page.locator('#btn-save-def').click();
  await page.waitForTimeout(500);

  // Should still be on wizard
  await expect(page.locator('#rel-type')).toBeVisible();
  const value = await page.locator('#rel-type').inputValue();
  expect(value).toBe('');
});

test.skip('Label→Label: source and target are label dropdowns', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/integrate`);
  await page.waitForLoadState('networkidle');

  await page.getByTestId('new-integration-btn').click();

  // Step 1: Source label dropdown should be visible
  await expect(page.getByTestId('source-label-select')).toBeVisible();

  // Navigate to step 3
  await page.locator('#btn-next').click();
  await page.locator('#btn-next').click();

  // Step 3: Target label dropdown should be visible
  await expect(page.getByTestId('target-label-select')).toBeVisible();
});

test.skip('can switch between match strategies (Label→Label refactor)', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/integrate`);
  await page.waitForLoadState('networkidle');

  await page.getByTestId('new-integration-btn').click();

  // Navigate to step 2 (Match Strategy)
  await page.locator('#btn-next').click();

  // Property match should be visible by default
  await expect(page.locator('#match-property')).toBeVisible();
  await expect(page.locator('#match-fuzzy')).not.toBeVisible();
  await expect(page.locator('#match-table-import')).not.toBeVisible();
  await expect(page.locator('#match-api-endpoint')).not.toBeVisible();

  // Switch to Fuzzy match
  await page.locator('.match-strategy-btn[data-strategy="fuzzy"]').click();
  await expect(page.locator('#match-property')).not.toBeVisible();
  await expect(page.locator('#match-fuzzy')).toBeVisible();

  // Switch to Table Import
  await page.locator('.match-strategy-btn[data-strategy="table_import"]').click();
  await expect(page.locator('#match-fuzzy')).not.toBeVisible();
  await expect(page.locator('#match-table-import')).toBeVisible();

  // Switch to API Endpoint
  await page.locator('.match-strategy-btn[data-strategy="api_endpoint"]').click();
  await expect(page.locator('#match-table-import')).not.toBeVisible();
  await expect(page.locator('#match-api-endpoint')).toBeVisible();

  // Switch back to Property match
  await page.locator('.match-strategy-btn[data-strategy="property"]').click();
  await expect(page.locator('#match-api-endpoint')).not.toBeVisible();
  await expect(page.locator('#match-property')).toBeVisible();
});

test.skip('can add and remove relationship properties', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/integrate`);
  await page.waitForLoadState('networkidle');

  await page.getByTestId('new-integration-btn').click();

  // Navigate to step 3
  await page.locator('#btn-next').click();
  await page.locator('#btn-next').click();

  // Add 3 relationship properties
  for (let i = 0; i < 3; i++) {
    await page.locator('#btn-add-rel-prop').click();
  }

  // Verify 3 property rows exist
  const propRows = page.locator('#rel-props-container .property-row');
  await expect(propRows).toHaveCount(3);

  // Fill in values
  await propRows.nth(0).locator('[data-prop-key]').fill('key1');
  await propRows.nth(1).locator('[data-prop-key]').fill('key2');
  await propRows.nth(2).locator('[data-prop-key]').fill('key3');

  // Remove the second property
  await propRows.nth(1).locator('button').click();

  // Verify only 2 properties remain
  await expect(page.locator('#rel-props-container .property-row')).toHaveCount(2);
});

test.skip('wizard visual summary: step circles show summaries for completed steps', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/integrate`);
  await page.waitForLoadState('networkidle');

  // Create test labels first
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Create Person label
  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('Person');
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(500);

  // Create File label
  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('File');
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(500);

  // Go back to Links
  await page.goto(`${base}/integrate`);
  await page.waitForLoadState('networkidle');
  await page.getByTestId('new-integration-btn').click();

  // Step 1: Initial state should show "1"
  let step1Circle = page.getByTestId('step-1-circle');
  await expect(step1Circle).toHaveText('1');

  // Fill out Step 1
  await page.getByTestId('integration-name').fill('Test Visual Summary');
  await page.getByTestId('source-label-select').selectOption('Person');

  // Navigate to Step 2
  await page.locator('#btn-next').click();
  await page.waitForTimeout(200);

  // Step 1 should now show "Person" (source label name)
  await expect(step1Circle).toHaveText('Person');

  // Step 2 should be active and show "2"
  let step2Circle = page.getByTestId('step-2-circle');
  await expect(step2Circle).toHaveText('2');

  // Select fuzzy match strategy
  await page.locator('.match-strategy-btn[data-strategy="fuzzy"]').click();

  // Navigate to Step 3
  await page.locator('#btn-next').click();
  await page.waitForTimeout(200);

  // Step 2 should now show "~" (fuzzy icon)
  await expect(step2Circle).toHaveText('~');

  // Fill out Step 3
  await page.getByTestId('target-label-select').selectOption('File');
  await page.getByTestId('rel-type').fill('AUTHORED');

  // Navigate back to Step 2
  await page.locator('#btn-prev').click();
  await page.waitForTimeout(200);

  // Step 1 should still show "Person"
  await expect(step1Circle).toHaveText('Person');

  // Switch to table_import strategy
  await page.locator('.match-strategy-btn[data-strategy="table_import"]').click();

  // Navigate to Step 3 again
  await page.locator('#btn-next').click();
  await page.waitForTimeout(200);

  // Step 2 should now show "📊" (table icon)
  await expect(step2Circle).toHaveText('📊');

  // Navigate back to Step 1
  await page.locator('#btn-prev').click();
  await page.locator('#btn-prev').click();
  await page.waitForTimeout(200);

  // Change source label
  await page.getByTestId('source-label-select').selectOption('File');
  await page.locator('#btn-next').click();
  await page.waitForTimeout(200);

  // Step 1 should now show "File"
  await expect(step1Circle).toHaveText('File');

  // Test tooltip visibility on hover (Step 1)
  const step1Tooltip = page.getByTestId('step-1-tooltip');
  await expect(step1Tooltip).toHaveText('Source: File');
});
