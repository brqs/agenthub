import { Archive, Bot, MessageSquare, Moon, Settings, Sparkles } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';

const navItems = [
  { to: '/chat', label: '聊天', icon: MessageSquare },
  { to: '/agents', label: 'Agent', icon: Bot },
];

export function ModuleRail({ onLogout }: { onLogout: () => void }) {
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
          className="flex h-11 w-11 items-center justify-center rounded-2xl hover:bg-slate-800 hover:text-white"
          title="归档"
        >
          <Archive className="h-5 w-5" />
        </button>
        <button
          type="button"
          className="flex h-11 w-11 items-center justify-center rounded-2xl hover:bg-slate-800 hover:text-white"
          title="主题"
        >
          <Moon className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={onLogout}
          className="flex h-11 w-11 items-center justify-center rounded-2xl hover:bg-slate-800 hover:text-white"
          title="退出登录"
        >
          <Settings className="h-5 w-5" />
        </button>
      </div>
    </nav>
  );
}

