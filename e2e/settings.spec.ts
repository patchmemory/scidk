import { test, expect } from '@playwright/test';

/**
 * E2E tests for Settings page functionality.
 * Tests Neo4j connection, interpreter toggles, and rclone settings.
 *
 * TODO: Update tests after settings modularization (task:ui/settings/modularization)
 * Settings sections have been extracted into separate partial templates:
 * - settings/_general.html, _neo4j.html, _chat.html, _interpreters.html,
 *   _plugins.html, _rclone.html, _integrations.html
 * The main index.html now uses {% include %} directives to compose the page.
 */

test('settings page loads and displays system information', async ({ page, baseURL }) => {
  const consoleMessages: { type: string; text: string }[] = [];
  page.on('console', (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Navigate to Settings page
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Verify page loads (Settings is now the landing page at /)
  await expect(page).toHaveTitle(/-SciDK->/i, { timeout: 10_000 });

  // Check for sidebar navigation
  await expect(page.locator('.settings-sidebar')).toBeVisible();
  await expect(page.locator('.settings-sidebar-item[data-section="general"]')).toBeVisible();
  await expect(page.locator('.settings-sidebar-item[data-section="neo4j"]')).toBeVisible();
  await expect(page.locator('.settings-sidebar-item[data-section="interpreters"]')).toBeVisible();

  // Check that General section is active by default
  const generalSection = page.locator('#general-section');
  await expect(generalSection).toBeVisible();
  await expect(generalSection.locator('h1')).toHaveText('General');

  // Check for system info badges
  const badges = generalSection.locator('.badge');
  await expect(badges.first()).toBeVisible();

  // Check for unexpected console errors (allow API 404s for interpreters)
  const errors = consoleMessages.filter((m) =>
    m.type === 'error' &&
    !m.text.includes('Failed to load resource') &&
    !m.text.includes('404')
  );
  expect(errors.length).toBe(0);
});

// OBSOLETE: Settings is now the landing page (/) - no separate nav link needed
test.skip('settings navigation link is visible in header', async ({ page, baseURL }) => {
  // This test is obsolete because Settings page is now the landing page at /
  // There is no separate "Settings" navigation link anymore
});

test('neo4j connection form has all required inputs', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Neo4j section
  await page.locator('.settings-sidebar-item[data-section="neo4j"]').click();
  await page.waitForTimeout(200);

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
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Neo4j section
  await page.locator('.settings-sidebar-item[data-section="neo4j"]').click();
  await page.waitForTimeout(200);

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
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Neo4j section
  await page.locator('.settings-sidebar-item[data-section="neo4j"]').click();
  await page.waitForTimeout(200);

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
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Neo4j section
  await page.locator('.settings-sidebar-item[data-section="neo4j"]').click();
  await page.waitForTimeout(200);

  // Mock the save API
  await page.route('**/api//neo4j', async (route) => {
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
  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Neo4j section
  await page.locator('.settings-sidebar-item[data-section="neo4j"]').click();
  await page.waitForTimeout(200);

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

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Interpreters section
  await page.locator('.settings-sidebar-item[data-section="interpreters"]').click();
  await page.waitForTimeout(200);

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

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Interpreters section
  await page.locator('.settings-sidebar-item[data-section="interpreters"]').click();
  await page.waitForTimeout(200);

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

// TODO: Backend needs GET /api/settings/rclone-interpret endpoint before this test can work
test.skip('rclone interpretation settings can be updated', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Mock the load API
  await page.route('**/api//rclone-interpret', async (route) => {
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

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Rclone section
  await page.locator('.settings-sidebar-item[data-section="rclone"]').click();
  await page.waitForTimeout(200);

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

test('rclone section displays interpretation settings', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Navigate to Rclone section
  await page.locator('.settings-sidebar-item[data-section="rclone"]').click();
  await page.waitForTimeout(200);

  // Check for Rclone section header
  const rcloneSection = page.locator('#rclone-section');
  await expect(rcloneSection).toBeVisible();
  await expect(rcloneSection.locator('h1')).toHaveText('Rclone');

  // Check for Interpretation subsection
  const interpretSection = rcloneSection.locator('h2').filter({ hasText: 'Interpretation' });
  await expect(interpretSection).toBeVisible();

  // Check for interpretation form inputs
  const suggestInput = page.locator('#rc-suggest');
  const batchInput = page.locator('#rc-batch');
  const saveButton = page.locator('#rc-save');

  await expect(suggestInput).toBeVisible();
  await expect(batchInput).toBeVisible();
  await expect(saveButton).toBeVisible();
});

test('settings page sidebar navigation works', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(`${base}/`);
  await page.waitForLoadState('networkidle');

  // Verify we're at settings page (now the landing page)
  await expect(page).toHaveTitle(/-SciDK->/i);

  // General section should be active by default
  const generalSection = page.locator('#general-section');
  await expect(generalSection).toBeVisible();
  await expect(generalSection).toHaveClass(/active/);

  // Click on Interpreters sidebar item
  const interpretersSidebarItem = page.locator('.settings-sidebar-item[data-section="interpreters"]');
  await interpretersSidebarItem.click();
  await page.waitForTimeout(200);

  // Verify interpreters section is now visible and active
  const interpretersSection = page.locator('#interpreters-section');
  await expect(interpretersSection).toBeVisible();
  await expect(interpretersSection).toHaveClass(/active/);
  await expect(interpretersSidebarItem).toHaveClass(/active/);

  // Click on Plugins sidebar item
  const pluginsSidebarItem = page.locator('.settings-sidebar-item[data-section="plugins"]');
  await pluginsSidebarItem.click();
  await page.waitForTimeout(200);

  // Verify plugins section is now visible and active
  const pluginsSection = page.locator('#plugins-section');
  await expect(pluginsSection).toBeVisible();
  await expect(pluginsSection).toHaveClass(/active/);
  await expect(pluginsSidebarItem).toHaveClass(/active/);

  // Verify interpreters section is no longer active
  await expect(interpretersSection).not.toHaveClass(/active/);
});
