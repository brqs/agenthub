import { ContentRenderer } from '@/components/blocks/ContentRenderer';
import { AgentAvatar } from '@/components/agents/AgentAvatar';
import { indexArtifactsByPath } from '@/components/artifact/richArtifactModel';
import { ReviewThreadTimeline } from '@/components/chat/ReviewThreadTimeline';
import { useOrchestratorRunForMessage } from '@/hooks/useOrchestratorRuns';
import { useWorkspaceArtifacts } from '@/hooks/useWorkspace';
import type { DemoContentBlock, DemoMessage } from '@/lib/mockData';
import type { Agent } from '@/lib/types';
import { cn, formatTime } from '@/lib/utils';
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  AtSign,
  Check,
  Combine,
  Loader2,
  Pencil,
  Pin,
  RotateCcw,
  Route,
  Trash2,
  X,
  Zap,
} from 'lucide-react';
import { useEffect, useState } from 'react';

const EMPTY_ERROR_FALLBACK_TEXT = '调用失败：后端未返回错误详情，请重试。';
const EMPTY_ERROR_FALLBACK_BLOCK: DemoContentBlock = {
  type: 'text',
  text: EMPTY_ERROR_FALLBACK_TEXT,
};
const EMPTY_INTERRUPTED_FALLBACK_TEXT = '已打断本次回复，可以继续补充要求。';
const EMPTY_INTERRUPTED_FALLBACK_BLOCK: DemoContentBlock = {
  type: 'text',
  text: EMPTY_INTERRUPTED_FALLBACK_TEXT,
};

export function MessageBubble({
  message,
  highlighted = false,
  onTogglePin,
  onRetry,
  isRetrying = false,
  onMentionAgent,
  onUpdateQueuedMessage,
  onDeleteQueuedMessage,
  onMoveQueuedUp,
  onMoveQueuedDown,
  onMergeQueuedWithPrevious,
  onConvertQueuedToGuidance,
  onStopAndRunQueuedMessage,
  isInterrupting = false,
  agents = [],
}: {
  message: DemoMessage;
  highlighted?: boolean;
  onTogglePin?: (messageId: string) => void;
  onRetry?: (messageId: string) => void;
  isRetrying?: boolean;
  onMentionAgent?: (agent: Agent) => void;
  onUpdateQueuedMessage?: (messageId: string, text: string) => void | Promise<void>;
  onDeleteQueuedMessage?: (messageId: string) => void | Promise<void>;
  onMoveQueuedUp?: (messageId: string) => void | Promise<void>;
  onMoveQueuedDown?: (messageId: string) => void | Promise<void>;
  onMergeQueuedWithPrevious?: (messageId: string) => void | Promise<void>;
  onConvertQueuedToGuidance?: (messageId: string) => void | Promise<void>;
  onStopAndRunQueuedMessage?: (messageId: string) => void | Promise<void>;
  isInterrupting?: boolean;
  agents?: Agent[];
}) {
  const isUser = message.role === 'user';
  const isQueuedUser = isUser && message.status === 'queued';
  const agent = agents.find((item) => item.id === message.agent_id);
  const [mentionMenuPosition, setMentionMenuPosition] = useState<{ x: number; y: number } | null>(null);
  const [editingQueued, setEditingQueued] = useState(false);
  const [queuedDraft, setQueuedDraft] = useState(() => messageText(message));
  const [queuedActionError, setQueuedActionError] = useState<string | null>(null);
  const [queuedActionPending, setQueuedActionPending] = useState(false);
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

  useEffect(() => {
    if (!editingQueued) {
      setQueuedDraft(messageText(message));
    }
  }, [editingQueued, message]);

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

  async function saveQueuedEdit() {
    const value = queuedDraft.trim();
    if (!value || !onUpdateQueuedMessage) return;
    setQueuedActionPending(true);
    setQueuedActionError(null);
    try {
      await onUpdateQueuedMessage(message.id, value);
      setEditingQueued(false);
    } catch (error) {
      setQueuedActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setQueuedActionPending(false);
    }
  }

  async function deleteQueued() {
    if (!onDeleteQueuedMessage) return;
    setQueuedActionPending(true);
    setQueuedActionError(null);
    try {
      await onDeleteQueuedMessage(message.id);
    } catch (error) {
      setQueuedActionError(error instanceof Error ? error.message : String(error));
      setQueuedActionPending(false);
    }
  }

  async function moveQueuedUp() {
    if (!onMoveQueuedUp) return;
    setQueuedActionPending(true);
    setQueuedActionError(null);
    try {
      await onMoveQueuedUp(message.id);
    } catch (error) {
      setQueuedActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setQueuedActionPending(false);
    }
  }

  async function moveQueuedDown() {
    if (!onMoveQueuedDown) return;
    setQueuedActionPending(true);
    setQueuedActionError(null);
    try {
      await onMoveQueuedDown(message.id);
    } catch (error) {
      setQueuedActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setQueuedActionPending(false);
    }
  }

  async function mergeQueuedWithPrevious() {
    if (!onMergeQueuedWithPrevious) return;
    setQueuedActionPending(true);
    setQueuedActionError(null);
    try {
      await onMergeQueuedWithPrevious(message.id);
    } catch (error) {
      setQueuedActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setQueuedActionPending(false);
    }
  }

  async function convertQueuedToGuidance() {
    if (!onConvertQueuedToGuidance) return;
    setQueuedActionPending(true);
    setQueuedActionError(null);
    try {
      await onConvertQueuedToGuidance(message.id);
    } catch (error) {
      setQueuedActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setQueuedActionPending(false);
    }
  }

  async function stopAndRunQueued() {
    if (!onStopAndRunQueuedMessage) return;
    setQueuedActionPending(true);
    setQueuedActionError(null);
    try {
      await onStopAndRunQueuedMessage(message.id);
    } catch (error) {
      setQueuedActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setQueuedActionPending(false);
    }
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
          {!isUser && isInterrupting && (
            <span className="text-slate-500 dark:text-slate-400">正在停止</span>
          )}
          {!isUser && !isInterrupting && message.status === 'pending' && <span className="text-brand-light">正在准备</span>}
          {!isInterrupting && message.status === 'streaming' && <span className="text-brand-light">正在输入</span>}
          {message.status === 'error' && <span className="text-red-400">需要重试</span>}
          {message.status === 'interrupted' && (
            <span className="text-slate-500 dark:text-slate-400">已打断</span>
          )}
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
            isQueuedUser
              ? 'w-fit max-w-full border border-brand/25 bg-brand/10 px-4 py-2.5 text-slate-900 shadow-brand/5 dark:border-brand-light/25 dark:bg-brand-light/10 dark:text-slate-100'
              : isUser
              ? 'user-message-bubble w-fit max-w-full bg-brand px-4 py-2.5 text-white shadow-brand/10'
              : message.status === 'error'
                ? 'border border-red-300 bg-red-50 text-slate-950 dark:border-red-500/30 dark:bg-red-950/20 dark:text-slate-100'
                : message.status === 'interrupted'
                  ? 'border border-slate-300 bg-slate-50 text-slate-950 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100'
                : 'border border-slate-300 bg-white text-slate-950 shadow-black/5 dark:border-slate-800 dark:bg-slate-900/75 dark:text-slate-100 dark:shadow-black/10',
          )}
        >
          {editingQueued ? (
            <QueuedMessageEditor
              value={queuedDraft}
              isPending={queuedActionPending}
              error={queuedActionError}
              onChange={setQueuedDraft}
              onSave={() => void saveQueuedEdit()}
              onCancel={() => {
                setEditingQueued(false);
                setQueuedDraft(messageText(message));
                setQueuedActionError(null);
              }}
            />
          ) : (
            <MessageContent message={message} agents={agents} isInterrupting={isInterrupting} />
          )}
          {isQueuedUser && !editingQueued && (
            <QueuedMessageActions
              isPending={queuedActionPending}
              error={queuedActionError}
              canMoveUp={Boolean(onMoveQueuedUp)}
              canMoveDown={Boolean(onMoveQueuedDown)}
              canMergeWithPrevious={Boolean(onMergeQueuedWithPrevious)}
              canEdit={Boolean(onUpdateQueuedMessage)}
              canDelete={Boolean(onDeleteQueuedMessage)}
              canConvertToGuidance={Boolean(onConvertQueuedToGuidance)}
              canStopAndRun={Boolean(onStopAndRunQueuedMessage)}
              onMoveUp={() => void moveQueuedUp()}
              onMoveDown={() => void moveQueuedDown()}
              onMergeWithPrevious={() => void mergeQueuedWithPrevious()}
              onEdit={() => setEditingQueued(true)}
              onDelete={() => void deleteQueued()}
              onConvertToGuidance={() => void convertQueuedToGuidance()}
              onStopAndRun={() => void stopAndRunQueued()}
            />
          )}
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

function MessageContent({
  message,
  agents,
  isInterrupting = false,
}: {
  message: DemoMessage;
  agents: Agent[];
  isInterrupting?: boolean;
}) {
  const visibleBlocks = visibleMessageBlocks(message);
  if (isEmptyLiveAgentMessage(message, visibleBlocks)) {
    if (isInterrupting) {
      return <InterruptingEmptyState />;
    }
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

function isEmptyLiveAgentMessage(message: DemoMessage, visibleBlocks: DemoContentBlock[]): boolean {
  return (
    message.role !== 'user' &&
    (message.status === 'pending' || message.status === 'streaming') &&
    visibleBlocks.length === 0
  );
}

function QueuedMessageEditor({
  value,
  isPending,
  error,
  onChange,
  onSave,
  onCancel,
}: {
  value: string;
  isPending: boolean;
  error: string | null;
  onChange: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="min-w-[260px] space-y-2">
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={3}
        disabled={isPending}
        className="mobile-text-safe w-full resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-brand disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
      />
      {error && <p className="text-xs text-red-600 dark:text-red-300">{error}</p>}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={isPending}
          className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          <X className="h-3.5 w-3.5" />
          Cancel
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={isPending || !value.trim()}
          className="inline-flex items-center gap-1 rounded-md bg-brand px-2.5 py-1.5 text-xs font-medium text-white hover:bg-brand-hover disabled:opacity-50"
        >
          <Check className="h-3.5 w-3.5" />
          Save
        </button>
      </div>
    </div>
  );
}

function QueuedMessageActions({
  isPending,
  error,
  canMoveUp,
  canMoveDown,
  canMergeWithPrevious,
  canEdit,
  canDelete,
  canConvertToGuidance,
  canStopAndRun,
  onMoveUp,
  onMoveDown,
  onMergeWithPrevious,
  onEdit,
  onDelete,
  onConvertToGuidance,
  onStopAndRun,
}: {
  isPending: boolean;
  error: string | null;
  canMoveUp: boolean;
  canMoveDown: boolean;
  canMergeWithPrevious: boolean;
  canEdit: boolean;
  canDelete: boolean;
  canConvertToGuidance: boolean;
  canStopAndRun: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onMergeWithPrevious: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onConvertToGuidance: () => void;
  onStopAndRun: () => void;
}) {
  return (
    <div className="mt-2 flex items-center justify-between gap-3 border-t border-brand/15 pt-2 text-xs text-slate-500 dark:border-brand-light/15 dark:text-slate-400">
      <span>Queued</span>
      {error && <span className="min-w-0 flex-1 truncate text-red-600 dark:text-red-300">{error}</span>}
      <div className="flex shrink-0 items-center gap-1">
        {canMoveUp && (
          <button
            type="button"
            onClick={onMoveUp}
            disabled={isPending}
            className="rounded-md p-1.5 text-slate-500 hover:bg-white/70 hover:text-slate-950 disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-white"
            title="Move queued message up"
            aria-label="Move queued message up"
          >
            <ArrowUp className="h-3.5 w-3.5" />
          </button>
        )}
        {canMoveDown && (
          <button
            type="button"
            onClick={onMoveDown}
            disabled={isPending}
            className="rounded-md p-1.5 text-slate-500 hover:bg-white/70 hover:text-slate-950 disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-white"
            title="Move queued message down"
            aria-label="Move queued message down"
          >
            <ArrowDown className="h-3.5 w-3.5" />
          </button>
        )}
        {canMergeWithPrevious && (
          <button
            type="button"
            onClick={onMergeWithPrevious}
            disabled={isPending}
            className="rounded-md p-1.5 text-slate-500 hover:bg-white/70 hover:text-brand disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-brand-light"
            title="Merge queued message with previous"
            aria-label="Merge queued message with previous"
          >
            <Combine className="h-3.5 w-3.5" />
          </button>
        )}
        {canConvertToGuidance && (
          <button
            type="button"
            onClick={onConvertToGuidance}
            disabled={isPending}
            className="rounded-md p-1.5 text-slate-500 hover:bg-white/70 hover:text-brand disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-brand-light"
            title="Convert queued message to guidance"
            aria-label="Convert queued message to guidance"
          >
            <Route className="h-3.5 w-3.5" />
          </button>
        )}
        {canStopAndRun && (
          <button
            type="button"
            onClick={onStopAndRun}
            disabled={isPending}
            className="rounded-md p-1.5 text-slate-500 hover:bg-white/70 hover:text-brand disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-brand-light"
            title="Stop current reply and run this queued message"
            aria-label="Stop current reply and run this queued message"
          >
            <Zap className="h-3.5 w-3.5" />
          </button>
        )}
        {canEdit && (
          <button
            type="button"
            onClick={onEdit}
            disabled={isPending}
            className="rounded-md p-1.5 text-slate-500 hover:bg-white/70 hover:text-slate-950 disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-white"
            title="Edit queued message"
            aria-label="Edit queued message"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        )}
        {canDelete && (
          <button
            type="button"
            onClick={onDelete}
            disabled={isPending}
            className="rounded-md p-1.5 text-slate-500 hover:bg-white/70 hover:text-red-600 disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-red-300"
            title="Delete queued message"
            aria-label="Delete queued message"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

function messageText(message: DemoMessage): string {
  return message.content
    .filter((block): block is DemoContentBlock & { type: 'text'; text: string } => block.type === 'text')
    .map((block) => block.text)
    .join('\n');
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

function InterruptingEmptyState() {
  const label = '正在停止本次回复...';

  return (
    <div
      className="flex min-h-5 items-center gap-2 text-sm text-slate-500 dark:text-slate-400"
      role="status"
      aria-live="polite"
      aria-label={label}
    >
      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-slate-400" />
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
  if (message.status === 'interrupted' && message.content.length === 0) {
    return [EMPTY_INTERRUPTED_FALLBACK_BLOCK];
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
    message.status === 'done' || message.status === 'error' || message.status === 'interrupted',
  );

  return <ReviewThreadTimeline detail={runDetailQuery.data} agents={agents} />;
}
