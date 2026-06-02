import { act, renderHook } from '@testing-library/react';
import { useVisualViewportHeight } from './useVisualViewportHeight';

describe('useVisualViewportHeight', () => {
  it('tracks visual viewport height and keyboard visibility', () => {
    const listeners = new Map<string, () => void>();
    const viewport = {
      height: 812,
      addEventListener: vi.fn((event: string, listener: () => void) => {
        listeners.set(event, listener);
      }),
      removeEventListener: vi.fn(),
    };
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 812 });
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });

    const { unmount } = renderHook(() => useVisualViewportHeight());
    expect(document.documentElement.style.getPropertyValue('--app-height')).toBe('812px');
    expect(document.documentElement.dataset.keyboardVisible).toBe('false');

    viewport.height = 540;
    act(() => listeners.get('resize')?.());

    expect(document.documentElement.style.getPropertyValue('--app-height')).toBe('540px');
    expect(document.documentElement.dataset.keyboardVisible).toBe('true');

    unmount();
    expect(document.documentElement.style.getPropertyValue('--app-height')).toBe('');
    expect(document.documentElement.dataset.keyboardVisible).toBeUndefined();
  });
});
