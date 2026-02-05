import { test, expect } from '@playwright/test';

/**
 * E2E tests for Home page functionality.
 * Tests search, chat, and filter controls that weren't covered in existing tests.
 */

test('home page loads with all sections', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Check for main sections
  await expect(page.locator('h2').filter({ hasText: 'Recent Scans' })).toBeVisible();
  await expect(page.locator('h2').filter({ hasText: 'Summary' })).toBeVisible();
  await expect(page.locator('h2').filter({ hasText: 'Chat' })).toBeVisible();
  await expect(page.locator('h2').filter({ hasText: 'Search' })).toBeVisible();
});

test('filter reset button is present and functional', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Expand scanned sources section if it exists
  const scannenSourcesDetails = page.locator('details').filter({ hasText: 'Scanned Sources' });
  if (await scannenSourcesDetails.count() > 0) {
    await scannenSourcesDetails.locator('summary').click();

    // Check for reset button
    const resetButton = page.locator('#filter-reset');
    await expect(resetButton).toBeVisible();

    // Set some filter values
    const pathInput = page.locator('#filter-path');
    await pathInput.fill('test');

    const recursiveSelect = page.locator('#filter-recursive');
    await recursiveSelect.selectOption('true');

    // Click reset
    await resetButton.click();

    // Wait for reset to apply
    await page.waitForTimeout(300);

    // Verify filters were reset
    await expect(pathInput).toHaveValue('');
    await expect(recursiveSelect).toHaveValue('');
  }
});

test('home chat form is present and functional', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Check for chat form
  const chatForm = page.locator('#chat-form-home');
  await expect(chatForm).toBeVisible();

  // Check for chat input
  const chatInput = page.locator('#chat-input-home');
  await expect(chatInput).toBeVisible();

  // Check for submit button
  const submitButton = chatForm.locator('button[type="submit"]');
  await expect(submitButton).toBeVisible();
});

test('home chat input accepts text', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(base);
  await page.waitForLoadState('networkidle');

  const chatInput = page.locator('#chat-input-home');

  // Type a message
  await chatInput.fill('What datasets do I have?');
  await expect(chatInput).toHaveValue('What datasets do I have?');
});

test('home chat form submits to API', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Mock the chat API
  await page.route('**/api/chat', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        history: [
          { role: 'user', content: 'Test message' },
          { role: 'assistant', content: 'Test response' }
        ]
      })
    });
  });

  const chatForm = page.locator('#chat-form-home');
  const chatInput = page.locator('#chat-input-home');
  const chatHistory = page.locator('#chat-history-home');

  // Submit a message
  await chatInput.fill('Test message');
  const submitButton = chatForm.locator('button[type="submit"]');
  await submitButton.click();

  // Wait for history to update
  await page.waitForTimeout(1000);

  // Verify history has content
  const historyContent = await chatHistory.textContent();
  expect(historyContent).toContain('Test message');
  expect(historyContent).toContain('Test response');

  // Verify input was cleared
  await expect(chatInput).toHaveValue('');
});

test('search form is present and functional', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Check for search form
  const searchForm = page.locator('#search-form');
  await expect(searchForm).toBeVisible();

  // Check for search input
  const searchInput = page.locator('#search-input');
  await expect(searchInput).toBeVisible();
  await expect(searchInput).toHaveAttribute('placeholder', /Search by filename/i);

  // Check for submit button
  const submitButton = searchForm.locator('button[type="submit"]');
  await expect(submitButton).toBeVisible();
});

test('search input accepts text', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(base);
  await page.waitForLoadState('networkidle');

  const searchInput = page.locator('#search-input');

  // Type a search query
  await searchInput.fill('test.csv');
  await expect(searchInput).toHaveValue('test.csv');

  // Clear and type another query
  await searchInput.fill('python_code');
  await expect(searchInput).toHaveValue('python_code');
});

test('search form submits to /api/search endpoint', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Track API request
  let searchRequestMade = false;
  let searchQuery = '';
  page.on('request', (request) => {
    if (request.url().includes('/api/search')) {
      searchRequestMade = true;
      const url = new URL(request.url());
      searchQuery = url.searchParams.get('q') || '';
    }
  });

  // Mock the search API
  await page.route('**/api/search*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: '123',
          filename: 'test.csv',
          path: '/data/test.csv',
          extension: 'csv',
          matched_on: ['filename']
        }
      ])
    });
  });

  const searchForm = page.locator('#search-form');
  const searchInput = page.locator('#search-input');
  const resultsDiv = page.locator('#search-results');

  // Submit a search
  await searchInput.fill('test.csv');
  const searchButton = searchForm.locator('button[type="submit"]');
  await searchButton.click();

  // Wait for results
  await page.waitForTimeout(1000);

  // Verify API request was made
  expect(searchRequestMade).toBe(true);
  expect(searchQuery).toBe('test.csv');

  // Verify results are displayed
  const resultsContent = await resultsDiv.textContent();
  expect(resultsContent).toContain('test.csv');
});

test('search form displays "No results" when API returns empty', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Mock empty search results
  await page.route('**/api/search*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([])
    });
  });

  const searchForm = page.locator('#search-form');
  const searchInput = page.locator('#search-input');
  const resultsDiv = page.locator('#search-results');

  // Submit a search
  await searchInput.fill('nonexistent.xyz');
  const searchButton = searchForm.locator('button[type="submit"]');
  await searchButton.click();

  // Wait for results
  await page.waitForTimeout(1000);

  // Verify "No results" message
  const resultsContent = await resultsDiv.textContent();
  expect(resultsContent).toContain('No results');
});

test('search form clears results when empty query submitted', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(base);
  await page.waitForLoadState('networkidle');

  const searchForm = page.locator('#search-form');
  const searchInput = page.locator('#search-input');
  const resultsDiv = page.locator('#search-results');

  // Submit empty search
  await searchInput.fill('');
  await searchForm.evaluate((form) => (form as HTMLFormElement).submit());

  // Wait briefly
  await page.waitForTimeout(300);

  // Verify results are cleared
  const resultsContent = await resultsDiv.textContent();
  expect(resultsContent).toBe('');
});

test('recent scans section shows scans with links to Files page', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(base);
  await page.waitForLoadState('networkidle');

  const recentScansSection = page.locator('[data-testid="home-recent-scans"]');
  await expect(recentScansSection).toBeVisible();

  // Check for either scans list or "No scans yet" message
  const scansList = recentScansSection.locator('ul');
  const noScansMessage = recentScansSection.locator('p.small');

  const hasScans = await scansList.count() > 0;
  const hasNoScansMessage = await noScansMessage.count() > 0;

  // Should have either scans or no scans message
  expect(hasScans || hasNoScansMessage).toBe(true);

  // If there's a no scans message, verify it has link to Files
  if (hasNoScansMessage) {
    const filesLink = noScansMessage.locator('a[href="/datasets"]');
    if (await filesLink.count() > 0) {
      await expect(filesLink).toBeVisible();
    }
  }

  // If there are scans, verify they have links with scan_id parameter
  if (hasScans) {
    const firstScanLink = scansList.locator('li a').first();
    if (await firstScanLink.count() > 0) {
      const href = await firstScanLink.getAttribute('href');
      expect(href).toContain('/datasets?scan_id=');
    }
  }
});

test('home page has background scans section with link to Files', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Check for Background Scans section
  const bgScansHeading = page.locator('h2').filter({ hasText: 'Background Scans' });
  await expect(bgScansHeading).toBeVisible();

  // Verify link to Files page
  const filesLink = page.locator('a[href="/datasets"]').last();
  await expect(filesLink).toBeVisible();
});
