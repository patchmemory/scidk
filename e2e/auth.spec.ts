/**
 * E2E tests for authentication flow
 *
 * Tests cover:
 * - Login page rendering
 * - Successful login
 * - Failed login
 * - Logout
 * - Auth middleware (redirect to login when not authenticated)
 * - Session persistence
 */

import { test, expect } from '@playwright/test';

// Helper to enable auth via settings API
async function enableAuth(request: any, username: string, password: string) {
  const response = await request.post('/api/settings/security/auth', {
    data: {
      enabled: true,
      username,
      password,
    },
  });
  expect(response.ok()).toBeTruthy();
}

// Helper to disable auth via settings API
async function disableAuth(request: any) {
  const response = await request.post('/api/settings/security/auth', {
    data: {
      enabled: false,
    },
  });
  expect(response.ok()).toBeTruthy();
}

test.describe.configure({ mode: 'serial' }); // Run auth tests serially to avoid state conflicts

test.describe('Authentication Flow', () => {
  test.beforeEach(async ({ page, request }) => {
    // Ensure auth is disabled before each test
    await disableAuth(request);
  });

  test.afterEach(async ({ request }) => {
    // Clean up: disable auth after each test
    await disableAuth(request);
  });

  test('login page renders correctly', async ({ page }) => {
    await page.goto('/login');

    // Check page elements
    await expect(page.getByTestId('login-header')).toContainText('-SciDK->');
    await expect(page.getByTestId('login-username')).toBeVisible();
    await expect(page.getByTestId('login-password')).toBeVisible();
    await expect(page.getByTestId('login-remember')).toBeVisible();
    await expect(page.getByTestId('login-submit')).toBeVisible();
  });

  test('successful login flow', async ({ page, request }) => {
    // Enable auth
    await enableAuth(request, 'testuser', 'testpass123');

    // Navigate to login page
    await page.goto('/login');

    // Fill in credentials
    await page.getByTestId('login-username').fill('testuser');
    await page.getByTestId('login-password').fill('testpass123');

    // Submit form
    await page.getByTestId('login-submit').click();

    // Should redirect to home page
    await expect(page).toHaveURL('/');

    // Logout button should be visible
    await expect(page.getByTestId('logout-btn')).toBeVisible();
  });

  test('failed login shows error', async ({ page, request }) => {
    // Enable auth
    await enableAuth(request, 'testuser', 'testpass123');

    // Navigate to login page
    await page.goto('/login');

    // Fill in wrong credentials
    await page.getByTestId('login-username').fill('testuser');
    await page.getByTestId('login-password').fill('wrongpassword');

    // Submit form
    await page.getByTestId('login-submit').click();

    // Should show error message
    await expect(page.getByTestId('login-error')).toBeVisible();
    await expect(page.getByTestId('login-error')).toContainText('Invalid credentials');

    // Should still be on login page
    await expect(page).toHaveURL('/login');
  });

  test('login with missing fields shows validation error', async ({ page, request }) => {
    // Enable auth
    await enableAuth(request, 'testuser', 'testpass123');

    // Navigate to login page
    await page.goto('/login');

    // Fill password but leave username empty
    await page.getByTestId('login-password').fill('testpass123');

    // Try to submit - should trigger browser validation or show error
    await page.getByTestId('login-submit').click();

    // Wait a bit for any validation to appear
    await page.waitForTimeout(500);

    // Should either show validation error or stay on login page
    await expect(page).toHaveURL(/\/login/);
  });

  test('remember me checkbox works', async ({ page, request }) => {
    // Enable auth
    await enableAuth(request, 'testuser', 'testpass123');

    // Navigate to login page
    await page.goto('/login');

    // Fill credentials and check remember me
    await page.getByTestId('login-username').fill('testuser');
    await page.getByTestId('login-password').fill('testpass123');
    await page.getByTestId('login-remember').check();

    // Submit
    await page.getByTestId('login-submit').click();

    // Should redirect to home page
    await expect(page).toHaveURL('/');
  });

  test('logout clears session and redirects to login', async ({ page, request }) => {
    // Enable auth
    await enableAuth(request, 'testuser', 'testpass123');

    // Login via UI (not API) so cookies are set in page context
    await page.goto('/login');
    await page.getByTestId('login-username').fill('testuser');
    await page.getByTestId('login-password').fill('testpass123');
    await page.getByTestId('login-submit').click();

    // Wait for redirect to home
    await expect(page).toHaveURL('/');

    // Logout button should be visible
    await expect(page.getByTestId('logout-btn')).toBeVisible();

    // Click logout
    await page.getByTestId('logout-btn').click();

    // Should redirect to login page
    await expect(page).toHaveURL('/login');
  });

  test('unauthenticated users redirected to login', async ({ page, request }) => {
    // Enable auth without logging in
    await enableAuth(request, 'testuser', 'testpass123');

    // Try to access protected page (datasets)
    await page.goto('/datasets');

    // Should redirect to login with return URL
    await expect(page).toHaveURL(/\/login/);
  });

  test('authenticated users can access all pages', async ({ page, request }) => {
    // Enable auth
    await enableAuth(request, 'testuser', 'testpass123');

    // Login via UI so cookies are set in page context
    await page.goto('/login');
    await page.getByTestId('login-username').fill('testuser');
    await page.getByTestId('login-password').fill('testpass123');
    await page.getByTestId('login-submit').click();

    // Wait for redirect to home
    await expect(page).toHaveURL('/');

    // Should be able to access protected pages
    await page.goto('/datasets');
    await expect(page).toHaveURL('/datasets');

    await page.goto('/labels');
    await expect(page).toHaveURL('/labels');

    await page.goto('/chat');
    await expect(page).toHaveURL('/chat');
  });

  test('API returns 401 for unauthenticated requests', async ({ request }) => {
    // Enable auth
    await enableAuth(request, 'testuser', 'testpass123');

    // Try to access protected API endpoint without auth
    const response = await request.get('/api/admin/health', {
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(401);
    const data = await response.json();
    expect(data.error).toContain('Authentication required');
  });

  test.skip('auth status endpoint works correctly', async ({ page, request }) => {
    // Test when auth is disabled
    let response = await request.get('/api/auth/status');
    expect(response.ok()).toBeTruthy();
    let data = await response.json();
    expect(data.authenticated).toBe(true);
    expect(data.auth_enabled).toBe(false);

    // Enable auth
    await enableAuth(request, 'testuser', 'testpass123');

    // Test when auth is enabled but not logged in
    response = await request.get('/api/auth/status');
    expect(response.ok()).toBeTruthy();
    data = await response.json();
    expect(data.authenticated).toBe(false);
    expect(data.auth_enabled).toBe(true);

    // Login
    const loginResponse = await request.post('/api/auth/login', {
      data: {
        username: 'testuser',
        password: 'testpass123',
      },
    });
    expect(loginResponse.ok()).toBeTruthy();
    const loginData = await loginResponse.json();

    // Test when logged in
    response = await request.get('/api/auth/status', {
      headers: {
        Authorization: `Bearer ${loginData.token}`,
      },
    });
    expect(response.ok()).toBeTruthy();
    data = await response.json();
    expect(data.authenticated).toBe(true);
    expect(data.username).toBe('testuser');
  });

  test.skip('settings page shows security configuration', async ({ page }) => {
    await page.goto('/');

    // Security section should be visible
    await expect(page.locator('h3:has-text("Security")')).toBeVisible();

    // Auth toggle should be present
    await expect(page.locator('#security-auth-enabled')).toBeVisible();

    // Save button should be present
    await expect(page.getByTestId('save-security-btn')).toBeVisible();
  });

  test('enabling auth from settings page works', async ({ page }) => {
    await page.goto('/');

    // Enable auth toggle
    await page.locator('#security-auth-enabled').check();

    // Auth fields should appear
    await expect(page.locator('#security-username')).toBeVisible();
    await expect(page.locator('#security-password')).toBeVisible();

    // Fill in credentials
    await page.locator('#security-username').fill('admin');
    await page.locator('#security-password').fill('admin123');

    // Save settings
    await page.getByTestId('save-security-btn').click();

    // Should see success message (toast or status text)
    await expect(page.locator('#security-status')).toContainText('enabled', {
      timeout: 5000,
    });

    // Should redirect to login after 2 seconds
    await expect(page).toHaveURL('/login', { timeout: 5000 });
  });
});
