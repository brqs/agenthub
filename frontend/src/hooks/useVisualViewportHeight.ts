import { useEffect } from 'react';

const KEYBOARD_THRESHOLD = 120;

export function useVisualViewportHeight() {
  useEffect(() => {
    const root = document.documentElement;
    const viewport = window.visualViewport;

    function updateViewportHeight() {
      const height = viewport?.height ?? window.innerHeight;
      const keyboardVisible = window.innerHeight - height > KEYBOARD_THRESHOLD;
      root.style.setProperty('--app-height', `${Math.round(height)}px`);
      root.dataset.keyboardVisible = String(keyboardVisible);
    }

    updateViewportHeight();
    viewport?.addEventListener('resize', updateViewportHeight);
    viewport?.addEventListener('scroll', updateViewportHeight);
    window.addEventListener('resize', updateViewportHeight);

    return () => {
      viewport?.removeEventListener('resize', updateViewportHeight);
      viewport?.removeEventListener('scroll', updateViewportHeight);
      window.removeEventListener('resize', updateViewportHeight);
      root.style.removeProperty('--app-height');
      delete root.dataset.keyboardVisible;
    };
  }, []);
}
