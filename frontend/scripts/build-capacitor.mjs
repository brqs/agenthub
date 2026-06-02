import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';

function loadLocalEnv() {
  const envFiles = ['.env.local'];
  const values = {};

  for (const file of envFiles) {
    if (!existsSync(file)) continue;
    const lines = readFileSync(file, 'utf8').split(/\r?\n/);
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const separator = trimmed.indexOf('=');
      if (separator === -1) continue;
      const key = trimmed.slice(0, separator).trim();
      const value = trimmed.slice(separator + 1).trim().replace(/^['"]|['"]$/g, '');
      values[key] = value;
    }
  }

  return values;
}

const localEnv = loadLocalEnv();
const buildEnv = { ...localEnv, ...process.env };
const apiBaseUrl = buildEnv.VITE_API_BASE_URL ?? '';
const allowInsecureNativeApi = buildEnv.VITE_ALLOW_INSECURE_NATIVE_API === 'true';

if (!apiBaseUrl.startsWith('https://') && !(allowInsecureNativeApi && apiBaseUrl.startsWith('http://'))) {
  console.error('Capacitor build requires VITE_API_BASE_URL=https://... unless VITE_ALLOW_INSECURE_NATIVE_API=true is set for a temporary HTTP backend.');
  process.exit(1);
}

if (apiBaseUrl.startsWith('http://')) {
  console.warn('Warning: building Capacitor app with an HTTP API. Use HTTPS before production release.');
}

execFileSync('pnpm', ['build'], {
  env: buildEnv,
  stdio: 'inherit',
});
