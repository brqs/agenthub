import { ContentRenderer } from '@/components/blocks/ContentRenderer';
import { AgentAvatar } from '@/components/agents/AgentAvatar';
import { indexArtifactsByPath } from '@/components/artifact/richArtifactModel';
import { ReviewThreadTimeline } from '@/components/chat/ReviewThreadTimeline';
import { useOrchestratorRunForMessage } from '@/hooks/useOrchestratorRuns';
import { useWorkspaceArtifacts } from '@/hooks/useWorkspace';
import type { DemoContentBlock, DemoMessage } from '@/lib/mockData';
import type { Agent } from '@/lib/types';
import { cn, formatTime } from '@/lib/utils';
import { AlertTriangle, AtSign, Loader2, Pin, RotateCcw } from 'lucide-react';
import { useEffect, useState } from 'react';

const EMPTY_ERROR_FALLBACK_TEXT = '调用失败：后端未返回错误详情，请重试。';
const EMPTY_ERROR_FALLBACK_BLOCK: DemoContentBlock = {
  type: 'text',
  text: EMPTY_ERROR_FALLBACK_TEXT,
};

export function MessageBubble({
  message,
  highlighted = false,
  onTogglePin,
  onRetry,
  isRetrying = false,
  onMentionAgent,
  agents = [],
}: {
  message: DemoMessage;
  highlighted?: boolean;
  onTogglePin?: (messageId: string) => void;
  onRetry?: (messageId: string) => void;
  isRetrying?: boolean;
  onMentionAgent?: (agent: Agent) => void;
  agents?: Agent[];
}) {
  const isUser = message.role === 'user';
  const agent = agents.find((item) => item.id === message.agent_id);
  const [mentionMenuPosition, setMentionMenuPosition] = useState<{ x: number; y: number } | null>(null);
  const canMentionAgent = !isUser && agent !== undefined && onMentionAgent !== undefined;

  useEffect(() => {
    if (!mentionMenuPosition) return undefined;

    function closeMenu() {
      setMentionMenuPosition(null);
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') closeMenu();
    }

    window.addEventListener('click', closeMenu);
    window.addEventListener('scroll', closeMenu, true);
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      window.removeEventListener('click', closeMenu);
      window.removeEventListener('scroll', closeMenu, true);
      window.removeEventListener('keydown', closeOnEscape);
    };
  }, [mentionMenuPosition]);

  function openMentionMenu(event: React.MouseEvent<HTMLDivElement>) {
    if (!canMentionAgent) return;
    event.preventDefault();
    setMentionMenuPosition({ x: event.clientX, y: event.clientY });
  }

  function mentionAgent() {
    if (!agent || !onMentionAgent) return;
    onMentionAgent(agent);
    setMentionMenuPosition(null);
  }

  return (
    <article
      className={cn(
        'group flex min-w-0 max-w-full gap-2 rounded-md px-1 py-1 transition-colors sm:gap-3',
        isUser && 'justify-end',
        highlighted && 'bg-brand/10 ring-1 ring-brand/40',
      )}
    >
      {!isUser && (
        <div className="flex shrink-0 flex-col items-center gap-1 pt-6">
          <div
            className={cn(canMentionAgent && 'cursor-context-menu')}
            onContextMenu={openMentionMenu}
            title={canMentionAgent ? `右键 @${agent.name}` : undefined}
          >
            <AgentAvatar agent={agent} />
          </div>
          {canMentionAgent && (
            <button
              type="button"
              onClick={mentionAgent}
              className="rounded-md p-1 text-slate-500 hover:bg-slate-100 hover:text-brand dark:hover:bg-slate-800 dark:hover:text-brand-light md:hidden"
              aria-label={`@ ${agent.name}`}
            >
              <AtSign className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}
      <div className={cn(isUser ? 'order-1 flex min-w-0 max-w-[min(680px,88%)] flex-col items-end sm:max-w-[min(680px,78%)]' : 'min-w-0 max-w-full flex-1')}>
        <div className={cn('mb-1.5 flex min-w-0 max-w-full items-center gap-2 px-1 text-xs text-slate-500', isUser && 'justify-end')}>
          <span className="font-medium text-slate-800 dark:text-slate-300">{isUser ? '你' : agent?.name ?? 'Agent'}</span>
          <span>{formatTime(message.created_at)}</span>
          {message.status === 'streaming' && <span className="text-brand-light">正在输入</span>}
          {message.status === 'error' && <span className="text-red-400">需要重试</span>}
          {onTogglePin && (
            <button
              type="button"
              onClick={() => onTogglePin(message.id)}
              className={cn(
                'ml-1 rounded-md p-1 transition hover:bg-slate-100 hover:text-slate-950 group-hover:opacity-100 dark:hover:bg-slate-800 dark:hover:text-white',
                message.is_pinned ? 'text-brand opacity-100 dark:text-brand-light' : 'text-slate-500 opacity-100 md:opacity-0 dark:text-slate-600',
              )}
              title={message.is_pinned ? '取消 Pin' : 'Pin 消息'}
              aria-label={message.is_pinned ? '取消 Pin' : 'Pin 消息'}
            >
              <Pin className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        <div
          className={cn(
            'mobile-text-safe min-w-0 max-w-full overflow-visible rounded-md px-3 py-3 shadow-sm sm:px-4',
            isUser
              ? 'user-message-bubble w-fit max-w-full bg-brand px-4 py-2.5 text-white shadow-brand/10'
              : message.status === 'error'
                ? 'border border-red-300 bg-red-50 text-slate-950 dark:border-red-500/30 dark:bg-red-950/20 dark:text-slate-100'
                : 'border border-slate-300 bg-white text-slate-950 shadow-black/5 dark:border-slate-800 dark:bg-slate-900/75 dark:text-slate-100 dark:shadow-black/10',
          )}
        >
          <MessageContent message={message} agents={agents} />
          {!isUser && message.agent_id === 'orchestrator' && (
            <ReviewThreadForMessage message={message} agents={agents} />
          )}
          {message.status === 'error' && onRetry && (
            <button
              type="button"
              disabled={isRetrying}
              onClick={() => onRetry(message.id)}
              className="mt-3 inline-flex items-center gap-2 rounded-md border border-red-300 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-red-500/30 dark:text-red-100 dark:hover:bg-red-500/10"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              {isRetrying ? '重试中' : '重试'}
            </button>
          )}
        </div>
      </div>
      {mentionMenuPosition && agent && (
        <div
          role="menu"
          className="fixed z-50 min-w-40 overflow-hidden rounded-md border border-slate-300 bg-white p-1 shadow-xl shadow-black/15 dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/30"
          style={{ left: mentionMenuPosition.x, top: mentionMenuPosition.y }}
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            role="menuitem"
            onClick={mentionAgent}
            className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm text-slate-900 transition hover:bg-brand/10 hover:text-brand dark:text-slate-200 dark:hover:bg-brand/15 dark:hover:text-brand-light"
          >
            @ {agent.name}
          </button>
        </div>
      )}
    </article>
  );
}

function MessageContent({ message, agents }: { message: DemoMessage; agents: Agent[] }) {
  const visibleBlocks = visibleMessageBlocks(message);
  if (message.status === 'streaming' && visibleBlocks.length === 0) {
    return <StreamingEmptyState isOrchestrator={message.agent_id === 'orchestrator'} />;
  }

  const failureBlocks: Array<DemoContentBlock & { type: 'text'; text: string }> =
    message.status === 'error' ? visibleBlocks.filter(isFailureTextBlock) : [];
  const contentBlocks =
    failureBlocks.length > 0
      ? visibleBlocks.filter((block) => !isFailureTextBlock(block))
      : visibleBlocks;
  const hasFileBlock = contentBlocks.some((block) => block.type === 'file');
  const contentRenderer =
    contentBlocks.length === 0 ? null : hasFileBlock ? (
      <ManifestAwareMessageContent message={message} agents={agents} blocks={contentBlocks} />
    ) : (
      <ContentRenderer
        blocks={contentBlocks}
        agents={agents}
        streaming={message.status === 'streaming'}
        conversationId={message.conversation_id}
      />
    );

  if (failureBlocks.length > 0) {
    const firstFailureBlock = failureBlocks[0];
    const failureText =
      firstFailureBlock?.type === 'text'
        ? firstFailureBlock.text
        : EMPTY_ERROR_FALLBACK_TEXT;
    return (
      <div className="space-y-3">
        <FailureCard text={failureText} />
        {contentRenderer}
      </div>
    );
  }

  if (!hasFileBlock) {
    return contentRenderer;
  }
  return contentRenderer;
}

function ManifestAwareMessageContent({
  message,
  agents,
  blocks,
}: {
  message: DemoMessage;
  agents: Agent[];
  blocks: DemoContentBlock[];
}) {
  const artifactsQuery = useWorkspaceArtifacts(message.conversation_id, true);
  const artifactManifestByPath = indexArtifactsByPath(artifactsQuery.data);

  return (
    <ContentRenderer
      blocks={blocks}
      agents={agents}
      streaming={message.status === 'streaming'}
      conversationId={message.conversation_id}
      artifactManifestByPath={artifactManifestByPath}
    />
  );
}

function StreamingEmptyState({ isOrchestrator }: { isOrchestrator: boolean }) {
  const label = isOrchestrator ? '正在分析请求...' : '正在组织回复...';

  return (
    <div
      className="flex min-h-5 items-center gap-2 text-sm text-slate-500 dark:text-slate-400"
      role="status"
      aria-live="polite"
      aria-label={label}
    >
      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-brand-light" />
      <span>{label}</span>
    </div>
  );
}

function FailureCard({ text }: { text: string }) {
  return (
    <section className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-900 dark:border-rose-400/25 dark:bg-rose-950/25 dark:text-rose-100">
      <div className="flex min-w-0 items-start gap-2">
        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-rose-100 text-rose-700 dark:bg-rose-400/10 dark:text-rose-200">
          <AlertTriangle className="h-3.5 w-3.5" />
        </span>
        <div className="min-w-0">
          <div className="text-xs font-semibold uppercase tracking-wide text-rose-700 dark:text-rose-200">
            调用失败
          </div>
          <p className="mt-1 line-clamp-3 break-words text-xs leading-5">{text}</p>
        </div>
      </div>
    </section>
  );
}

export function visibleMessageBlocks(message: DemoMessage): DemoContentBlock[] {
  if (message.status === 'error' && message.content.length === 0) {
    return [EMPTY_ERROR_FALLBACK_BLOCK];
  }
  if (message.agent_id !== 'orchestrator') {
    return message.content;
  }
  const filtered: DemoContentBlock[] = [];
  let keptFailureText = false;
  for (const block of message.content) {
    if (isLegacyOrchestratorTraceBlock(block)) continue;
    if (isFailureTextBlock(block)) {
      if (keptFailureText) continue;
      keptFailureText = true;
    }
    filtered.push(block);
  }
  if (message.status === 'error' && filtered.length === 0) {
    return [EMPTY_ERROR_FALLBACK_BLOCK];
  }
  return filtered;
}

function isLegacyOrchestratorTraceBlock(block: DemoContentBlock): boolean {
  if (block.type !== 'text') return false;
  const text = block.text.trim();
  return (
    text.startsWith('ReAct step ') ||
    text.startsWith('Execution summary') ||
    /^Planned \d+ sub-task\(s\)/.test(text)
  );
}

function isFailureTextBlock(block: DemoContentBlock): block is DemoContentBlock & { type: 'text'; text: string } {
  if (block.type !== 'text') return false;
  const text = block.text.trim();
  return text.startsWith('调用失败') || text.startsWith('failed:') || text.startsWith('orchestrator_task_failed:');
}

function ReviewThreadForMessage({ message, agents }: { message: DemoMessage; agents: Agent[] }) {
  const runDetailQuery = useOrchestratorRunForMessage(
    message.conversation_id,
    message.id,
    message.status === 'done' || message.status === 'error',
  );

  return <ReviewThreadTimeline detail={runDetailQuery.data} agents={agents} />;
}
