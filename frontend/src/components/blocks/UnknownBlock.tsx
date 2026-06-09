import { AlertTriangle } from 'lucide-react';

export function UnknownBlock({ type }: { type: string }) {
  return (
    <div className="my-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-950/20 dark:text-amber-100">
      <div className="flex items-center gap-2 font-medium">
        <AlertTriangle className="h-4 w-4" />
        未支持的消息块
      </div>
      <p className="mt-2 text-xs text-amber-700 dark:text-amber-200/70">
        当前前端暂未支持 `{type || 'unknown'}`，已使用降级展示避免消息流中断。
      </p>
    </div>
  );
}
