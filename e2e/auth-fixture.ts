import { test as base, expect } from '@playwright/test';

// Test credentials for E2E auth tests
export const TEST_USERNAME = 'test-admin';
export const TEST_PASSWORD = 'test-password-123';

type AuthFixtures = {
  authenticatedPage: typeof base extends (arg: infer T) => any ? T : never;
};

/**
 * Playwright fixture that provides an authenticated page context.
 * This automatically enables auth, creates a test user, and logs in.
 */
export const test = base.extend<AuthFixtures>({
  authenticatedPage: async ({ page, baseURL }, use) => {
    const base = baseURL || process.env.BASE_URL || 'http://127.0.0.1:5000';
    
    // Enable auth via API
    await fetch(`${base}/api/settings/security/auth`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        enabled: true,
        username: TEST_USERNAME,
        password: TEST_PASSWORD,
      }),
    });

    // Login via API to get session cookie
    const loginResp = await fetch(`${base}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: TEST_USERNAME,
        password: TEST_PASSWORD,
      }),
    });

    const loginData = await loginResp.json();
    
    // Set session cookie in the browser context
    if (loginData.token) {
      await page.context().addCookies([{
        name: 'scidk_session',
        value: loginData.token,
        domain: new URL(base).hostname,
        path: '/',
      }]);
    }

    await use(page);

    // Cleanup: disable auth after test
    await fetch(`${base}/api/settings/security/auth`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: false }),
    });
  },
});

export { expect };
