import { useEffect } from 'react';

const KEYBOARD_THRESHOLD = 120;
const MOBILE_VIEWPORT_QUERY = '(pointer: coarse), (max-width: 767px)';

export function useVisualViewportHeight() {
  useEffect(() => {
    const root = document.documentElement;
    const viewport = window.visualViewport;
    const mobileViewport = window.matchMedia?.(MOBILE_VIEWPORT_QUERY);

    function updateViewportHeight() {
      const height = viewport?.height ?? window.innerHeight;
      const keyboardVisible = window.innerHeight - height > KEYBOARD_THRESHOLD;
      const shouldUseMeasuredHeight = mobileViewport?.matches || keyboardVisible;

      if (shouldUseMeasuredHeight) {
        root.style.setProperty('--app-height', `${Math.round(height)}px`);
      } else {
        root.style.removeProperty('--app-height');
      }
      root.dataset.keyboardVisible = String(keyboardVisible);
    }

    updateViewportHeight();
    viewport?.addEventListener('resize', updateViewportHeight);
    viewport?.addEventListener('scroll', updateViewportHeight);
    window.addEventListener('resize', updateViewportHeight);
    addMediaQueryListener(mobileViewport, updateViewportHeight);

    return () => {
      viewport?.removeEventListener('resize', updateViewportHeight);
      viewport?.removeEventListener('scroll', updateViewportHeight);
      window.removeEventListener('resize', updateViewportHeight);
      removeMediaQueryListener(mobileViewport, updateViewportHeight);
      root.style.removeProperty('--app-height');
      delete root.dataset.keyboardVisible;
    };
  }, []);
}

function addMediaQueryListener(
  media: MediaQueryList | undefined,
  listener: () => void,
) {
  if (!media) return;
  if (typeof media.addEventListener === 'function') {
    media.addEventListener('change', listener);
    return;
  }
  media.addListener?.(listener);
}

function removeMediaQueryListener(
  media: MediaQueryList | undefined,
  listener: () => void,
) {
  if (!media) return;
  if (typeof media.removeEventListener === 'function') {
    media.removeEventListener('change', listener);
    return;
  }
  media.removeListener?.(listener);
}
