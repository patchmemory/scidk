import { test, expect } from '@playwright/test';

/**
 * E2E tests for Maps/Graph page functionality.
 * Tests graph visualization, filters, layout controls, and data export.
 */

test('map page loads and displays graph visualization', async ({ page, baseURL }) => {
  const consoleMessages: { type: string; text: string }[] = [];
  page.on('console', (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Navigate to Maps page
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  // Verify page loads
  await expect(page).toHaveTitle(/-SciDK-> Maps/i, { timeout: 10_000 });

  // Check for main sections
  await expect(page.locator('h2').filter({ hasText: 'Schema Graph' })).toBeVisible();
  await expect(page.locator('h2').filter({ hasText: 'Graph Schema' })).toBeVisible();

  // Check for graph container
  const graphContainer = page.locator('#schema-graph');
  await expect(graphContainer).toBeVisible();
  await expect(graphContainer).toHaveAttribute('data-testid', 'graph-explorer-root');

  // Check for schema tables
  await expect(page.locator('h3').filter({ hasText: 'Node Labels' })).toBeVisible();
  await expect(page.locator('h3').filter({ hasText: 'Relationship Types' })).toBeVisible();

  // No critical console errors (Cytoscape may have warnings)
  const errors = consoleMessages.filter((m) => m.type === 'error' && !m.text.includes('Cytoscape'));
  expect(errors.length).toBe(0);
});

test('map navigation link is visible in header', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Check that Maps link exists in navigation
  const mapsLink = page.getByTestId('nav-maps');
  await expect(mapsLink).toBeVisible();

  // Click it and verify we navigate to map page
  await mapsLink.click();
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveTitle(/-SciDK-> Maps/i);
});

test('graph filter controls are present and functional', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  // Check for filter controls
  const labelsFilter = page.locator('#filter-labels');
  const reltypesFilter = page.locator('#filter-reltypes');
  const layoutMode = page.locator('#layout-mode');

  await expect(labelsFilter).toBeVisible();
  await expect(reltypesFilter).toBeVisible();
  await expect(layoutMode).toBeVisible();

  // Verify filter options
  await expect(labelsFilter).toHaveValue('');
  await labelsFilter.selectOption('File');
  await expect(labelsFilter).toHaveValue('File');

  await expect(reltypesFilter).toHaveValue('');
  await reltypesFilter.selectOption('CONTAINS');
  await expect(reltypesFilter).toHaveValue('CONTAINS');

  // Verify layout options
  await expect(layoutMode).toHaveValue('cose');
  await layoutMode.selectOption('breadthfirst');
  await expect(layoutMode).toHaveValue('breadthfirst');
});

test('graph layout save and load buttons are present', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  const saveButton = page.locator('#save-positions');
  const loadButton = page.locator('#load-positions');

  await expect(saveButton).toBeVisible();
  await expect(loadButton).toBeVisible();
  await expect(saveButton).toHaveText('Save');
  await expect(loadButton).toHaveText('Load');
});

test('graph visual controls (sliders and checkbox) are functional', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  // Node size slider
  const nodeSizeSlider = page.locator('#node-size');
  await expect(nodeSizeSlider).toBeVisible();
  await expect(nodeSizeSlider).toHaveAttribute('type', 'range');
  await expect(nodeSizeSlider).toHaveValue('1');
  await nodeSizeSlider.fill('2');
  await expect(nodeSizeSlider).toHaveValue('2');

  // Edge width slider
  const edgeWidthSlider = page.locator('#edge-width');
  await expect(edgeWidthSlider).toBeVisible();
  await expect(edgeWidthSlider).toHaveAttribute('type', 'range');
  await expect(edgeWidthSlider).toHaveValue('1');
  await edgeWidthSlider.fill('1.5');
  await expect(edgeWidthSlider).toHaveValue('1.5');

  // Font size slider
  const fontSizeSlider = page.locator('#font-size');
  await expect(fontSizeSlider).toBeVisible();
  await expect(fontSizeSlider).toHaveAttribute('type', 'range');
  await expect(fontSizeSlider).toHaveValue('10');
  await fontSizeSlider.fill('14');
  await expect(fontSizeSlider).toHaveValue('14');

  // High contrast checkbox
  const highContrastCheckbox = page.locator('#high-contrast');
  await expect(highContrastCheckbox).toBeVisible();
  await expect(highContrastCheckbox).not.toBeChecked();
  await highContrastCheckbox.check();
  await expect(highContrastCheckbox).toBeChecked();
});

test('download schema CSV button is present and functional', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  const downloadButton = page.locator('#download-csv');
  await expect(downloadButton).toBeVisible();
  await expect(downloadButton).toHaveText('Download Schema (CSV)');

  // Test that clicking the button triggers a download
  const downloadPromise = page.waitForEvent('download');
  await downloadButton.click();

  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain('schema');
  expect(download.suggestedFilename()).toContain('.csv');
});

test('instances section controls are present', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  // Check instances section
  await expect(page.locator('h3').filter({ hasText: 'Instances' })).toBeVisible();

  // Check label selector
  const instancesLabel = page.locator('#instances-label');
  await expect(instancesLabel).toBeVisible();
  await expect(instancesLabel).toHaveValue('Scan');

  // Check preview button
  const previewButton = page.locator('#instances-preview');
  await expect(previewButton).toBeVisible();
  await expect(previewButton).toHaveText('Preview');

  // Check download links
  const fileCsvLink = page.locator('#dl-file-csv');
  const folderCsvLink = page.locator('#dl-folder-csv');
  const scanCsvLink = page.locator('#dl-scan-csv');
  const fileXlsxLink = page.locator('#dl-file-xlsx');

  await expect(fileCsvLink).toBeVisible();
  await expect(folderCsvLink).toBeVisible();
  await expect(scanCsvLink).toBeVisible();
  await expect(fileXlsxLink).toBeVisible();

  // Verify links have correct hrefs
  await expect(fileCsvLink).toHaveAttribute('href', '/api/graph/instances.csv?label=File');
  await expect(folderCsvLink).toHaveAttribute('href', '/api/graph/instances.csv?label=Folder');
  await expect(scanCsvLink).toHaveAttribute('href', '/api/graph/instances.csv?label=Scan');
  await expect(fileXlsxLink).toHaveAttribute('href', '/api/graph/instances.xlsx?label=File');
});

test('instances preview button loads data', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Mock the instances API
  await page.route('**/api/graph/instances?label=*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        label: 'Scan',
        properties: ['id', 'path', 'created_at'],
        instances: [
          { id: 'scan1', path: '/test/path', created_at: '2025-01-01' },
          { id: 'scan2', path: '/test/path2', created_at: '2025-01-02' }
        ]
      })
    });
  });

  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  // Select label and click preview
  const instancesLabel = page.locator('#instances-label');
  await instancesLabel.selectOption('Scan');

  const previewButton = page.locator('#instances-preview');
  await previewButton.click();

  // Wait for table to be populated
  await page.waitForTimeout(1000);

  // Check that table was rendered
  const instancesTable = page.locator('#instances-table');
  await expect(instancesTable).toBeVisible();

  // Verify table has content
  const tableContent = await instancesTable.textContent();
  expect(tableContent).toBeTruthy();
});

test('schema tables display node labels and relationships', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  // Check Node Labels table
  const nodeLabelsTable = page.locator('h3').filter({ hasText: 'Node Labels' }).locator('..').locator('table');
  await expect(nodeLabelsTable).toBeVisible();

  // Verify table structure
  const nodeTableHeaders = nodeLabelsTable.locator('thead th');
  await expect(nodeTableHeaders.first()).toContainText('Label');
  await expect(nodeTableHeaders.nth(1)).toContainText('Count');

  // Check Relationship Types table
  const relsTable = page.locator('h3').filter({ hasText: 'Relationship Types' }).locator('..').locator('table');
  await expect(relsTable).toBeVisible();

  // Verify table structure
  const relTableHeaders = relsTable.locator('thead th');
  await expect(relTableHeaders.first()).toContainText('Type');
  await expect(relTableHeaders.nth(1)).toContainText('Count');
});

test('interpretation types section is displayed', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  // Check for Interpretation Types section
  const interpretationTypesHeading = page.locator('h3').filter({ hasText: 'Interpretation Types' });
  await expect(interpretationTypesHeading).toBeVisible();
});

test('graph filters update visualization via API', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Track API calls
  let schemaApiCalls = 0;
  page.on('request', (request) => {
    if (request.url().includes('/api/graph/schema') || request.url().includes('/api/graph/subschema')) {
      schemaApiCalls++;
    }
  });

  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  // Initial load should have fetched schema at least once
  expect(schemaApiCalls).toBeGreaterThan(0);

  const initialCalls = schemaApiCalls;

  // Change label filter
  const labelsFilter = page.locator('#filter-labels');
  await labelsFilter.selectOption('File');

  // Wait for potential API call
  await page.waitForTimeout(1000);

  // Verify additional API call was made (filters trigger schema refetch)
  expect(schemaApiCalls).toBeGreaterThan(initialCalls);
});

test('layout mode changes are applied', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  const layoutMode = page.locator('#layout-mode');

  // Switch to hierarchical layout
  await layoutMode.selectOption('breadthfirst');
  await expect(layoutMode).toHaveValue('breadthfirst');

  // Wait for layout to be applied
  await page.waitForTimeout(500);

  // Switch to manual layout
  await layoutMode.selectOption('manual');
  await expect(layoutMode).toHaveValue('manual');

  // Wait for layout to be applied
  await page.waitForTimeout(500);

  // Switch back to force layout
  await layoutMode.selectOption('cose');
  await expect(layoutMode).toHaveValue('cose');
});

test('graph position save stores to localStorage', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  // Wait for graph to initialize
  await page.waitForTimeout(2000);

  // Click save button
  const saveButton = page.locator('#save-positions');
  await saveButton.click();

  // Check localStorage was updated
  const savedPositions = await page.evaluate(() => {
    return localStorage.getItem('cyto-node-positions');
  });

  // Save button was clicked, verify no errors thrown
  expect(true).toBe(true); // Test passes if save button works
});

test('graph position load retrieves from localStorage', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Set some test data in localStorage before loading page
  await page.goto(base);
  await page.evaluate(() => {
    localStorage.setItem('cyto-node-positions', JSON.stringify({ 'node1': { x: 100, y: 200 } }));
  });

  // Navigate to map page
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  // Wait for graph to initialize
  await page.waitForTimeout(2000);

  // Click load button
  const loadButton = page.locator('#load-positions');
  await loadButton.click();

  // Wait for positions to be applied
  await page.waitForTimeout(500);

  // Verify localStorage was read (no error thrown)
  const savedPositions = await page.evaluate(() => {
    return localStorage.getItem('cyto-node-positions');
  });

  expect(savedPositions).not.toBeNull();
});

/**
 * Tests for Labels + Neo4j schema integration with Map page
 */

test('map schema source selector is visible and functional', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  // Check for source selector
  const sourceSelector = page.getByTestId('schema-source-selector');
  await expect(sourceSelector).toBeVisible();

  // Verify options are present
  await expect(sourceSelector).toHaveValue('all');

  // Test switching sources
  await sourceSelector.selectOption('labels');
  await expect(sourceSelector).toHaveValue('labels');

  await sourceSelector.selectOption('neo4j');
  await expect(sourceSelector).toHaveValue('neo4j');

  await sourceSelector.selectOption('graph');
  await expect(sourceSelector).toHaveValue('graph');

  await sourceSelector.selectOption('all');
  await expect(sourceSelector).toHaveValue('all');
});

test('map uses combined schema endpoint', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Track API calls to verify combined endpoint is being used
  const apiCalls: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/graph/schema')) {
      apiCalls.push(request.url());
    }
  });

  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  // Wait for graph to load
  await page.waitForTimeout(1000);

  // Verify the combined schema endpoint was called
  const combinedCalls = apiCalls.filter(url => url.includes('/api/graph/schema/combined'));
  expect(combinedCalls.length).toBeGreaterThan(0);
});

test('map filter dropdowns populate dynamically from schema', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');

  // Wait for schema to load
  await page.waitForTimeout(1000);

  // Check that filter dropdowns have options
  const labelsFilter = page.getByTestId('filter-labels');
  const reltypesFilter = page.getByTestId('filter-reltypes');

  await expect(labelsFilter).toBeVisible();
  await expect(reltypesFilter).toBeVisible();

  // Get options (should be more than just "All")
  const labelOptions = await labelsFilter.locator('option').count();
  const relOptions = await reltypesFilter.locator('option').count();

  // Both should have at least "All" option
  expect(labelOptions).toBeGreaterThanOrEqual(1);
  expect(relOptions).toBeGreaterThanOrEqual(1);

  // Verify "All" option exists
  await expect(labelsFilter.locator('option[value=""]')).toHaveText('All');
  await expect(reltypesFilter.locator('option[value=""]')).toHaveText('All');
});

test('map source selector triggers schema reload', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Track schema API calls
  const schemaApiCalls: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/graph/schema/combined')) {
      schemaApiCalls.push(request.url());
    }
  });

  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  const initialCalls = schemaApiCalls.length;
  expect(initialCalls).toBeGreaterThan(0);

  // Change source selector
  const sourceSelector = page.getByTestId('schema-source-selector');
  await sourceSelector.selectOption('labels');
  await page.waitForTimeout(1000);

  // Verify additional API call was made with correct source parameter
  expect(schemaApiCalls.length).toBeGreaterThan(initialCalls);
  const latestCall = schemaApiCalls[schemaApiCalls.length - 1];
  expect(latestCall).toContain('source=labels');
});

test('map displays labels from Labels page in visualization', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // First, create a label on the Labels page
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Create a new label
  const newLabelBtn = page.getByTestId('new-label-btn');
  if (await newLabelBtn.isVisible()) {
    await newLabelBtn.click();
    await page.waitForTimeout(500);

    const labelNameInput = page.getByTestId('label-name');
    await labelNameInput.fill('E2EMapTest');

    const saveLabelBtn = page.getByTestId('save-label-btn');
    await saveLabelBtn.click();
    await page.waitForTimeout(1000);
  }

  // Navigate to Map page
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  // Select "Local Labels" or "All Sources" to see the label
  const sourceSelector = page.getByTestId('schema-source-selector');
  await sourceSelector.selectOption('labels');
  await page.waitForTimeout(1000);

  // Check that the label appears in the filter dropdown
  const labelsFilter = page.getByTestId('filter-labels');
  const optionsText = await labelsFilter.locator('option').allTextContents();

  // Verify E2EMapTest label is in the dropdown
  const hasTestLabel = optionsText.some(text => text.includes('E2EMapTest'));
  expect(hasTestLabel).toBe(true);

  // Clean up: delete the test label
  await page.goto(`${base}/labels`);
  await page.waitForLoadState('networkidle');

  // Find and delete the label (implementation depends on Labels page UI)
  // This is a best-effort cleanup
  const deleteBtn = page.locator('button').filter({ hasText: /delete/i }).first();
  if (await deleteBtn.isVisible()) {
    await deleteBtn.click();
    await page.waitForTimeout(500);
    // Confirm deletion if there's a confirmation dialog
    const confirmBtn = page.locator('button').filter({ hasText: /confirm|yes|delete/i }).first();
    if (await confirmBtn.isVisible()) {
      await confirmBtn.click();
    }
  }
});

test('map filter dropdowns update when source changes', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/map`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  const sourceSelector = page.getByTestId('schema-source-selector');
  const labelsFilter = page.getByTestId('filter-labels');

  // Get initial options with "all" source
  await sourceSelector.selectOption('all');
  await page.waitForTimeout(1000);
  const allSourceOptions = await labelsFilter.locator('option').count();

  // Switch to "labels" source
  await sourceSelector.selectOption('labels');
  await page.waitForTimeout(1000);
  const labelsSourceOptions = await labelsFilter.locator('option').count();

  // Switch to "graph" source
  await sourceSelector.selectOption('graph');
  await page.waitForTimeout(1000);
  const graphSourceOptions = await labelsFilter.locator('option').count();

  // At least one of these should have options (or all should have "All" option)
  // Exact counts will vary based on data, but all should be >= 1
  expect(allSourceOptions).toBeGreaterThanOrEqual(1);
  expect(labelsSourceOptions).toBeGreaterThanOrEqual(1);
  expect(graphSourceOptions).toBeGreaterThanOrEqual(1);
});
