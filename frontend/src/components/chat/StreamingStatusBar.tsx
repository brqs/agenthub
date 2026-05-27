import { Loader2 } from 'lucide-react';
import { getStreamingStatus } from './streamingStatus';
import type { DemoMessage } from '@/lib/mockData';
import { mockAgents } from '@/lib/mockData';
import type { Agent } from '@/lib/types';

export function StreamingStatusBar({
  messages,
  agents = mockAgents,
}: {
  messages: DemoMessage[];
  agents?: Agent[];
}) {
  const status = getStreamingStatus(messages, agents);
  if (!status) return null;

  const Icon = status.Icon;

  return (
    <div
      className="border-b border-slate-800 bg-slate-950/80 px-5 py-2"
      role="status"
      aria-live="polite"
    >
      <div className="mx-auto flex max-w-5xl items-center gap-2 rounded-md border border-brand/25 bg-brand/10 px-3 py-2 text-sm text-slate-200">
        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-brand-light" />
        <Icon className="h-4 w-4 shrink-0 text-slate-500" />
        <span className="min-w-0 truncate">
          <span className="font-medium text-white">{status.agentName}</span> {status.label}
        </span>
      </div>
    </div>
  );
}
