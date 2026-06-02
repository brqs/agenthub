import { Archive, Bot, MessageSquare, Settings } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';

const navItems = [
  { to: '/chat', label: '聊天', icon: MessageSquare },
  { to: '/agents', label: 'Agent', icon: Bot },
  { to: '/archive', label: '归档', icon: Archive },
];

export function MobileBottomNav({ onOpenSettings }: { onOpenSettings: () => void }) {
  return (
    <nav className="surface-panel z-40 grid shrink-0 grid-cols-4 border-t border-slate-200 px-2 pb-[max(env(safe-area-inset-bottom),0.25rem)] pt-1 dark:border-slate-800 md:hidden">
      {navItems.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            cn(
              'flex min-h-12 flex-col items-center justify-center gap-1 rounded-md px-2 text-[11px] font-medium transition',
              isActive
                ? 'text-brand-light'
                : 'text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white',
            )
          }
        >
          <item.icon className="h-4 w-4" />
          <span>{item.label}</span>
        </NavLink>
      ))}
      <button
        type="button"
        onClick={onOpenSettings}
        className="flex min-h-12 flex-col items-center justify-center gap-1 rounded-md px-2 text-[11px] font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
      >
        <Settings className="h-4 w-4" />
        <span>设置</span>
      </button>
    </nav>
  );
}
