import { Archive, Bot, MessageSquare, Moon, Settings, Sparkles, Sun, UserRound } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';
import type { ThemeMode } from '@/stores/uiStore';

const navItems = [
  { to: '/chat', label: '聊天', icon: MessageSquare },
  { to: '/agents', label: 'Agent', icon: Bot },
  { to: '/archive', label: '归档', icon: Archive },
];

export function ModuleRail({
  theme,
  onToggleTheme,
  onOpenSettings,
  onToggleUserMenu,
}: {
  theme: ThemeMode;
  onToggleTheme: () => void;
  onOpenSettings: () => void;
  onToggleUserMenu: () => void;
}) {
  const ThemeIcon = theme === 'dark' ? Moon : Sun;

  return (
    <nav className="flex h-screen w-16 shrink-0 flex-col items-center border-r border-slate-800 bg-slate-950 py-4 text-slate-400">
      <div className="mb-6 flex h-10 w-10 items-center justify-center rounded-2xl bg-brand text-white shadow-lg shadow-brand/25">
        <Sparkles className="h-5 w-5" />
      </div>

      <div className="flex flex-col gap-3">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                'group relative flex h-11 w-11 items-center justify-center rounded-2xl transition',
                isActive
                  ? 'bg-brand text-white shadow-lg shadow-brand/20'
                  : 'hover:bg-slate-800 hover:text-white',
              )
            }
            title={item.label}
          >
            <item.icon className="h-5 w-5" />
          </NavLink>
        ))}
      </div>

      <div className="mt-auto flex flex-col gap-3">
        <button
          type="button"
          onClick={onToggleUserMenu}
          className="flex h-11 w-11 items-center justify-center rounded-2xl hover:bg-slate-800 hover:text-white"
          title="用户菜单"
          aria-label="用户菜单"
        >
          <UserRound className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={onToggleTheme}
          className="flex h-11 w-11 items-center justify-center rounded-2xl hover:bg-slate-800 hover:text-white"
          title="主题"
          aria-label="主题"
        >
          <ThemeIcon className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={onOpenSettings}
          className="flex h-11 w-11 items-center justify-center rounded-2xl hover:bg-slate-800 hover:text-white"
          title="Settings"
          aria-label="Settings"
        >
          <Settings className="h-5 w-5" />
        </button>
      </div>
    </nav>
  );
}
