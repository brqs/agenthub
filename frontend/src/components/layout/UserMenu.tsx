import { LogOut, UserRound, X } from 'lucide-react';
import type { User } from '@/lib/types';

export function UserMenu({
  user,
  onLogout,
  onClose,
}: {
  user: User | null;
  onLogout: () => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-50 rounded-t-xl border border-slate-300 bg-white p-3 pb-[max(env(safe-area-inset-bottom),0.75rem)] shadow-2xl shadow-black/20 dark:border-slate-800 dark:bg-slate-900 dark:shadow-black/40 md:absolute md:bottom-4 md:left-20 md:right-auto md:w-72 md:rounded-md">
      <div className="mb-3 flex items-center gap-3 border-b border-slate-200 pb-3 dark:border-slate-800">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-brand text-white">
          <UserRound className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-950 dark:text-white">
            {user?.username ?? '未登录'}
          </div>
          <div className="text-xs text-slate-600 dark:text-slate-500">Real API</div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="ml-auto rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white md:hidden"
          aria-label="关闭账号菜单"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <button
        type="button"
        onClick={() => {
          onClose();
          onLogout();
        }}
        className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-slate-700 transition hover:bg-slate-100 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
      >
        <LogOut className="h-4 w-4" />
        退出登录
      </button>
    </div>
  );
}
