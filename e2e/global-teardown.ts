import { FullConfig } from '@playwright/test';
import { spawn } from 'node:child_process';
import { promisify } from 'node:util';

// Import the teardown function from global-setup
import { teardown } from './global-setup';

const exec = promisify(require('node:child_process').exec);

export default async function globalTeardown(config: FullConfig) {
  // Clean up test data before shutting down server
  const baseUrl = (process as any).env.BASE_URL;
  if (baseUrl) {
    // CRITICAL: Disable auth first via API
    try {
      const response = await fetch(`${baseUrl}/api/settings/security/auth`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: false }),
      });
      console.log('[cleanup] Legacy auth disabled via API:', response.ok);
    } catch (error) {
      console.error('[cleanup] Failed to disable auth via API:', error);
    }

    // CRITICAL: Also disable auth directly in database to handle multi-user auth
    try {
      await exec('python3 e2e/cleanup-auth.py scidk_settings.db');
    } catch (error: any) {
      console.error('[cleanup] Failed to cleanup auth in DB:', error.message);
    }

    // Clean up test scans
    try {
      const response = await fetch(`${baseUrl}/api/admin/cleanup-test-scans`, {
        method: 'POST',
      });
      const result = await response.json();
      console.log('[cleanup] Test scans cleaned up:', result);
    } catch (error) {
      console.error('[cleanup] Failed to cleanup test scans:', error);
    }

    // Clean up test labels
    try {
      const response = await fetch(`${baseUrl}/api/admin/cleanup-test-labels`, {
        method: 'POST',
      });
      const result = await response.json();
      console.log('[cleanup] Test labels cleaned up:', result);
    } catch (error) {
      console.error('[cleanup] Failed to cleanup test labels:', error);
    }

    // Clean up test API endpoints
    try {
      const response = await fetch(`${baseUrl}/api/admin/cleanup-test-endpoints`, {
        method: 'POST',
      });
      const result = await response.json();
      console.log('[cleanup] Test API endpoints cleaned up:', result);
    } catch (error) {
      console.error('[cleanup] Failed to cleanup test API endpoints:', error);
    }
  }

  // Kill the server process
  await teardown();
}
