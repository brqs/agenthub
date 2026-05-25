import { Activity, ChevronRight, Pin, ShieldCheck } from 'lucide-react';
import { AgentAvatar } from './AgentAvatar';
import type { DemoConversation, DemoMessage } from '@/lib/mockData';
import { getAgent } from '@/lib/mockData';

export function RightAgentPanel({
  conversation,
  messages,
}: {
  conversation: DemoConversation;
  messages: DemoMessage[];
}) {
  const agents = conversation.agent_ids.map(getAgent).filter((agent) => agent !== undefined);
  const pinned = messages.filter((message) => message.is_pinned);

  return (
    <aside className="hidden h-screen w-80 shrink-0 flex-col border-l border-slate-800 bg-slate-900 xl:flex">
      <div className="border-b border-slate-800 p-5">
        <div className="flex items-center gap-3">
          <div className="flex -space-x-2">
            {agents.slice(0, 3).map((agent) => (
              <AgentAvatar key={agent.id} agent={agent} />
            ))}
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-white">会话上下文</h2>
            <p className="text-xs text-slate-500">{conversation.mode === 'group' ? '群聊协作中' : '单 Agent 单聊'}</p>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-5 scrollbar-thin">
        <section>
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <Activity className="h-3.5 w-3.5" />
            Agents
          </div>
          <div className="space-y-3">
            {agents.map((agent) => (
              <div key={agent.id} className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
                <div className="flex items-center gap-3">
                  <AgentAvatar agent={agent} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-white">{agent.name}</div>
                    <div className="text-xs text-slate-500">{agent.provider}</div>
                  </div>
                  <ChevronRight className="h-4 w-4 text-slate-600" />
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {agent.capabilities.map((capability) => (
                    <span key={capability} className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300">
                      {capability}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-7">
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <Pin className="h-3.5 w-3.5" />
            Pin 消息
          </div>
          {pinned.length ? (
            <div className="space-y-2">
              {pinned.map((message) => (
                <div key={message.id} className="rounded-md bg-slate-950/60 p-3 text-xs text-slate-400">
                  {message.content[0]?.type === 'text' ? message.content[0].text : '富媒体内容'}
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-slate-800 p-4 text-sm text-slate-500">
              暂无 Pin 消息
            </div>
          )}
        </section>

        <section className="mt-7 rounded-md border border-slate-800 bg-slate-950/60 p-4">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-white">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            Mock 模式
          </div>
          <p className="text-sm leading-6 text-slate-500">
            当前 UI 使用本地 Mock 数据，后续会从 Hook 层替换为真实 API 与 SSE。
          </p>
        </section>
      </div>
    </aside>
  );
}

