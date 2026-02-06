import { test, expect } from '@playwright/test';

test.describe('Settings - Fuzzy Matching', () => {
  test.beforeEach(async ({ page, baseURL }) => {
    const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
    await page.goto(`${base}/settings#links`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForSelector('[data-testid="fuzzy-algorithm"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(200); // Small delay for JS initialization
  });

  test('should display fuzzy matching form @smoke', async ({ page }) => {
    // Check all form fields are present
    await expect(page.locator('[data-testid="fuzzy-algorithm"]')).toBeVisible();
    await expect(page.locator('[data-testid="fuzzy-threshold"]')).toBeVisible();
    await expect(page.locator('[data-testid="fuzzy-case-sensitive"]')).toBeVisible();
    await expect(page.locator('[data-testid="fuzzy-normalize-whitespace"]')).toBeVisible();
    await expect(page.locator('[data-testid="fuzzy-strip-punctuation"]')).toBeVisible();
    await expect(page.locator('[data-testid="btn-save-fuzzy-settings"]')).toBeVisible();
    await expect(page.locator('[data-testid="btn-reset-fuzzy-settings"]')).toBeVisible();
  });

  test('should load default settings @smoke', async ({ page }) => {
    // Default algorithm should be Levenshtein
    const algorithmValue = await page.locator('[data-testid="fuzzy-algorithm"]').inputValue();
    expect(algorithmValue).toBe('levenshtein');

    // Default threshold should be 80%
    const thresholdValue = await page.locator('[data-testid="fuzzy-threshold"]').inputValue();
    expect(parseInt(thresholdValue)).toBe(80);

    // Normalize whitespace should be checked by default
    await expect(page.locator('[data-testid="fuzzy-normalize-whitespace"]')).toBeChecked();

    // Strip punctuation should be checked by default
    await expect(page.locator('[data-testid="fuzzy-strip-punctuation"]')).toBeChecked();
  });

  test('should update threshold value display @smoke', async ({ page }) => {
    const thresholdSlider = page.locator('[data-testid="fuzzy-threshold"]');
    const thresholdDisplay = page.locator('#fuzzy-threshold-value');

    // Change threshold
    await thresholdSlider.fill('75');

    // Display should update
    await expect(thresholdDisplay).toContainText('75');
  });

  test('should save fuzzy matching settings @smoke', async ({ page }) => {
    // Change settings
    await page.selectOption('[data-testid="fuzzy-algorithm"]', 'jaro_winkler');
    await page.locator('[data-testid="fuzzy-threshold"]').fill('85');
    await page.locator('[data-testid="fuzzy-case-sensitive"]').check();

    // Save settings
    await page.click('[data-testid="btn-save-fuzzy-settings"]');

    // Wait for success message
    await expect(page.locator('#fuzzy-settings-message')).toContainText('saved successfully', { timeout: 5000 });

    // Reload page to verify persistence
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Check that settings persisted
    const algorithmValue = await page.locator('[data-testid="fuzzy-algorithm"]').inputValue();
    expect(algorithmValue).toBe('jaro_winkler');

    const thresholdValue = await page.locator('[data-testid="fuzzy-threshold"]').inputValue();
    expect(parseInt(thresholdValue)).toBe(85);

    await expect(page.locator('[data-testid="fuzzy-case-sensitive"]')).toBeChecked();
  });

  test('should show phonetic settings when algorithm is phonetic', async ({ page }) => {
    const phoneticSettings = page.locator('#fuzzy-phonetic-settings');

    // Initially hidden
    await expect(phoneticSettings).toBeHidden();

    // Select phonetic algorithm
    await page.selectOption('[data-testid="fuzzy-algorithm"]', 'phonetic');

    // Phonetic settings should now be visible
    await expect(phoneticSettings).toBeVisible();
    await expect(page.locator('[data-testid="fuzzy-phonetic-enabled"]')).toBeChecked();
  });

  test('should reset to defaults @smoke', async ({ page }) => {
    // Change settings
    await page.selectOption('[data-testid="fuzzy-algorithm"]', 'exact');
    await page.locator('[data-testid="fuzzy-threshold"]').fill('50');
    await page.locator('[data-testid="fuzzy-normalize-whitespace"]').uncheck();

    // Save changes
    await page.click('[data-testid="btn-save-fuzzy-settings"]');
    await page.waitForSelector('#fuzzy-settings-message:has-text("saved")');

    // Reset to defaults
    page.on('dialog', dialog => dialog.accept()); // Accept confirmation
    await page.click('[data-testid="btn-reset-fuzzy-settings"]');

    // Wait for reset message
    await expect(page.locator('#fuzzy-settings-message')).toContainText('Reset to defaults', { timeout: 5000 });

    // Check defaults are restored
    const algorithmValue = await page.locator('[data-testid="fuzzy-algorithm"]').inputValue();
    expect(algorithmValue).toBe('levenshtein');

    const thresholdValue = await page.locator('[data-testid="fuzzy-threshold"]').inputValue();
    expect(parseInt(thresholdValue)).toBe(80);

    await expect(page.locator('[data-testid="fuzzy-normalize-whitespace"]')).toBeChecked();
  });

  test('should display architecture info panel', async ({ page }) => {
    // Check that the architecture explanation is visible
    await expect(page.locator('text=Hybrid Matching Architecture')).toBeVisible();
    await expect(page.locator('text=Phase 1 (Client-Side)')).toBeVisible();
    await expect(page.locator('text=Phase 2 (Server-Side)')).toBeVisible();
    await expect(page.locator('text=Neo4j APOC')).toBeVisible();
  });
});
