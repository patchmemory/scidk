import { FullConfig } from '@playwright/test';

export default async function globalTeardown(config: FullConfig) {
  // Clean up test scans before shutting down server
  const baseUrl = (process as any).env.BASE_URL;
  if (baseUrl) {
    try {
      const response = await fetch(`${baseUrl}/api/admin/cleanup-test-scans`, {
        method: 'POST',
      });
      const result = await response.json();
      console.log('[cleanup] Test scans cleaned up:', result);
    } catch (error) {
      console.error('[cleanup] Failed to cleanup test scans:', error);
    }
  }

  // Kill the server process
  const { teardown } = await import('./global-setup');
  await teardown();
}
