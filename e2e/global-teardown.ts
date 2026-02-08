import { FullConfig } from '@playwright/test';

// Import the teardown function from global-setup
import { teardown } from './global-setup';

export default async function globalTeardown(config: FullConfig) {
  // Clean up test data before shutting down server
  const baseUrl = (process as any).env.BASE_URL;
  if (baseUrl) {
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
