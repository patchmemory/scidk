import { FullConfig } from '@playwright/test';
import { spawn, ChildProcessWithoutNullStreams } from 'node:child_process';
import http from 'node:http';

function waitForReady(url: string, timeout = 20000): Promise<void> {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      http
        .get(url, (res) => {
          res.resume();
          res.destroy();
          resolve();
        })
        .on('error', () => {
          if (Date.now() - start > timeout) reject(new Error('Server not ready'));
          else setTimeout(tick, 250);
        });
    };
    tick();
  });
}

let proc: ChildProcessWithoutNullStreams | null = null;

export default async function globalSetup(config: FullConfig) {
  const port = 5010 + Math.floor(Math.random() * 500);
  const env = { ...process.env, PORT: String(port), FLASK_ENV: 'development' };

  // Prefer running the Flask app directly via Python to avoid Flask CLI dependency
  const pyCode = [
    "from scidk.app import create_app",
    "app=create_app()",
    "app.run(host='127.0.0.1', port=int(__import__('os').environ.get('PORT','5000')), use_reloader=False)"
  ].join('; ');

  // Use python3 explicitly for better cross-platform compatibility
  const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
  proc = spawn(pythonCmd, ['-c', pyCode], {
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  proc.stdout?.on('data', (d) => process.stdout.write(`[server] ${d}`));
  proc.stderr?.on('data', (d) => process.stderr.write(`[server] ${d}`));

  const baseUrl = `http://127.0.0.1:${port}`;
  (process as any).env.BASE_URL = baseUrl;

  await waitForReady(baseUrl);
}

export async function teardown() {
  if (proc && !proc.killed) {
    try { proc.kill(); } catch {}
  }
}
