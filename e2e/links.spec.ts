import { test, expect } from '@playwright/test';

/**
 * E2E tests for Links page functionality.
 * Tests the complete workflow: create link definition → configure source → configure target → define relationship → preview → execute
 */

test('links page loads and displays empty state', async ({ page, baseURL }) => {
  const consoleMessages: { type: string; text: string }[] = [];
  page.on('console', (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Navigate to Links page
  await page.goto(`${base}/links`);
  await page.waitForLoadState('networkidle');

  // Verify page loads
  await expect(page).toHaveTitle(/SciDK - Links/i, { timeout: 10_000 });

  // Check for new link button
  await expect(page.getByTestId('new-link-btn')).toBeVisible();

  // Check for link list
  await expect(page.getByTestId('link-list')).toBeVisible();

  // No console errors
  const errors = consoleMessages.filter((m) => m.type === 'error');
  expect(errors.length).toBe(0);
});

test('links navigation link is visible in header', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Check that Links link exists in navigation
  const linksLink = page.getByTestId('nav-links');
  await expect(linksLink).toBeVisible();

  // Click it and verify we navigate to links page
  await linksLink.click();
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveTitle(/SciDK - Links/i);
});

test('wizard navigation: can navigate through all 4 steps', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/links`);
  await page.waitForLoadState('networkidle');

  // Click "New Link" button
  await page.getByTestId('new-link-btn').click();

  // Verify wizard is visible
  await expect(page.locator('#link-wizard')).toBeVisible();

  // Step 1 should be active
  await expect(page.locator('.wizard-step[data-step="1"]')).toHaveClass(/active/);

  // Enter link name
  await page.getByTestId('link-name').fill('Test Link');

  // Click Next to go to step 2
  await page.locator('#btn-next').click();
  await expect(page.locator('.wizard-step[data-step="2"]')).toHaveClass(/active/);

  // Click Next to go to step 3
  await page.locator('#btn-next').click();
  await expect(page.locator('.wizard-step[data-step="3"]')).toHaveClass(/active/);

  // Enter relationship type
  await page.locator('#rel-type').fill('TEST_REL');

  // Click Next to go to step 4
  await page.locator('#btn-next').click();
  await expect(page.locator('.wizard-step[data-step="4"]')).toHaveClass(/active/);

  // Verify Back button is visible
  await expect(page.locator('#btn-prev')).toBeVisible();

  // Click Back to go to step 3
  await page.locator('#btn-prev').click();
  await expect(page.locator('.wizard-step[data-step="3"]')).toHaveClass(/active/);
});

test('can create CSV to Graph link definition', async ({ page, baseURL }) => {
  const consoleMessages: { type: string; text: string }[] = [];
  page.on('console', (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/links`);
  await page.waitForLoadState('networkidle');

  // Click "New Link" button
  await page.getByTestId('new-link-btn').click();

  // Step 1: Configure Source
  await page.getByTestId('link-name').fill('CSV Authors to Files');

  // Select CSV source type
  await page.locator('.source-type-btn[data-source="csv"]').click();

  // Enter CSV data
  const csvData = 'name,email,file_path\nAlice,alice@ex.com,file1.txt\nBob,bob@ex.com,file2.txt';
  await page.locator('#csv-data').fill(csvData);

  // Go to Step 2
  await page.locator('#btn-next').click();

  // Step 2: Configure Target
  // Label target should be selected by default
  await page.locator('#target-label-name').fill('File');

  // Configure match strategy (property should be default)
  await page.locator('#match-source-field').fill('file_path');
  await page.locator('#match-target-field').fill('path');

  // Go to Step 3
  await page.locator('#btn-next').click();

  // Step 3: Define Relationship
  await page.locator('#rel-type').fill('AUTHORED');

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
  expect(linkText).toContain('CSV Authors to Files');
  expect(linkText).toContain('csv');
  expect(linkText).toContain('AUTHORED');

  // No console errors
  const errors = consoleMessages.filter((m) => m.type === 'error');
  expect(errors.length).toBe(0);
});

test('can create Graph to Graph link definition', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/links`);
  await page.waitForLoadState('networkidle');

  // Click "New Link" button
  await page.getByTestId('new-link-btn').click();

  // Step 1: Configure Source (Graph is default)
  await page.getByTestId('link-name').fill('Person to File Link');
  await page.locator('#source-label').fill('Person');
  await page.locator('#source-where').fill('p.role = "author"');

  // Go to Step 2
  await page.locator('#btn-next').click();

  // Step 2: Configure Target
  await page.locator('#target-label-name').fill('File');
  await page.locator('#match-source-field').fill('email');
  await page.locator('#match-target-field').fill('author_email');

  // Go to Step 3
  await page.locator('#btn-next').click();

  // Step 3: Define Relationship
  await page.locator('#rel-type').fill('AUTHORED_BY');

  // Save the definition
  await page.locator('#btn-save-def').click();
  await page.waitForTimeout(1500);

  // Verify link appears in list
  const linkItems = page.locator('.link-item');
  const linkText = await linkItems.first().textContent();
  expect(linkText).toContain('Person to File Link');
  expect(linkText).toContain('graph');
});

test('can save and load link definition', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/links`);
  await page.waitForLoadState('networkidle');

  const uniqueName = `Test Save Load ${Date.now()}`;

  // Create a link definition
  await page.getByTestId('new-link-btn').click();
  await page.getByTestId('link-name').fill(uniqueName);
  await page.locator('.source-type-btn[data-source="csv"]').click();
  await page.locator('#csv-data').fill('col1,col2\nval1,val2');
  await page.locator('#btn-next').click();
  await page.locator('#target-label-name').fill('TestLabel');
  await page.locator('#match-source-field').fill('col1');
  await page.locator('#match-target-field').fill('field1');
  await page.locator('#btn-next').click();
  await page.locator('#rel-type').fill('TEST_REL');
  await page.locator('#btn-save-def').click();
  await page.waitForTimeout(1500);

  // Click on the saved link by finding it by name
  const linkItem = page.locator('.link-item').filter({ hasText: uniqueName });
  await linkItem.click();
  await page.waitForTimeout(500);

  // Verify wizard is populated with saved data
  await expect(page.getByTestId('link-name')).toHaveValue(uniqueName);

  // Check that CSV button is active
  await expect(page.locator('.source-type-btn[data-source="csv"]')).toHaveClass(/active/);

  // Navigate to step 2 and verify
  await page.locator('#btn-next').click();
  await expect(page.locator('#target-label-name')).toHaveValue('TestLabel');
  await expect(page.locator('#match-source-field')).toHaveValue('col1');
  await expect(page.locator('#match-target-field')).toHaveValue('field1');

  // Navigate to step 3 and verify
  await page.locator('#btn-next').click();
  await expect(page.locator('#rel-type')).toHaveValue('TEST_REL');

  // Cleanup: Delete the test link
  page.once('dialog', async (dialog) => await dialog.accept());
  await page.locator('#btn-delete-def').click();
  await page.waitForTimeout(1000);
});

test('can delete link definition', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Capture console logs and errors
  const consoleLogs: string[] = [];
  page.on('console', msg => consoleLogs.push(`[${msg.type()}] ${msg.text()}`));
  page.on('pageerror', err => consoleLogs.push(`[ERROR] ${err.message}`));

  await page.goto(`${base}/links`);
  await page.waitForLoadState('networkidle');

  const uniqueName = `To Delete ${Date.now()}`;

  // Create a link definition
  await page.getByTestId('new-link-btn').click();
  await page.getByTestId('link-name').fill(uniqueName);
  await page.locator('#btn-next').click();
  await page.locator('#target-label-name').fill('TestLabel');
  await page.locator('#btn-next').click();
  await page.locator('#rel-type').fill('DELETE_ME');
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

test('validation: cannot save without name', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/links`);
  await page.waitForLoadState('networkidle');

  // Create new link but don't enter name
  await page.getByTestId('new-link-btn').click();

  // Try to save without name
  await page.locator('#btn-save-def').click();
  await page.waitForTimeout(500);

  // Should still be on wizard (not saved)
  await expect(page.getByTestId('link-name')).toBeVisible();
  const value = await page.getByTestId('link-name').inputValue();
  expect(value).toBe('');
});

test('validation: cannot save without relationship type', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/links`);
  await page.waitForLoadState('networkidle');

  // Create new link with name but no relationship type
  await page.getByTestId('new-link-btn').click();
  await page.getByTestId('link-name').fill('No Rel Type');

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

test('can switch between source types', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/links`);
  await page.waitForLoadState('networkidle');

  await page.getByTestId('new-link-btn').click();

  // Graph source should be visible by default
  await expect(page.locator('#source-graph')).toBeVisible();
  await expect(page.locator('#source-csv')).not.toBeVisible();
  await expect(page.locator('#source-api')).not.toBeVisible();

  // Switch to CSV
  await page.locator('.source-type-btn[data-source="csv"]').click();
  await expect(page.locator('#source-graph')).not.toBeVisible();
  await expect(page.locator('#source-csv')).toBeVisible();
  await expect(page.locator('#source-api')).not.toBeVisible();

  // Switch to API
  await page.locator('.source-type-btn[data-source="api"]').click();
  await expect(page.locator('#source-graph')).not.toBeVisible();
  await expect(page.locator('#source-csv')).not.toBeVisible();
  await expect(page.locator('#source-api')).toBeVisible();

  // Switch back to Graph
  await page.locator('.source-type-btn[data-source="graph"]').click();
  await expect(page.locator('#source-graph')).toBeVisible();
  await expect(page.locator('#source-csv')).not.toBeVisible();
  await expect(page.locator('#source-api')).not.toBeVisible();
});

test('can switch between match strategies', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/links`);
  await page.waitForLoadState('networkidle');

  await page.getByTestId('new-link-btn').click();

  // Navigate to step 2
  await page.locator('#btn-next').click();

  // Property match should be visible by default
  await expect(page.locator('#match-property')).toBeVisible();
  await expect(page.locator('#match-id')).not.toBeVisible();
  await expect(page.locator('#match-cypher')).not.toBeVisible();

  // Switch to ID match
  await page.locator('.match-strategy-btn[data-strategy="id"]').click();
  await expect(page.locator('#match-property')).not.toBeVisible();
  await expect(page.locator('#match-id')).toBeVisible();
  await expect(page.locator('#match-cypher')).not.toBeVisible();

  // Switch to Cypher match
  await page.locator('.match-strategy-btn[data-strategy="cypher"]').click();
  await expect(page.locator('#match-property')).not.toBeVisible();
  await expect(page.locator('#match-id')).not.toBeVisible();
  await expect(page.locator('#match-cypher')).toBeVisible();

  // Switch back to Property match
  await page.locator('.match-strategy-btn[data-strategy="property"]').click();
  await expect(page.locator('#match-property')).toBeVisible();
  await expect(page.locator('#match-id')).not.toBeVisible();
  await expect(page.locator('#match-cypher')).not.toBeVisible();
});

test('can add and remove relationship properties', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/links`);
  await page.waitForLoadState('networkidle');

  await page.getByTestId('new-link-btn').click();

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
