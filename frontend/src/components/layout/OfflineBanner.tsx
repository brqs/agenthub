import { RefreshCw, WifiOff } from 'lucide-react';

export function OfflineBanner({
  isOnline,
  updateAvailable,
  onApplyUpdate,
}: {
  isOnline: boolean;
  updateAvailable: boolean;
  onApplyUpdate: () => void;
}) {
  if (isOnline && !updateAvailable) return null;

  return (
    <div
      role="status"
      className="flex shrink-0 items-center justify-center gap-2 border-b border-amber-300 bg-amber-50 px-3 py-2 text-center text-xs font-medium text-amber-900 dark:border-amber-900/70 dark:bg-amber-950/80 dark:text-amber-100"
    >
      {isOnline ? <RefreshCw className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
      <span>{isOnline ? 'AgentHub 已更新，刷新后即可使用最新版本。' : '当前离线，已加载内容仍可查看。'}</span>
      {isOnline && updateAvailable && (
        <button
          type="button"
          onClick={onApplyUpdate}
          className="rounded-md border border-amber-400 px-2 py-1 hover:bg-amber-100 dark:border-amber-700 dark:hover:bg-amber-900"
        >
          刷新更新
        </button>
      )}
    </div>
  );
}
