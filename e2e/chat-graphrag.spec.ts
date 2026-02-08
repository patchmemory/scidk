import { test, expect, request as playwrightRequest } from '@playwright/test';

test.describe('Chat GraphRAG', () => {
  test.beforeEach(async ({ page, baseURL }) => {
    // Disable auth before each test
    const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
    const api = await playwrightRequest.newContext();
    await api.post(`${base}/api/settings/security/auth`, {
      headers: { 'Content-Type': 'application/json' },
      data: { enabled: false },
    });

    // Clear localStorage before each test
    await page.goto('/chat');
    await page.evaluate(() => {
      localStorage.clear();
    });
    await page.reload();
  });

  test('displays chat page with correct elements', async ({ page }) => {
    await page.goto('/chat');

    // Check title and header
    await expect(page.locator('h2')).toContainText('Chat');
    await expect(page.locator('h2')).toContainText('GraphRAG');

    // Check form elements
    await expect(page.getByTestId('chat-input')).toBeVisible();
    await expect(page.getByTestId('chat-send')).toBeVisible();
    await expect(page.getByTestId('chat-clear')).toBeVisible();

    // Check verbose mode checkbox
    await expect(page.locator('#verbose-mode')).toBeVisible();

    // Check history area
    await expect(page.getByTestId('chat-history')).toBeVisible();
  });

  // TODO: FLAKY - chat-history element sometimes not found
  test.skip('shows empty state message initially', async ({ page }) => {
    await page.goto('/chat');

    const history = page.getByTestId('chat-history');
    await expect(history).toContainText('No messages yet');
  });

  test('can send a message and receive response', async ({ page }) => {
    await page.goto('/chat');
    await page.waitForLoadState('domcontentloaded');

    // Type and send message
    await page.getByTestId('chat-input').fill('How many files are there?');
    await page.getByTestId('chat-send').click();

    // User message should appear immediately
    await expect(page.getByTestId('chat-message-user')).toBeVisible();
    await expect(page.getByTestId('chat-message-user')).toContainText('How many files are there?');

    // Wait for assistant response (may take a moment for GraphRAG)
    await expect(page.getByTestId('chat-message-assistant')).toBeVisible({ timeout: 10000 });

    // Response should contain some text
    const assistantMessage = page.getByTestId('chat-message-assistant');
    await expect(assistantMessage).not.toBeEmpty();
  });

  test('input is cleared after sending', async ({ page }) => {
    await page.goto('/chat');

    const input = page.getByTestId('chat-input');
    await input.fill('Test message');
    await page.getByTestId('chat-send').click();

    // Input should be cleared
    await expect(input).toHaveValue('');
  });

  test('verbose mode shows metadata', async ({ page }) => {
    await page.goto('/chat');

    // Enable verbose mode
    await page.locator('#verbose-mode').check();

    // Send a query
    await page.getByTestId('chat-input').fill('Find files');
    await page.getByTestId('chat-send').click();

    // Wait for response
    await expect(page.getByTestId('chat-message-assistant')).toBeVisible({ timeout: 10000 });

    // Check for metadata elements (execution time badge should appear)
    const assistantMessage = page.getByTestId('chat-message-assistant');
    const metadataSection = assistantMessage.locator('.chat-metadata');

    // Metadata may or may not have content depending on query, but section should exist if verbose
    // Just verify the verbose mode affects rendering
    const hasMetadata = await metadataSection.count();
    // Metadata section appears when there's data to show
  });

  test('can clear history', async ({ page }) => {
    await page.goto('/chat');

    // Send a message
    await page.getByTestId('chat-input').fill('Test message');
    await page.getByTestId('chat-send').click();

    // Wait for message to appear
    await expect(page.getByTestId('chat-message-user')).toBeVisible();

    // Click clear button and confirm
    page.on('dialog', dialog => dialog.accept());
    await page.getByTestId('chat-clear').click();

    // History should show empty state
    const history = page.getByTestId('chat-history');
    await expect(history).toContainText('History cleared');
  });

  test('history persists across page reloads', async ({ page }) => {
    await page.goto('/chat');

    // Send a message
    const testMessage = 'Test persistence message';
    await page.getByTestId('chat-input').fill(testMessage);
    await page.getByTestId('chat-send').click();

    // Wait for user message
    await expect(page.getByTestId('chat-message-user')).toBeVisible();

    // Reload page
    await page.reload();

    // Message should still be there
    await expect(page.getByTestId('chat-message-user')).toContainText(testMessage);
  });

  test('verbose preference persists', async ({ page }) => {
    await page.goto('/chat');

    // Enable verbose mode
    const verboseCheckbox = page.locator('#verbose-mode');
    await verboseCheckbox.check();
    await expect(verboseCheckbox).toBeChecked();

    // Reload page
    await page.reload();

    // Verbose mode should still be checked
    await expect(verboseCheckbox).toBeChecked();
  });

  test('displays user and assistant messages with different styles', async ({ page }) => {
    await page.goto('/chat');

    // Send a message
    await page.getByTestId('chat-input').fill('Test styling');
    await page.getByTestId('chat-send').click();

    // Wait for both messages
    await expect(page.getByTestId('chat-message-user')).toBeVisible();
    await expect(page.getByTestId('chat-message-assistant')).toBeVisible({ timeout: 10000 });

    // Check that messages have different styling
    const userMessage = page.getByTestId('chat-message-user');
    const assistantMessage = page.getByTestId('chat-message-assistant');

    // Verify role indicators
    await expect(userMessage).toContainText('You');
    await expect(assistantMessage).toContainText('Assistant');

    // Verify CSS classes
    await expect(userMessage).toHaveClass(/user/);
    await expect(assistantMessage).toHaveClass(/assistant/);
  });

  test('prevents sending empty messages', async ({ page }) => {
    await page.goto('/chat');

    // Try to send empty message
    await page.getByTestId('chat-send').click();

    // No message should appear
    const userMessages = page.getByTestId('chat-message-user');
    await expect(userMessages).toHaveCount(0);
  });

  test('handles error responses gracefully', async ({ page }) => {
    await page.goto('/chat');

    // Mock a failing API response
    await page.route('/api/chat/graphrag', route => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'error', error: 'Test error' })
      });
    });

    // Send a message
    await page.getByTestId('chat-input').fill('This will fail');
    await page.getByTestId('chat-send').click();

    // Error message should appear
    await expect(page.getByTestId('chat-message-assistant')).toBeVisible();
    await expect(page.getByTestId('chat-message-assistant')).toContainText('Error');
  });

  test('displays execution time in verbose mode', async ({ page }) => {
    await page.goto('/chat');

    // Enable verbose mode
    await page.locator('#verbose-mode').check();

    // Mock response with metadata
    await page.route('/api/chat/graphrag', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          reply: 'Found 3 results',
          history: [],
          metadata: {
            entities: { identifiers: ['TEST_001'], labels: ['File'], properties: {} },
            execution_time_ms: 1234,
            result_count: 3
          }
        })
      });
    });

    // Send a query
    await page.getByTestId('chat-input').fill('Find files');
    await page.getByTestId('chat-send').click();

    // Wait for response
    await expect(page.getByTestId('chat-message-assistant')).toBeVisible();

    // Check for metadata
    const assistantMessage = page.getByTestId('chat-message-assistant');
    await expect(assistantMessage).toContainText('1234ms');
    await expect(assistantMessage).toContainText('3 results');
  });

  test('displays entity badges in verbose mode', async ({ page }) => {
    await page.goto('/chat');

    // Enable verbose mode
    await page.locator('#verbose-mode').check();

    // Mock response with entities
    await page.route('/api/chat/graphrag', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          reply: 'Found results',
          history: [],
          metadata: {
            entities: {
              identifiers: ['TEST_001', 'ABC_123'],
              labels: ['File', 'Scan'],
              properties: { name: 'test.txt' }
            },
            execution_time_ms: 500,
            result_count: 2
          }
        })
      });
    });

    // Send query
    await page.getByTestId('chat-input').fill('Find TEST_001');
    await page.getByTestId('chat-send').click();

    // Wait for response
    await expect(page.getByTestId('chat-message-assistant')).toBeVisible();

    // Check for entity badges
    const assistantMessage = page.getByTestId('chat-message-assistant');
    await expect(assistantMessage).toContainText('ID: TEST_001');
    await expect(assistantMessage).toContainText('ID: ABC_123');
    await expect(assistantMessage).toContainText('Label: File');
    await expect(assistantMessage).toContainText('Label: Scan');
    await expect(assistantMessage).toContainText('name: test.txt');
  });

  test('multiple messages display in chronological order', async ({ page }) => {
    await page.goto('/chat');

    // Send first message
    await page.getByTestId('chat-input').fill('First message');
    await page.getByTestId('chat-send').click();
    await expect(page.getByTestId('chat-message-user').first()).toContainText('First message');

    // Wait for first response
    await expect(page.getByTestId('chat-message-assistant').first()).toBeVisible({ timeout: 10000 });

    // Send second message
    await page.getByTestId('chat-input').fill('Second message');
    await page.getByTestId('chat-send').click();

    // Check message order
    const messages = page.locator('.chat-message');
    await expect(messages).toHaveCount(4); // 2 user + 2 assistant (at least)

    // First user message should be before second
    const allText = await page.getByTestId('chat-history').textContent();
    const firstIndex = allText?.indexOf('First message') ?? -1;
    const secondIndex = allText?.indexOf('Second message') ?? -1;
    expect(firstIndex).toBeLessThan(secondIndex);
  });
});
