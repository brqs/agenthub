import { act, renderHook } from '@testing-library/react';
import { useNetworkStatus } from './useNetworkStatus';

describe('useNetworkStatus', () => {
  afterEach(() => {
    setOnlineStatus(true);
  });

  it('tracks browser offline and online events', () => {
    setOnlineStatus(true);
    const { result } = renderHook(() => useNetworkStatus());

    expect(result.current).toBe(true);

    act(() => {
      setOnlineStatus(false);
      window.dispatchEvent(new Event('offline'));
    });
    expect(result.current).toBe(false);

    act(() => {
      setOnlineStatus(true);
      window.dispatchEvent(new Event('online'));
    });
    expect(result.current).toBe(true);
  });
});

function setOnlineStatus(isOnline: boolean): void {
  Object.defineProperty(window.navigator, 'onLine', {
    configurable: true,
    value: isOnline,
  });
}
