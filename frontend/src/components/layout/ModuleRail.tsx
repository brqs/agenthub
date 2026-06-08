import { Archive, Bot, MessageSquare, Monitor, Moon, Settings, Sparkles, Sun, UserRound } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';
import type { ThemeMode, ThemePreference } from '@/stores/uiStore';

const navItems = [
  { to: '/chat', label: '聊天', icon: MessageSquare },
  { to: '/agents', label: 'Agent', icon: Bot },
  { to: '/archive', label: '归档', icon: Archive },
];

export function ModuleRail({
  themePreference,
  resolvedTheme,
  onCycleTheme,
  onOpenSettings,
  onToggleUserMenu,
  onChatClick,
  chatHref = '/chat',
}: {
  themePreference: ThemePreference;
  resolvedTheme: ThemeMode;
  onCycleTheme: () => void;
  onOpenSettings: () => void;
  onToggleUserMenu: () => void;
  onChatClick?: () => void;
  chatHref?: string;
}) {
  const ThemeIcon = themePreference === 'system' ? Monitor : resolvedTheme === 'dark' ? Moon : Sun;
  const themeTitle =
    themePreference === 'system'
      ? `主题：跟随系统（当前${resolvedTheme === 'dark' ? '深色' : '浅色'}）`
      : `主题：${resolvedTheme === 'dark' ? '深色' : '浅色'}`;

  return (
    <nav className="hidden h-full w-16 shrink-0 flex-col items-center border-r border-slate-200 bg-white py-4 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400 md:flex">
      <div className="mb-6 flex h-10 w-10 items-center justify-center rounded-2xl bg-brand text-white shadow-lg shadow-brand/25">
        <Sparkles className="h-5 w-5" />
      </div>

      <div className="flex flex-col gap-3">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to === '/chat' ? chatHref : item.to}
            className={({ isActive }) =>
              cn(
                'group relative flex h-11 w-11 items-center justify-center rounded-2xl transition',
                isActive
                  ? 'bg-brand text-white shadow-lg shadow-brand/20'
                  : 'hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white',
              )
            }
            title={item.label}
            onClick={item.to === '/chat' ? onChatClick : undefined}
          >
            <item.icon className="h-5 w-5" />
          </NavLink>
        ))}
      </div>

      <div className="mt-auto flex flex-col gap-3">
        <button
          type="button"
          onClick={onToggleUserMenu}
          className="flex h-11 w-11 items-center justify-center rounded-2xl hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
          title="用户菜单"
          aria-label="用户菜单"
        >
          <UserRound className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={onCycleTheme}
          className="flex h-11 w-11 items-center justify-center rounded-2xl hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
          title={themeTitle}
          aria-label={themeTitle}
        >
          <ThemeIcon className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={onOpenSettings}
          className="flex h-11 w-11 items-center justify-center rounded-2xl hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
          title="Settings"
          aria-label="Settings"
        >
          <Settings className="h-5 w-5" />
        </button>
      </div>
    </nav>
  );
}
