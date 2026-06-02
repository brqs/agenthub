import { useEffect, useState } from 'react';

export function useNetworkStatus(): boolean {
  const [isOnline, setIsOnline] = useState(getOnlineStatus);

  useEffect(() => {
    const updateStatus = () => setIsOnline(getOnlineStatus());
    window.addEventListener('online', updateStatus);
    window.addEventListener('offline', updateStatus);
    return () => {
      window.removeEventListener('online', updateStatus);
      window.removeEventListener('offline', updateStatus);
    };
  }, []);

  return isOnline;
}

function getOnlineStatus(): boolean {
  if (typeof navigator === 'undefined') return true;
  return navigator.onLine;
}
