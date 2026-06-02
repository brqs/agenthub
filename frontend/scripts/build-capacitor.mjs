import { execFileSync } from 'node:child_process';

const apiBaseUrl = process.env.VITE_API_BASE_URL ?? '';

if (!apiBaseUrl.startsWith('https://')) {
  console.error('Capacitor build requires VITE_API_BASE_URL=https://...');
  process.exit(1);
}

execFileSync('pnpm', ['build'], {
  env: process.env,
  stdio: 'inherit',
});
