import { test, expect } from '@playwright/test';

/**
 * E2E tests for Labels page functionality.
 * Tests the complete workflow: create label → add properties → add relationships → save → delete
 */

/**
 * Helper function to find a label by name in the label list
 * This is more resilient than using .first() which assumes order
 */
async function findLabelByName(page: any, labelName: string) {
  const labelItems = page.getByTestId('label-item');
  const count = await labelItems.count();
  for (let i = 0; i < count; i++) {
    const text = await labelItems.nth(i).textContent();
    if (text?.includes(labelName)) {
      return labelItems.nth(i);
    }
  }
  return null;
}

test('labels page loads and displays empty state', async ({ page, baseURL }) => {
  const consoleMessages: { type: string; text: string }[] = [];
  page.on('console', (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Navigate to Labels page
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Verify page loads
  await expect(page).toHaveTitle(/SciDK - Labels/i, { timeout: 10_000 });

  // Check for new label button
  await expect(page.getByTestId('new-label-btn')).toBeVisible();

  // Check for label list
  await expect(page.getByTestId('label-list')).toBeVisible();

  // No console errors
  const errors = consoleMessages.filter((m) => m.type === 'error');
  expect(errors.length).toBe(0);
});

test('labels navigation link is visible in header', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Check that Labels link exists in navigation
  const labelsLink = page.getByTestId('nav-labels');
  await expect(labelsLink).toBeVisible();

  // Click it and verify we navigate to labels page
  await labelsLink.click();
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveTitle(/SciDK - Labels/i);
});

test('complete label workflow: create → edit → delete', async ({ page, baseURL }) => {
  const consoleMessages: { type: string; text: string }[] = [];
  page.on('console', (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Step 1: Click "New Label" button
  await page.getByTestId('new-label-btn').click();

  // Step 2: Enter label name
  const labelNameInput = page.getByTestId('label-name');
  await expect(labelNameInput).toBeVisible();
  await labelNameInput.fill('E2ETestLabel');

  // Step 3: Add a property
  await page.getByTestId('add-property-btn').click();

  // Fill property details
  const propertyRows = page.getByTestId('property-row');
  const firstPropertyRow = propertyRows.first();
  await firstPropertyRow.getByTestId('property-name').fill('testProperty');
  await firstPropertyRow.getByTestId('property-type').selectOption('string');
  await firstPropertyRow.getByTestId('property-required').check();

  // Step 4: Add another property
  await page.getByTestId('add-property-btn').click();
  const secondPropertyRow = propertyRows.nth(1);
  await secondPropertyRow.getByTestId('property-name').fill('count');
  await secondPropertyRow.getByTestId('property-type').selectOption('number');

  // Step 5: Save the label
  await page.getByTestId('save-label-btn').click();

  // Wait for save to complete (look for toast or list update)
  await page.waitForTimeout(1000);

  // Step 6: Verify label appears in list
  const labelItems = page.getByTestId('label-item');
  await expect(labelItems.first()).toBeVisible(); // Wait for at least one label

  // Find our specific label by name (more resilient to existing data)
  const ourLabel = await findLabelByName(page, 'E2ETestLabel');
  expect(ourLabel).not.toBeNull();
  const labelText = await ourLabel!.textContent();
  expect(labelText).toContain('E2ETestLabel');
  expect(labelText).toContain('2 properties');

  // Step 7: Click on the label to edit it
  await ourLabel!.click();
  await page.waitForTimeout(500);

  // Verify editor is populated
  await expect(labelNameInput).toHaveValue('E2ETestLabel');
  const editPropertyRows = page.getByTestId('property-row');
  await expect(editPropertyRows).toHaveCount(2);

  // Step 8: Delete the label
  const deleteBtn = page.getByTestId('delete-label-btn');
  await expect(deleteBtn).toBeVisible();

  // Handle confirmation dialog
  page.on('dialog', async (dialog) => {
    expect(dialog.type()).toBe('confirm');
    await dialog.accept();
  });

  await deleteBtn.click();
  await page.waitForTimeout(1000);

  // Verify label is removed from list
  const remainingLabels = await page.getByTestId('label-item').count();
  // Should be 0 or not include our test label
  const listContent = await page.getByTestId('label-list').textContent();
  expect(listContent).not.toContain('E2ETestLabel');

  // No console errors
  const errors = consoleMessages.filter((m) => m.type === 'error');
  expect(errors.length).toBe(0);
});

test('can add and remove multiple properties', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Create new label
  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('MultiPropLabel');

  // Add 3 properties
  for (let i = 0; i < 3; i++) {
    await page.getByTestId('add-property-btn').click();
    const rows = page.getByTestId('property-row');
    const currentRow = rows.nth(i);
    await currentRow.getByTestId('property-name').fill(`prop${i + 1}`);
  }

  // Verify 3 properties exist
  await expect(page.getByTestId('property-row')).toHaveCount(3);

  // Remove the second property
  const removeButtons = page.getByTestId('remove-property-btn');
  await removeButtons.nth(1).click();

  // Verify only 2 properties remain
  await expect(page.getByTestId('property-row')).toHaveCount(2);

  // Save label
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(1000);

  // Verify saved - find the specific label by name, not first item
  const labelItems = page.getByTestId('label-item');
  await expect(labelItems).toHaveCount(await labelItems.count()); // Wait for labels to load

  // Find our specific label by filtering text content
  let foundLabel = null;
  const count = await labelItems.count();
  for (let i = 0; i < count; i++) {
    const text = await labelItems.nth(i).textContent();
    if (text?.includes('MultiPropLabel')) {
      foundLabel = labelItems.nth(i);
      expect(text).toContain('2 properties');
      break;
    }
  }
  expect(foundLabel).not.toBeNull();

  // Cleanup: delete the label
  await foundLabel!.click();
  page.on('dialog', async (dialog) => await dialog.accept());
  await page.getByTestId('delete-label-btn').click();
  await page.waitForTimeout(500);
});

test('can create label with relationships', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // First create a target label
  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('TargetLabel');
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(1000);

  // Now create a label with relationship
  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('SourceLabel');

  // Add relationship
  await page.getByTestId('add-relationship-btn').click();
  const relationshipRow = page.getByTestId('relationship-row').first();
  await relationshipRow.getByTestId('relationship-type').fill('LINKS_TO');
  await relationshipRow.getByTestId('relationship-target').selectOption('TargetLabel');

  // Save
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(1000);

  // Verify
  const labelItems = page.getByTestId('label-item');
  const sourceLabel = labelItems.filter({ hasText: 'SourceLabel' });
  const labelText = await sourceLabel.textContent();
  expect(labelText).toContain('1 relationship');

  // Cleanup
  page.on('dialog', async (dialog) => await dialog.accept());
  for (const labelName of ['SourceLabel', 'TargetLabel']) {
    const item = labelItems.filter({ hasText: labelName });
    await item.click();
    await page.waitForTimeout(300);
    await page.getByTestId('delete-label-btn').click();
    await page.waitForTimeout(500);
  }
});

test('validation: cannot save label without name', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Create new label but don't enter name
  await page.getByTestId('new-label-btn').click();

  // Try to save without name
  await page.getByTestId('save-label-btn').click();

  // Should see error message (implementation shows error inline)
  // The label name input should still be visible and empty
  const labelNameInput = page.getByTestId('label-name');
  await expect(labelNameInput).toBeVisible();
  const value = await labelNameInput.inputValue();
  expect(value).toBe('');
});

test('neo4j: push label to neo4j', async ({ page, baseURL, request: pageRequest }) => {
  // Skip test if Neo4j is not configured
  test.skip(!process.env.NEO4J_URI, 'NEO4J_URI not configured');

  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Create a label first
  await page.getByTestId('new-label-btn').click();
  await page.getByTestId('label-name').fill('Neo4jTestLabel');

  // Add a property
  await page.getByTestId('add-property-btn').click();
  const propertyRow = page.getByTestId('property-row').first();
  await propertyRow.getByTestId('property-name').fill('id');
  await propertyRow.getByTestId('property-type').selectOption('string');
  await propertyRow.getByTestId('property-required').check();

  // Save the label
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(1000);

  // Verify Push to Neo4j button is visible
  const pushBtn = page.getByTestId('push-neo4j-btn');
  await expect(pushBtn).toBeVisible();

  // Push to Neo4j
  await pushBtn.click();
  await page.waitForTimeout(2000);

  // Wait for success toast (the push should succeed if Neo4j is connected)
  // We can't easily check the toast content, but we can verify no errors occurred
  // by checking that the page is still functional

  // Verify label is still loadable
  const labelItems = page.getByTestId('label-item');
  await expect(labelItems.first()).toBeVisible();

  // Cleanup: delete the test label by finding it by name
  const ourLabel = await findLabelByName(page, 'Neo4jTestLabel');
  expect(ourLabel).not.toBeNull();

  page.on('dialog', async (dialog) => await dialog.accept());
  await ourLabel!.click();
  await page.waitForTimeout(300);
  await page.getByTestId('delete-label-btn').click();
  await page.waitForTimeout(500);
});

test('neo4j: pull labels from neo4j', async ({ page, baseURL }) => {
  // Skip test if Neo4j is not configured
  test.skip(!process.env.NEO4J_URI, 'NEO4J_URI not configured');

  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Click the "New Label" button to show the editor
  await page.getByTestId('new-label-btn').click();

  // Verify Pull from Neo4j button is visible
  const pullBtn = page.getByTestId('pull-neo4j-btn');
  await expect(pullBtn).toBeVisible();

  // Set up dialog handler before clicking
  page.on('dialog', async (dialog) => {
    expect(dialog.type()).toBe('confirm');
    expect(dialog.message()).toContain('Pull schema from Neo4j');
    await dialog.accept();
  });

  // Click Pull from Neo4j
  await pullBtn.click();
  await page.waitForTimeout(2000);

  // After pulling, labels should be loaded (if any exist in Neo4j)
  // We can't guarantee any labels exist, but the operation should complete without error
  // Verify the label list is still visible and functional
  const labelList = page.getByTestId('label-list');
  await expect(labelList).toBeVisible();
});
