import { registerPwa } from './pwa';

describe('registerPwa', () => {
  beforeEach(() => {
    delete (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
    vi.restoreAllMocks();
  });

  it('cleans stale PWA state instead of registering a service worker in desktop runtime', async () => {
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    const unregister = vi.fn(async () => true);
    const deleteCache = vi.fn(async () => true);
    const register = vi.fn();

    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: {
        getRegistrations: vi.fn(async () => [{ unregister }]),
        register,
      },
    });
    Object.defineProperty(window, 'caches', {
      configurable: true,
      value: {
        keys: vi.fn(async () => ['agenthub-shell-v1']),
        delete: deleteCache,
      },
    });

    registerPwa();
    await Promise.resolve();
    await Promise.resolve();

    expect(unregister).toHaveBeenCalledTimes(1);
    expect(deleteCache).toHaveBeenCalledWith('agenthub-shell-v1');
    expect(register).not.toHaveBeenCalled();
  });
});
