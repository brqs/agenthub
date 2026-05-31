import { LogOut, UserRound } from 'lucide-react';
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
    <div className="absolute bottom-4 left-20 z-40 w-72 rounded-md border border-slate-800 bg-slate-900 p-3 shadow-2xl shadow-black/40">
      <div className="mb-3 flex items-center gap-3 border-b border-slate-800 pb-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-brand text-white">
          <UserRound className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-white">
            {user?.username ?? '未登录'}
          </div>
          <div className="text-xs text-slate-500">Real API</div>
        </div>
      </div>
      <button
        type="button"
        onClick={() => {
          onClose();
          onLogout();
        }}
        className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-800 hover:text-white"
      >
        <LogOut className="h-4 w-4" />
        退出登录
      </button>
    </div>
  );
}
