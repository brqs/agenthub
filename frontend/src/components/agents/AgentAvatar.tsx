import { Bot } from 'lucide-react';
import type { Agent } from '@/lib/types';
import { cn } from '@/lib/utils';

const PROVIDER_STYLES: Record<Agent['provider'], string> = {
  claude: 'bg-agent-claude text-white',
  deepseek: 'bg-agent-deepseek text-white',
  openai: 'bg-agent-openai text-white',
  custom: 'bg-agent-orchestrator text-white',
  mock: 'bg-slate-700 text-slate-100',
};

export function AgentAvatar({
  agent,
  size = 'md',
}: {
  agent?: Agent;
  size?: 'sm' | 'md' | 'lg';
}) {
  const sizeClass = {
    sm: 'h-7 w-7 text-xs',
    md: 'h-9 w-9 text-sm',
    lg: 'h-11 w-11 text-base',
  }[size];

  return (
    <div
      className={cn(
        'flex shrink-0 items-center justify-center rounded-full font-semibold shadow-sm',
        sizeClass,
        agent ? PROVIDER_STYLES[agent.provider] : 'bg-slate-700 text-slate-200',
      )}
    >
      {agent ? agent.name.slice(0, 1).toUpperCase() : <Bot className="h-4 w-4" />}
    </div>
  );
}

