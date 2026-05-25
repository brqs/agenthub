import { Bot, PanelsTopLeft, Workflow } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { ComponentType } from 'react';
import anthropicLogo from '@/assets/agent-logos/anthropic.svg';
import deepseekLogo from '@/assets/agent-logos/deepseek.svg';
import openaiLogo from '@/assets/agent-logos/openai.svg';
import type { Agent } from '@/lib/types';
import { cn } from '@/lib/utils';

const PROVIDER_STYLES: Record<Agent['provider'], string> = {
  claude: 'bg-agent-claude text-white',
  deepseek: 'bg-agent-deepseek text-white',
  openai: 'bg-agent-openai text-white',
  custom: 'bg-agent-orchestrator text-white',
  mock: 'bg-slate-700 text-slate-100',
};

const PROVIDER_LOGOS: Partial<Record<Agent['provider'], string>> = {
  claude: anthropicLogo,
  deepseek: deepseekLogo,
  openai: openaiLogo,
};

const AGENT_ICONS: Record<string, ComponentType<{ className?: string }>> = {
  orchestrator: Workflow,
  'web-designer': PanelsTopLeft,
};

export function AgentAvatar({
  agent,
  size = 'md',
}: {
  agent?: Agent;
  size?: 'sm' | 'md' | 'lg';
}) {
  const [logoFailed, setLogoFailed] = useState(false);
  const sizeClass = {
    sm: 'h-7 w-7 text-xs',
    md: 'h-9 w-9 text-sm',
    lg: 'h-11 w-11 text-base',
  }[size];
  const logoSizeClass = {
    sm: 'h-5 w-5',
    md: 'h-7 w-7',
    lg: 'h-8 w-8',
  }[size];
  const AgentIcon = agent ? AGENT_ICONS[agent.id] : undefined;
  const logoSrc = agent && !logoFailed && AgentIcon === undefined ? PROVIDER_LOGOS[agent.provider] : undefined;
  const logoAlt = agent ? `${agent.name} logo` : 'Agent logo';
  const shouldInvertLogo =
    agent !== undefined &&
    AgentIcon === undefined &&
    (agent.provider === 'claude' || agent.provider === 'openai');

  useEffect(() => {
    setLogoFailed(false);
  }, [agent?.id, agent?.provider]);

  return (
    <div
      className={cn(
        'flex shrink-0 items-center justify-center rounded-full font-semibold shadow-sm',
        sizeClass,
        logoSrc || AgentIcon
          ? 'border border-slate-200 bg-white text-slate-950 dark:border-slate-700 dark:bg-slate-950 dark:ring-1 dark:ring-white/10'
          : agent
            ? PROVIDER_STYLES[agent.provider]
            : 'bg-slate-700 text-slate-200',
      )}
    >
      {AgentIcon ? (
        <AgentIcon className={cn(logoSizeClass, 'text-brand dark:text-brand-light')} />
      ) : logoSrc ? (
        <img
          src={logoSrc}
          alt={logoAlt}
          className={cn('object-contain', logoSizeClass, shouldInvertLogo && 'dark:invert')}
          draggable={false}
          onError={() => setLogoFailed(true)}
        />
      ) : agent ? (
        agent.name.slice(0, 1).toUpperCase()
      ) : (
        <Bot className="h-4 w-4" />
      )}
    </div>
  );
}
