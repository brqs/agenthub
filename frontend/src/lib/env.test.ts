describe('desktop runtime API URL policy', () => {
  beforeEach(() => {
    vi.resetModules();
    window.localStorage.clear();
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
  });

  afterEach(() => {
    delete (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
    vi.resetModules();
  });

  it('allows an explicitly selected desktop HTTP backend profile', async () => {
    const { getApiBaseUrl, setRuntimeApiBaseUrl } = await import('./env');

    expect(() =>
      setRuntimeApiBaseUrl('http://111.229.151.159:8000', { persistDesktop: true }),
    ).not.toThrow();
    expect(getApiBaseUrl()).toBe('http://111.229.151.159:8000');
  });

  it('still rejects non-explicit remote HTTP desktop API switches', async () => {
    const { setRuntimeApiBaseUrl } = await import('./env');

    expect(() => setRuntimeApiBaseUrl('http://111.229.151.159:8000')).toThrow();
  });
});
