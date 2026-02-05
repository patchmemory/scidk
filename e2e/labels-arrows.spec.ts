import { test, expect } from '@playwright/test';

/**
 * E2E tests for Arrows.app import/export functionality on Labels page.
 */

/**
 * Helper function to find a label by name in the label list
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

/**
 * Helper to clean up test labels
 */
async function deleteLabelIfExists(page: any, labelName: string) {
  const label = await findLabelByName(page, labelName);
  if (label) {
    await label.click();
    await page.waitForTimeout(300);

    // Handle delete confirmation dialog
    page.once('dialog', async (dialog) => {
      await dialog.accept();
    });

    const deleteBtn = page.getByTestId('delete-label-btn');
    if ((await deleteBtn.isVisible()) && (await deleteBtn.isEnabled())) {
      await deleteBtn.click();
      await page.waitForTimeout(500);
    }
  }
}

test('arrows import button is visible', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Wait for the page to fully load
  await page.waitForTimeout(500);

  // Check for Arrows import button
  const importBtn = page.getByTestId('import-arrows-btn');
  await expect(importBtn).toBeVisible({ timeout: 10000 });
  await expect(importBtn).toHaveText(/Import Arrows/i);
});

test('arrows export button is visible', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);

  // Check for Arrows export button
  const exportBtn = page.getByTestId('export-arrows-btn');
  await expect(exportBtn).toBeVisible({ timeout: 10000 });
  await expect(exportBtn).toHaveText(/Export Arrows/i);
});

test('can open import modal and close it', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Click import button
  await page.getByTestId('import-arrows-btn').click();
  await page.waitForTimeout(300);

  // Verify modal is visible
  const modal = page.locator('#import-arrows-modal');
  await expect(modal).toBeVisible();

  // Check modal title
  await expect(modal.locator('.modal-title')).toHaveText(/Import Schema from Arrows\.app/i);

  // Check textarea is present
  const textarea = modal.locator('#arrows-json-input');
  await expect(textarea).toBeVisible();

  // Close modal
  const closeBtn = modal.locator('.btn-close');
  await closeBtn.click();

  // Wait for Bootstrap modal animation to complete
  await page.waitForTimeout(500);

  // Verify modal is hidden (Bootstrap adds 'show' class when visible)
  await expect(modal).not.toHaveClass(/show/);
});

test('can import schema from arrows.app JSON', async ({ page, baseURL }) => {
  const consoleMessages: { type: string; text: string }[] = [];
  page.on('console', (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Clean up any existing test labels
  await deleteLabelIfExists(page, 'E2EArrowsPerson');
  await deleteLabelIfExists(page, 'E2EArrowsCompany');

  // Click import button
  await page.getByTestId('import-arrows-btn').click();
  await page.waitForTimeout(300);

  // Prepare Arrows JSON
  const arrowsJson = JSON.stringify({
    nodes: [
      {
        id: 'n0',
        caption: 'E2EArrowsPerson',
        labels: ['E2EArrowsPerson'],
        properties: { name: 'String', age: 'Integer' },
        position: { x: 100, y: 100 },
      },
      {
        id: 'n1',
        caption: 'E2EArrowsCompany',
        labels: ['E2EArrowsCompany'],
        properties: { name: 'String' },
        position: { x: 300, y: 100 },
      },
    ],
    relationships: [
      {
        id: 'r0',
        type: 'WORKS_FOR',
        fromId: 'n0',
        toId: 'n1',
        properties: {},
      },
    ],
  });

  // Paste JSON into textarea
  const textarea = page.locator('#arrows-json-input');
  await textarea.fill(arrowsJson);
  await page.waitForTimeout(200);

  // Verify preview appears
  const preview = page.locator('#import-preview');
  await expect(preview).toBeVisible();
  await expect(page.locator('#preview-label-count')).toHaveText('2');
  await expect(page.locator('#preview-rel-count')).toHaveText('1');

  // Click import confirm button and wait for API response
  const importResponsePromise = page.waitForResponse((response) => response.url().includes('/api/labels/import/arrows'));
  await page.getByTestId('import-confirm-btn').click();
  await importResponsePromise;

  // Wait for modal animation and labels reload
  await page.waitForTimeout(2000);

  // Verify modal is closed (check for 'show' class)
  const modal = page.locator('#import-arrows-modal');
  await expect(modal).not.toHaveClass(/show/);

  // Verify labels were imported (they should be in the label list now)
  const personLabel = await findLabelByName(page, 'E2EArrowsPerson');
  expect(personLabel).not.toBeNull();

  const companyLabel = await findLabelByName(page, 'E2EArrowsCompany');
  expect(companyLabel).not.toBeNull();

  // Click on person label to verify properties and relationships
  await personLabel!.click();
  await page.waitForTimeout(300);

  // Check that properties are displayed (name, age)
  const propertiesContainer = page.getByTestId('properties-container');
  const propertiesText = await propertiesContainer.textContent();
  expect(propertiesText).toContain('name');
  expect(propertiesText).toContain('age');

  // Check that relationship is displayed (WORKS_FOR -> E2EArrowsCompany)
  const relationshipsContainer = page.getByTestId('relationships-container');
  const relationshipsText = await relationshipsContainer.textContent();
  expect(relationshipsText).toContain('WORKS_FOR');
  expect(relationshipsText).toContain('E2EArrowsCompany');

  // No console errors
  const errors = consoleMessages.filter((m) => m.type === 'error');
  expect(errors.length).toBe(0);

  // Cleanup: delete imported labels
  await deleteLabelIfExists(page, 'E2EArrowsPerson');
  await deleteLabelIfExists(page, 'E2EArrowsCompany');
});

test('can export schema to arrows.app format', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Create a test label first
  await page.getByTestId('new-label-btn').click();
  await page.waitForTimeout(200);

  const labelNameInput = page.getByTestId('label-name');
  await labelNameInput.fill('E2EExportTestLabel');

  // Add a property
  await page.getByTestId('add-property-btn').click();
  await page.waitForTimeout(100);

  const propertyRows = page.locator('.property-row');
  const firstRow = propertyRows.first();
  await firstRow.locator('input[placeholder*="name"]').fill('testField');

  // Save label
  await page.getByTestId('save-label-btn').click();
  await page.waitForTimeout(500);

  // Verify label was created
  const createdLabel = await findLabelByName(page, 'E2EExportTestLabel');
  expect(createdLabel).not.toBeNull();

  // Click export button
  // Note: This triggers a download, we just verify the button works
  const exportBtn = page.getByTestId('export-arrows-btn');
  await exportBtn.click();
  await page.waitForTimeout(500);

  // Verify no errors occurred (download should have started)
  // We can't easily verify the file contents in E2E, but we can check
  // that the page is still functional

  await expect(page.getByTestId('label-list')).toBeVisible();

  // Cleanup: delete test label
  await deleteLabelIfExists(page, 'E2EExportTestLabel');
});

test('import handles invalid JSON gracefully', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Open import modal
  await page.getByTestId('import-arrows-btn').click();
  await page.waitForTimeout(300);

  // Enter invalid JSON
  const textarea = page.locator('#arrows-json-input');
  await textarea.fill('{ invalid json');
  await page.waitForTimeout(200);

  // Preview should not appear
  const preview = page.locator('#import-preview');
  await expect(preview).not.toBeVisible();

  // Try to import (should fail gracefully)
  await page.getByTestId('import-confirm-btn').click();
  await page.waitForTimeout(500);

  // Modal should still be visible (error occurred)
  const modal = page.locator('#import-arrows-modal');
  await expect(modal).toBeVisible();

  // Close modal
  await modal.locator('.btn-close').click();
});

test('import with empty textarea shows warning', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Open import modal
  await page.getByTestId('import-arrows-btn').click();
  await page.waitForTimeout(300);

  // Leave textarea empty and try to import
  await page.getByTestId('import-confirm-btn').click();
  await page.waitForTimeout(500);

  // Modal should still be visible (nothing imported)
  const modal = page.locator('#import-arrows-modal');
  await expect(modal).toBeVisible();
});
