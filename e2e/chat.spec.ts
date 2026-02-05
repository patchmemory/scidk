import { test, expect } from '@playwright/test';

/**
 * E2E tests for Chat page functionality.
 * Tests chat form, API integration, and history display.
 */

test('chat page loads and displays beta badge', async ({ page, baseURL }) => {
  const consoleMessages: { type: string; text: string }[] = [];
  page.on('console', (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  // Navigate to Chat page
  await page.goto(`${base}/chat`);
  await page.waitForLoadState('networkidle');

  // Verify page loads
  await expect(page).toHaveTitle(/SciDK - Chats/i, { timeout: 10_000 });

  // Check for Beta badge
  const betaBadge = page.locator('.badge');
  await expect(betaBadge).toBeVisible();
  await expect(betaBadge).toHaveText('Beta');

  // Check for chat form
  const chatForm = page.locator('#chat-form');
  await expect(chatForm).toBeVisible();

  // Check for chat input
  const chatInput = page.locator('#chat-input');
  await expect(chatInput).toBeVisible();
  await expect(chatInput).toHaveAttribute('placeholder', /Ask something/i);

  // Check for send button
  const sendButton = page.locator('#chat-form button[type="submit"]');
  await expect(sendButton).toBeVisible();
  await expect(sendButton).toHaveText('Send');

  // No console errors
  const errors = consoleMessages.filter((m) => m.type === 'error');
  expect(errors.length).toBe(0);
});

test('chat navigation link is visible in header', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';

  await page.goto(base);
  await page.waitForLoadState('networkidle');

  // Check that Chats link exists in navigation
  const chatsLink = page.getByTestId('nav-chats');
  await expect(chatsLink).toBeVisible();

  // Click it and verify we navigate to chat page
  await chatsLink.click();
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveTitle(/SciDK - Chats/i);
});

test('chat form can accept input', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/chat`);
  await page.waitForLoadState('networkidle');

  const chatInput = page.locator('#chat-input');

  // Type a message
  const testMessage = 'Hello, can you help me with my datasets?';
  await chatInput.fill(testMessage);

  // Verify the input contains the message
  await expect(chatInput).toHaveValue(testMessage);
});

test('chat form submits to /api/chat endpoint', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/chat`);
  await page.waitForLoadState('networkidle');

  const chatInput = page.locator('#chat-input');
  const chatForm = page.locator('#chat-form');

  // Listen for API request
  const apiRequestPromise = page.waitForRequest(
    (request) => request.url().includes('/api/chat') && request.method() === 'POST'
  );

  // Mock the API response to avoid actual chat API calls
  await page.route('**/api/chat', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        history: [
          { role: 'user', content: 'What are my datasets?' },
          { role: 'assistant', content: 'Here are your datasets...' }
        ]
      })
    });
  });

  // Type and submit a message
  await chatInput.fill('What are my datasets?');

  const submitButton = page.locator('#chat-form button[type="submit"]');
  const [apiRequest] = await Promise.all([
    apiRequestPromise,
    submitButton.click()
  ]);

  expect(apiRequest.url()).toContain('/api/chat');

  // Verify request payload
  const postData = apiRequest.postDataJSON();
  expect(postData).toHaveProperty('message', 'What are my datasets?');
});

test('chat form displays history after response', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/chat`);
  await page.waitForLoadState('networkidle');

  const chatInput = page.locator('#chat-input');
  const chatForm = page.locator('#chat-form');
  const chatHistory = page.locator('#chat-history');

  // Mock the API response
  await page.route('**/api/chat', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        history: [
          { role: 'user', content: 'Test question' },
          { role: 'assistant', content: 'Test response' }
        ]
      })
    });
  });

  // Submit a message
  await chatInput.fill('Test question');
  const submitButton = page.locator('#chat-form button[type="submit"]');
  await submitButton.click();

  // Wait for history to be populated
  await page.waitForTimeout(1000); // Wait for API mock and DOM update

  // Verify history has content
  const historyContent = await chatHistory.textContent();
  expect(historyContent).toContain('user:');
  expect(historyContent).toContain('Test question');
  expect(historyContent).toContain('assistant:');
  expect(historyContent).toContain('Test response');

  // Verify input is cleared after submission
  await expect(chatInput).toHaveValue('');
});

test('chat form handles API errors gracefully', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/chat`);
  await page.waitForLoadState('networkidle');

  const chatInput = page.locator('#chat-input');
  const chatForm = page.locator('#chat-form');

  // Set up dialog handler to catch the alert
  page.on('dialog', async (dialog) => {
    expect(dialog.message()).toContain('Chat error');
    await dialog.accept();
  });

  // Mock an API error
  await page.route('**/api/chat', async (route) => {
    await route.abort('failed');
  });

  // Submit a message
  await chatInput.fill('This will fail');
  await chatForm.evaluate((form) => (form as HTMLFormElement).submit());

  // Wait for the error dialog to appear and be handled
  await page.waitForTimeout(500);

  // Verify input is still cleared even after error
  await expect(chatInput).toHaveValue('');
});

test('chat form does not submit empty messages', async ({ page, baseURL }) => {
  const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
  await page.goto(`${base}/chat`);
  await page.waitForLoadState('networkidle');

  const chatInput = page.locator('#chat-input');
  const chatForm = page.locator('#chat-form');

  // Track API calls
  let apiCallMade = false;
  page.on('request', (request) => {
    if (request.url().includes('/api/chat') && request.method() === 'POST') {
      apiCallMade = true;
    }
  });

  // Try to submit empty message
  await chatInput.fill('   '); // Whitespace only
  await chatForm.evaluate((form) => (form as HTMLFormElement).submit());

  // Wait a bit to ensure no request is made
  await page.waitForTimeout(500);

  // Verify no API call was made
  expect(apiCallMade).toBe(false);
});
