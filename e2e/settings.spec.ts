import { test, expect } from '@playwright/test';

/**
 * E2E tests for Settings page functionality.
 * Tests Neo4j connection, interpreter toggles, and rclone settings.
 */

test('settings page loads and displays system information', async ({ page, baseURL }) => {
  const consoleMessages: { type: string; text: string }[] = [];
  page.on('console', (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Navigate to Settings page
  await page.goto(`${base}/settings`);
  await page.waitForLoadState('networkidle');

  // Verify page loads
  await expect(page).toHaveTitle(/SciDK - Settings/i, { timeout: 10_000 });

  // Check for main sections
  await expect(page.locator('main h1')).toContainText('Settings');
  await expect(page.locator('h2').filter({ hasText: 'Neo4j Connection' })).toBeVisible();
  await expect(page.locator('h2').filter({ hasText: 'Interpreters' })).toBeVisible();
  await expect(page.locator('h2').filter({ hasText: 'Plugins' })).toBeVisible();
  await expect(page.locator('h2').filter({ hasText: 'Rclone Interpretation' })).toBeVisible();

  // Check for system info badges
  const badges = page.locator('.badge');
  await expect(badges.first()).toBeVisible();

  // Check for unexpected console errors (allow API 404s for interpreters)
  const errors = consoleMessages.filter((m) => 
    m.type === 'error' && 
    !m.text.includes('Failed to load resource') &&
    !m.text.includes('404')
  );
  expect(errors.length).toBe(0);
});

test('settings navigation link is visible in header', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Check that Settings link exists in navigation
  const settingsLink = page.getByTestId('nav-settings');
  await expect(settingsLink).toBeVisible();

  // Click it and verify we navigate to settings page
  await settingsLink.click();
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveTitle(/SciDK - Settings/i);
});

test('neo4j connection form has all required inputs', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/settings`);
  await page.waitForLoadState('networkidle');

  // Check Neo4j form inputs
  const uriInput = page.locator('#neo4j-uri');
  const userInput = page.locator('#neo4j-user');
  const dbInput = page.locator('#neo4j-db');
  const passInput = page.locator('#neo4j-pass');
  const showCheckbox = page.locator('#neo4j-pass-show');

  await expect(uriInput).toBeVisible();
  await expect(userInput).toBeVisible();
  await expect(dbInput).toBeVisible();
  await expect(passInput).toBeVisible();
  await expect(showCheckbox).toBeVisible();

  // Check buttons
  const saveButton = page.locator('#neo4j-save');
  const connectButton = page.locator('#neo4j-connect');

  await expect(saveButton).toBeVisible();
  await expect(connectButton).toBeVisible();

  // Check status indicator
  const light = page.locator('#neo4j-light');
  const statusText = page.locator('#neo4j-status-text');

  await expect(light).toBeVisible();
  await expect(statusText).toBeVisible();
});

test('neo4j password visibility toggle works', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/settings`);
  await page.waitForLoadState('networkidle');

  const passInput = page.locator('#neo4j-pass');
  const showCheckbox = page.locator('#neo4j-pass-show');

  // Password field should start as type=password
  await expect(passInput).toHaveAttribute('type', 'password');

  // Click show checkbox
  await showCheckbox.check();

  // Password field should now be type=text
  await expect(passInput).toHaveAttribute('type', 'text');

  // Uncheck to hide again
  await showCheckbox.uncheck();
  await expect(passInput).toHaveAttribute('type', 'password');
});

test('neo4j form can accept input', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/settings`);
  await page.waitForLoadState('networkidle');

  const uriInput = page.locator('#neo4j-uri');
  const userInput = page.locator('#neo4j-user');
  const dbInput = page.locator('#neo4j-db');
  const passInput = page.locator('#neo4j-pass');

  // Fill in test values
  await uriInput.fill('bolt://localhost:7687');
  await userInput.fill('testuser');
  await dbInput.fill('testdb');
  await passInput.fill('testpass');

  // Verify values
  await expect(uriInput).toHaveValue('bolt://localhost:7687');
  await expect(userInput).toHaveValue('testuser');
  await expect(dbInput).toHaveValue('testdb');
  await expect(passInput).toHaveValue('testpass');
});

test('neo4j save button sends POST request', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/settings`);
  await page.waitForLoadState('networkidle');

  // Mock the save API
  await page.route('**/api/settings/neo4j', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true })
      });
    } else {
      await route.continue();
    }
  });

  // Fill in credentials
  await page.locator('#neo4j-uri').fill('bolt://localhost:7687');
  await page.locator('#neo4j-user').fill('neo4j');
  await page.locator('#neo4j-pass').fill('password123');

  // Click save
  const saveButton = page.locator('#neo4j-save');
  await saveButton.click();

  // Wait for request to complete
  await page.waitForTimeout(500);

  // Password should be cleared after save
  await expect(page.locator('#neo4j-pass')).toHaveValue('');
});

test('neo4j test connection button works', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/settings`);
  await page.waitForLoadState('networkidle');

  // Expand advanced section
  const advancedDetails = page.locator('details').filter({ hasText: 'Advanced / Health' });
  await advancedDetails.locator('summary').click();

  // Mock the health check API
  await page.route('**/api/health/graph', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        backend: 'in_memory',
        in_memory_ok: true,
        neo4j: {
          configured: false,
          connectable: false
        }
      })
    });
  });

  // Click test button
  const testButton = page.locator('#btn-test-graph');
  await expect(testButton).toBeVisible();
  await testButton.click();

  // Wait for status to update
  await page.waitForTimeout(500);

  // Check status text was updated
  const statusText = page.locator('#graph-health-status');
  await expect(statusText).not.toBeEmpty();
  await expect(statusText).toContainText('backend=');
});

test('interpreters table loads and displays data', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Mock the interpreters API
  await page.route('**/api/interpreters?view=effective', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'csv',
          name: 'CSV Interpreter',
          globs: ['*.csv'],
          enabled: true,
          source: 'default'
        },
        {
          id: 'json',
          name: 'JSON Interpreter',
          globs: ['*.json'],
          enabled: false,
          source: 'default'
        }
      ])
    });
  });

  await page.goto(`${base}/settings`);
  await page.waitForLoadState('networkidle');

  // Wait for table to be populated
  await page.waitForTimeout(1000);

  // Check table exists
  const interpTable = page.locator('#interp-table');
  await expect(interpTable).toBeVisible();

  // Check that rows were populated
  const tbody = interpTable.locator('tbody');
  const rows = tbody.locator('tr');
  await expect(rows).toHaveCount(2);

  // Verify first interpreter
  const firstRow = rows.first();
  await expect(firstRow).toContainText('CSV Interpreter');
  await expect(firstRow).toContainText('csv');
  await expect(firstRow).toContainText('*.csv');

  // Check checkboxes
  const firstCheckbox = firstRow.locator('input[type="checkbox"]');
  await expect(firstCheckbox).toBeChecked();
});

test('interpreter toggle sends API request', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Mock the interpreters list API
  await page.route('**/api/interpreters?view=effective', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'csv',
          name: 'CSV Interpreter',
          globs: ['*.csv'],
          enabled: true,
          source: 'default'
        }
      ])
    });
  });

  // Mock the toggle API
  let toggleRequestMade = false;
  await page.route('**/api/interpreters/*/toggle', async (route) => {
    toggleRequestMade = true;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true })
    });
  });

  await page.goto(`${base}/settings`);
  await page.waitForLoadState('networkidle');

  // Wait for table to be populated
  await page.waitForTimeout(1000);

  // Find and toggle the checkbox
  const checkbox = page.locator('#interp-table input[type="checkbox"]').first();
  await checkbox.click();

  // Wait for request
  await page.waitForTimeout(500);

  // Verify the API request was made
  expect(toggleRequestMade).toBe(true);
});

test('rclone interpretation settings can be updated', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Mock the load API
  await page.route('**/api/settings/rclone-interpret', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          suggest_mount_threshold: 400,
          max_files_per_batch: 1000
        })
      });
    } else if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true })
      });
    }
  });

  await page.goto(`${base}/settings`);
  await page.waitForLoadState('networkidle');

  // Wait for settings to load
  await page.waitForTimeout(1000);

  // Check inputs
  const suggestInput = page.locator('#rc-suggest');
  const batchInput = page.locator('#rc-batch');
  const saveButton = page.locator('#rc-save');

  await expect(suggestInput).toBeVisible();
  await expect(batchInput).toBeVisible();
  await expect(saveButton).toBeVisible();

  // Verify loaded values
  await expect(suggestInput).toHaveValue('400');
  await expect(batchInput).toHaveValue('1000');

  // Change values
  await suggestInput.fill('500');
  await batchInput.fill('1500');

  // Save
  await saveButton.click();

  // Wait for save to complete
  await page.waitForTimeout(500);

  // Check for success message
  const msgSpan = page.locator('#rc-msg');
  await expect(msgSpan).toContainText('Saved');
});

test('rclone mounts section displays when feature is enabled', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/settings`);
  await page.waitForLoadState('networkidle');

  // Check for Rclone Mounts section
  const mountsSection = page.locator('h2').filter({ hasText: 'Rclone Mounts' });
  await expect(mountsSection).toBeVisible();

  // Check for mount form inputs
  const remoteInput = page.locator('#rc-remote');
  const subpathInput = page.locator('#rc-subpath');
  const nameInput = page.locator('#rc-name');
  const roCheckbox = page.locator('#rc-ro');
  const createButton = page.locator('#rc-create');

  await expect(remoteInput).toBeVisible();
  await expect(subpathInput).toBeVisible();
  await expect(nameInput).toBeVisible();
  await expect(roCheckbox).toBeVisible();
  await expect(createButton).toBeVisible();

  // Check for refresh button
  const refreshButton = page.locator('#rc-refresh');
  await expect(refreshButton).toBeVisible();

  // Check for mounts table
  const mountsTable = page.locator('#rc-table-body');
  await expect(mountsTable).toBeVisible();
});

test('settings page anchor links work for section navigation', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Navigate to interpreters section via anchor
  await page.goto(`${base}/settings#interpreters`);
  await page.waitForLoadState('networkidle');

  // Verify we're at settings page
  await expect(page).toHaveTitle(/SciDK - Settings/i);

  // Verify interpreters section is visible
  const interpretersHeading = page.locator('#interpreters');
  await expect(interpretersHeading).toBeVisible();

  // Navigate to plugins section via anchor
  await page.goto(`${base}/settings#plugins`);
  await page.waitForLoadState('networkidle');

  // Verify plugins section is visible
  const pluginsHeading = page.locator('#plugins');
  await expect(pluginsHeading).toBeVisible();
});
