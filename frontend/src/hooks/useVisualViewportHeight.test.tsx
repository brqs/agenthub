import { act, renderHook } from '@testing-library/react';
import { useVisualViewportHeight } from './useVisualViewportHeight';

describe('useVisualViewportHeight', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.documentElement.style.removeProperty('--app-height');
    delete document.documentElement.dataset.keyboardVisible;
  });

  it('does not write app height on desktop visual viewport changes', () => {
    const { listeners, viewport } = setupViewport({ height: 812, mobile: false });

    renderHook(() => useVisualViewportHeight());

    expect(document.documentElement.style.getPropertyValue('--app-height')).toBe('');
    expect(document.documentElement.dataset.keyboardVisible).toBe('false');

    viewport.height = 780;
    act(() => listeners.get('resize')?.());

    expect(document.documentElement.style.getPropertyValue('--app-height')).toBe('');
    expect(document.documentElement.dataset.keyboardVisible).toBe('false');
  });

  it('tracks visual viewport height on mobile viewports', () => {
    const { listeners, viewport } = setupViewport({ height: 812, mobile: true });

    renderHook(() => useVisualViewportHeight());

    expect(document.documentElement.style.getPropertyValue('--app-height')).toBe('812px');
    expect(document.documentElement.dataset.keyboardVisible).toBe('false');

    viewport.height = 700;
    act(() => listeners.get('resize')?.());

    expect(document.documentElement.style.getPropertyValue('--app-height')).toBe('700px');
    expect(document.documentElement.dataset.keyboardVisible).toBe('false');
  });

  it('uses measured height when a software keyboard is visible', () => {
    const { listeners, viewport } = setupViewport({ height: 812, mobile: false });

    renderHook(() => useVisualViewportHeight());

    viewport.height = 540;
    act(() => listeners.get('resize')?.());

    expect(document.documentElement.style.getPropertyValue('--app-height')).toBe('540px');
    expect(document.documentElement.dataset.keyboardVisible).toBe('true');
  });

  it('cleans up root styles and listeners on unmount', () => {
    const { viewport, media } = setupViewport({ height: 812, mobile: true });

    const { unmount } = renderHook(() => useVisualViewportHeight());

    expect(document.documentElement.style.getPropertyValue('--app-height')).toBe('812px');

    unmount();

    expect(document.documentElement.style.getPropertyValue('--app-height')).toBe('');
    expect(document.documentElement.dataset.keyboardVisible).toBeUndefined();
    expect(viewport.removeEventListener).toHaveBeenCalledWith('resize', expect.any(Function));
    expect(viewport.removeEventListener).toHaveBeenCalledWith('scroll', expect.any(Function));
    expect(media.removeEventListener).toHaveBeenCalledWith('change', expect.any(Function));
  });
});

function setupViewport({ height, mobile }: { height: number; mobile: boolean }) {
  const listeners = new Map<string, () => void>();
  const viewport = {
    height,
    addEventListener: vi.fn((event: string, listener: () => void) => {
      listeners.set(event, listener);
    }),
    removeEventListener: vi.fn(),
  };
  const media = {
    matches: mobile,
    addEventListener: vi.fn((event: string, listener: () => void) => {
      listeners.set(`media:${event}`, listener);
    }),
    removeEventListener: vi.fn(),
  };

  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 812 });
  Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });
  vi.stubGlobal('matchMedia', vi.fn(() => media));

  return { listeners, viewport, media };
}
