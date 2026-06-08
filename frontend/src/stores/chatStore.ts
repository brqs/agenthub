import { create } from 'zustand';
import {
  type DemoContentBlock,
  type DemoConversation,
  type DemoMessage,
  type ClarificationBlock,
  type ProcessBlock,
  type TaskCardBlock,
  type TaskStatus,
} from '@/lib/mockData';
import type {
  Conversation,
  Message,
  PresentationMetadata,
  StreamEvent,
  TurnControlBlock,
} from '@/lib/types';

type SortableMessage = Pick<
  Message,
  'id' | 'role' | 'reply_to_id' | 'created_at' | 'status' | 'queue_position'
>;

interface ChatState {
  conversations: DemoConversation[];
  messagesByConversation: Record<string, DemoMessage[]>;
  activeStreams: Record<
    string,
    {
      messageId: string;
      conversationId: string;
      agentId: string | null;
      startedAt: string;
      interrupting?: boolean;
    }
  >;
  selectedConversationId: string;
  search: string;
  highlightedMessageId: string | null;
  setSelectedConversationId: (conversationId: string) => void;
  setSearch: (search: string) => void;
  setHighlightedMessageId: (messageId: string | null) => void;
  toggleMessagePin: (messageId: string) => void;
  toggleConversationPin: (conversationId: string) => void;
  toggleConversationArchive: (conversationId: string) => void;
  applyStreamEvent: (messageId: string, event: StreamEvent) => void;
  startActiveStream: (message: Pick<Message, 'id' | 'conversation_id' | 'agent_id'>) => void;
  setActiveStreamInterrupting: (messageId: string, interrupting: boolean) => void;
  finishActiveStream: (messageId: string) => void;
  resetMessageForRetry: (messageId: string) => void;
  /** Prepend a freshly created conversation (returned by POST /conversations). */
  addConversation: (conversation: Conversation) => void;
  /** Replace the conversation list (used to mirror server state in API mode). */
  hydrateConversations: (conversations: Conversation[]) => void;
  /** Replace messages for a single conversation (used on initial fetch in API mode). */
  hydrateMessages: (conversationId: string, messages: Message[]) => void;
  /** Append the {user_message, agent_message} pair returned by POST /messages. */
  appendRemoteExchange: (
    conversationId: string,
    userMessage: Message,
    agentMessage: Message,
  ) => void;
  appendQueuedMessage: (conversationId: string, queuedMessage: Message) => void;
  updateConversationLocal: (conversation: Conversation) => void;
  updateMessageLocal: (message: Message) => void;
  replaceMessageLocal: (oldMessageId: string, message: Message) => void;
  removeMessageLocal: (messageId: string) => void;
  clearChat: () => void;
}

const PRESENTATION_ROLES = new Set<PresentationMetadata['role']>([
  'execution_process',
  'tool_trace',
  'execution_text',
  'artifact_evidence',
  'agent_summary',
  'final_answer',
]);
const PRESENTATION_BOUNDARIES = new Set<NonNullable<PresentationMetadata['boundary']>>([
  'execution_start',
  'answer_start',
]);

function presentationFromMetadata(
  metadata: Record<string, unknown> | undefined,
): PresentationMetadata | null {
  const raw = metadata?.presentation;
  if (!raw || typeof raw !== 'object') return null;
  const value = raw as Record<string, unknown>;
  const role = value.role;
  if (typeof role !== 'string' || !PRESENTATION_ROLES.has(role as PresentationMetadata['role'])) {
    return null;
  }
  const presentation: PresentationMetadata = {
    role: role as PresentationMetadata['role'],
    collapsible: Boolean(value.collapsible),
  };
  if (
    typeof value.boundary === 'string' &&
    PRESENTATION_BOUNDARIES.has(value.boundary as NonNullable<PresentationMetadata['boundary']>)
  ) {
    presentation.boundary = value.boundary as NonNullable<PresentationMetadata['boundary']>;
  }
  if (typeof value.group_id === 'string' && value.group_id) {
    presentation.group_id = value.group_id;
  }
  if (typeof value.closes_group_id === 'string' && value.closes_group_id) {
    presentation.closes_group_id = value.closes_group_id;
  }
  if (typeof value.label === 'string' && value.label) {
    presentation.label = value.label;
  }
  return presentation;
}

function defaultExecutionPresentation(label = '执行过程'): PresentationMetadata {
  return {
    role: 'execution_process',
    collapsible: true,
    group_id: 'execution-main',
    label,
  };
}

function roleRank(role: SortableMessage['role']): number {
  if (role === 'user') return 0;
  if (role === 'agent') return 1;
  return 2;
}

function messageTime(message: SortableMessage): number {
  const time = Date.parse(message.created_at);
  return Number.isFinite(time) ? time : 0;
}

function compareMessages(a: SortableMessage, b: SortableMessage): number {
  if (a.reply_to_id === b.id) return 1;
  if (b.reply_to_id === a.id) return -1;

  if (a.status === 'queued' && b.status === 'queued') {
    const positionDiff = (a.queue_position ?? Number.MAX_SAFE_INTEGER) -
      (b.queue_position ?? Number.MAX_SAFE_INTEGER);
    if (positionDiff !== 0) return positionDiff;
  }

  const timeDiff = messageTime(a) - messageTime(b);
  if (timeDiff !== 0) return timeDiff;

  const roleDiff = roleRank(a.role) - roleRank(b.role);
  if (roleDiff !== 0) return roleDiff;

  return a.id.localeCompare(b.id);
}

export function sortMessagesForDisplay<T extends SortableMessage>(messages: T[]): T[] {
  const byId = new Map(messages.map((message) => [message.id, message]));
  const childrenByParent = new Map<string, T[]>();
  const baseSorted = [...messages].sort(compareMessages);

  for (const message of baseSorted) {
    if (!message.reply_to_id || !byId.has(message.reply_to_id)) continue;
    const siblings = childrenByParent.get(message.reply_to_id) ?? [];
    siblings.push(message);
    childrenByParent.set(message.reply_to_id, siblings);
  }

  const ordered: T[] = [];
  const visited = new Set<string>();

  const pushMessage = (message: T) => {
    if (visited.has(message.id)) return;
    visited.add(message.id);
    ordered.push(message);
    for (const child of childrenByParent.get(message.id) ?? []) {
      pushMessage(child);
    }
  };

  for (const message of baseSorted) {
    if (message.reply_to_id && byId.has(message.reply_to_id)) continue;
    pushMessage(message);
  }
  for (const message of baseSorted) {
    pushMessage(message);
  }

  return ordered;
}

function appendText(blocks: DemoContentBlock[], text: string): DemoContentBlock[] {
  const [firstBlock, ...rest] = blocks;
  if (!firstBlock || firstBlock.type !== 'text') {
    return [{ type: 'text', text }, ...blocks];
  }

  return [{ ...firstBlock, text: `${firstBlock.text}${text}` }, ...rest];
}

function isTaskCardMetadata(value: unknown): value is Omit<TaskCardBlock, 'type'> {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as { title?: unknown; tasks?: unknown };
  return typeof candidate.title === 'string' && Array.isArray(candidate.tasks);
}

function createTaskCard(metadata: Record<string, unknown> | undefined): TaskCardBlock {
  const fallback: Omit<TaskCardBlock, 'type'> = {
    title: 'Orchestrator 调度计划',
    tasks: [],
  };
  const value = isTaskCardMetadata(metadata) ? metadata : fallback;
  return {
    type: 'task_card',
    presentation: presentationFromMetadata(metadata),
    title: value.title,
    tasks: value.tasks.map((task) => ({
      id: String(task.id),
      agent_id: String(task.agent_id),
      planned_agent_id:
        typeof task.planned_agent_id === 'string' ? task.planned_agent_id : String(task.agent_id),
      current_agent_id: typeof task.current_agent_id === 'string' ? task.current_agent_id : null,
      final_agent_id: typeof task.final_agent_id === 'string' ? task.final_agent_id : null,
      title: String(task.title),
      status: task.status as TaskStatus,
    })),
  };
}

function createProcessBlock(
  metadata: Record<string, unknown> | undefined,
  agentId?: string,
): ProcessBlock {
  const steps = Array.isArray(metadata?.steps)
    ? metadata.steps
        .filter((step): step is Record<string, unknown> => Boolean(step && typeof step === 'object'))
        .map((step) => ({
          id: typeof step.id === 'string' ? step.id : undefined,
          label: String(step.label ?? '执行步骤'),
          kind: processStepKind(step.kind),
          status: processStepStatus(step.status),
          detail: typeof step.detail === 'string' ? step.detail : null,
          agent_id: typeof step.agent_id === 'string' ? step.agent_id : null,
        }))
    : [];
  return {
    type: 'process',
    agent_id: (metadata?.agent_id as string | undefined) ?? agentId ?? 'orchestrator',
    presentation: presentationFromMetadata(metadata),
    title: typeof metadata?.title === 'string' ? metadata.title : '执行过程',
    status: processStatus(metadata?.status),
    default_collapsed:
      typeof metadata?.default_collapsed === 'boolean' ? metadata.default_collapsed : false,
    steps,
    summary: typeof metadata?.summary === 'string' ? metadata.summary : null,
    metadata: (metadata?.metadata as Record<string, unknown>) ?? {},
  };
}

function createClarificationBlock(
  metadata: Record<string, unknown> | undefined,
  agentId?: string,
): ClarificationBlock {
  return {
    type: 'clarification',
    agent_id: (metadata?.agent_id as string | undefined) ?? agentId ?? 'orchestrator',
    presentation: presentationFromMetadata(metadata),
    mode: clarificationMode(metadata?.mode),
    title: typeof metadata?.title === 'string' ? metadata.title : '需求澄清',
    status: clarificationStatus(metadata?.status),
    current_question: clarificationQuestion(metadata?.current_question),
    questions: clarificationQuestions(metadata?.questions),
    summary: typeof metadata?.summary === 'string' ? metadata.summary : null,
    metadata: (metadata?.metadata as Record<string, unknown>) ?? {},
  };
}

function processStepFromValue(value: unknown): ProcessBlock['steps'][number] | null {
  if (!value || typeof value !== 'object') return null;
  const step = value as Record<string, unknown>;
  return {
    id: typeof step.id === 'string' ? step.id : undefined,
    label: String(step.label ?? '执行步骤'),
    kind: processStepKind(step.kind),
    status: processStepStatus(step.status),
    detail: typeof step.detail === 'string' ? step.detail : null,
    agent_id: typeof step.agent_id === 'string' ? step.agent_id : null,
  };
}

function applyProcessDelta(
  block: ProcessBlock,
  metadata: Record<string, unknown> | undefined,
): ProcessBlock {
  const rawDelta = metadata?.process_delta;
  if (!rawDelta || typeof rawDelta !== 'object') return block;
  const delta = rawDelta as Record<string, unknown>;
  if (delta.op === 'upsert_step') {
    const step = processStepFromValue(delta.step);
    if (!step) return block;
    const steps = [...block.steps];
    if (step.id) {
      const existingIndex = steps.findIndex((item) => item.id === step.id);
      if (existingIndex >= 0) {
        steps[existingIndex] = step;
        return { ...block, steps };
      }
    }
    return { ...block, steps: [...steps, step] };
  }
  if (delta.op === 'set_summary') {
    return {
      ...block,
      status: processStatus(delta.status),
      summary: typeof delta.summary === 'string' ? delta.summary : block.summary,
    };
  }
  return block;
}

type TaskCardTask = TaskCardBlock['tasks'][number];

function findTaskForAgentSwitch(
  tasks: TaskCardTask[],
  event: Extract<StreamEvent, { event: 'agent_switch' }>,
): TaskCardTask | null {
  const taskTitle = event.data.task?.trim();
  if (taskTitle) {
    return (
      tasks.find(
        (task) =>
          task.title === taskTitle && (task.status === 'pending' || task.status === 'running'),
      ) ?? null
    );
  }
  return (
    tasks.find((task) => task.status === 'pending' && task.agent_id === event.data.to_agent) ??
    null
  );
}

function setTaskCurrentAgent(task: TaskCardTask, agentId: string): TaskCardTask {
  if (task.agent_id === agentId && task.current_agent_id == null) {
    return { ...task, status: 'running' };
  }
  return {
    ...task,
    agent_id: agentId,
    planned_agent_id: task.planned_agent_id ?? task.agent_id,
    current_agent_id: agentId,
    final_agent_id: null,
    status: 'running',
  };
}

function setTaskFinalAgent(
  task: TaskCardTask,
  status: Extract<TaskStatus, 'done' | 'error'>,
): TaskCardTask {
  if (task.current_agent_id == null) {
    return { ...task, status };
  }
  const agentId = task.current_agent_id ?? task.agent_id;
  return {
    ...task,
    agent_id: agentId,
    current_agent_id: null,
    final_agent_id: agentId,
    status,
  };
}

function updateTaskStatuses(
  blocks: DemoContentBlock[],
  event: Extract<StreamEvent, { event: 'agent_switch' }>,
): DemoContentBlock[] {
  return blocks.map((block) => {
    if (block.type !== 'task_card') return block;
    const targetTask = findTaskForAgentSwitch(block.tasks, event);
    return {
      ...block,
      tasks: block.tasks.map((task) => {
        if (task === targetTask) {
          return setTaskCurrentAgent(task, event.data.to_agent);
        }
        if (task.status === 'running') {
          return setTaskFinalAgent(task, 'done');
        }
        return task;
      }),
    };
  });
}

function completeRunningTasks(blocks: DemoContentBlock[]): DemoContentBlock[] {
  return blocks.map((block) => {
    if (block.type !== 'task_card') return block;
    return {
      ...block,
      tasks: block.tasks.map((task) =>
        task.status === 'running' ? setTaskFinalAgent(task, 'done') : task,
      ),
    };
  });
}

function failRunningTasks(blocks: DemoContentBlock[]): DemoContentBlock[] {
  return blocks.map((block) => {
    if (block.type !== 'task_card') return block;
    return {
      ...block,
      tasks: block.tasks.map((task) =>
        task.status === 'running' ? setTaskFinalAgent(task, 'error') : task,
      ),
    };
  });
}

function interruptRunningBlocks(blocks: DemoContentBlock[]): DemoContentBlock[] {
  return blocks.map((block) => {
    if (block.type === 'task_card') {
      return {
        ...block,
        tasks: block.tasks.map((task) =>
          task.status === 'pending' || task.status === 'running'
            ? { ...task, status: 'interrupted' as const }
            : task,
        ),
      };
    }
    if (block.type === 'process') {
      return {
        ...block,
        status:
          block.status === 'running' || block.status === 'partial'
            ? ('interrupted' as const)
            : block.status,
        steps: block.steps.map((step) =>
          step.status === 'running' ? { ...step, status: 'interrupted' as const } : step,
        ),
      };
    }
    return block;
  });
}

function previewFromMessage(message: DemoMessage): string | null {
  if (message.status === 'queued') return '1 条消息已排队';
  if (message.status === 'interrupted') return '回复已打断';
  for (const block of message.content) {
    if (block.type === 'text' && block.text.trim()) {
      return block.text.trim();
    }
    if (block.type === 'code' && block.code.trim()) {
      return `Code: ${block.language || 'text'}`;
    }
    if (block.type === 'task_card') {
      return `${block.title}: ${block.tasks.length} tasks`;
    }
    if (block.type === 'agent_switch') {
      return `${block.to_agent}: ${block.task}`;
    }
    if (block.type === 'tool_call') {
      return `${block.tool_name}: ${block.status}`;
    }
    if (block.type === 'process') {
      return `${block.title}: ${block.status}`;
    }
    if (block.type === 'clarification') {
      return `${block.title}: ${block.status}`;
    }
    if (block.type === 'turn_control') {
      return `${block.title}: ${block.status}`;
    }
    if (block.type === 'file') {
      return block.path || block.filename;
    }
  }
  if (message.status === 'error') return 'Agent response failed';
  return null;
}

function applyToolCall(
  blocks: DemoContentBlock[],
  event: Extract<StreamEvent, { event: 'tool_call' }>,
): DemoContentBlock[] {
  return [
    ...blocks,
    {
      type: 'tool_call',
      agent_id: event.data.agent_id ?? null,
      presentation: presentationFromMetadata(event.data.metadata),
      call_id: event.data.call_id,
      tool_name: event.data.tool_name,
      arguments: event.data.tool_arguments,
      status: 'pending',
    },
  ];
}

function applyToolResult(
  blocks: DemoContentBlock[],
  event: Extract<StreamEvent, { event: 'tool_result' }>,
): DemoContentBlock[] {
  return blocks.map((block) => {
    if (block.type !== 'tool_call' || block.call_id !== event.data.call_id) return block;
    return {
      ...block,
      agent_id: block.agent_id ?? event.data.agent_id ?? null,
      status: event.data.tool_status,
      output_preview: event.data.tool_output,
      output_truncated: event.data.tool_output_truncated,
      error_code: event.data.error_code,
    };
  });
}

function applyDelta(blocks: DemoContentBlock[], event: StreamEvent): DemoContentBlock[] {
  if (event.event === 'block_start') {
    const next = [...blocks];
    if (event.data.block_type === 'task_card') {
      next[event.data.block_index] = createTaskCard(event.data.metadata);
    } else if (event.data.block_type === 'process') {
      next[event.data.block_index] = createProcessBlock(
        event.data.metadata,
        event.data.agent_id,
      );
    } else if (event.data.block_type === 'clarification') {
      next[event.data.block_index] = createClarificationBlock(
        event.data.metadata,
        event.data.agent_id,
      );
    } else if (event.data.block_type === 'code') {
      next[event.data.block_index] = {
        type: 'code',
        agent_id: event.data.agent_id ?? null,
        presentation: presentationFromMetadata(event.data.metadata),
        language: (event.data.metadata?.language as string) || 'text',
        code: '',
      };
    } else if (event.data.block_type === 'workflow') {
      next[event.data.block_index] = {
        type: 'workflow',
        agent_id: event.data.agent_id ?? null,
        presentation: presentationFromMetadata(event.data.metadata),
        last_run_id: (event.data.metadata?.last_run_id as string) || null,
        name: (event.data.metadata?.name as string) || null,
        path: (event.data.metadata?.path as string) || undefined,
        format: event.data.metadata?.format === 'json' ? 'json' : 'yaml',
        definition: {},
        raw_definition: '',
        nodes: [],
        edges: [],
        validation_status:
          event.data.metadata?.validation_status === 'passed' ||
          event.data.metadata?.validation_status === 'failed'
            ? event.data.metadata.validation_status
            : 'unknown',
        runtime_status:
          event.data.metadata?.runtime_status === 'ready' ||
          event.data.metadata?.runtime_status === 'invalid'
            ? event.data.metadata.runtime_status
            : 'not_supported',
        dry_run_status:
          event.data.metadata?.dry_run_status === 'passed' ||
          event.data.metadata?.dry_run_status === 'failed'
            ? event.data.metadata.dry_run_status
            : 'not_supported',
        health_status:
          event.data.metadata?.health_status === 'passed' ||
          event.data.metadata?.health_status === 'failed'
            ? event.data.metadata.health_status
            : 'unknown',
        validation_errors: [],
      };
    } else if (event.data.block_type === 'file') {
      next[event.data.block_index] = {
        type: 'file',
        agent_id: event.data.agent_id ?? null,
        presentation: presentationFromMetadata(event.data.metadata),
        path: (event.data.metadata?.path as string) || null,
        artifact_kind:
          (event.data.metadata?.artifact_kind as
            | 'document'
            | 'ppt'
            | 'image'
            | 'archive'
            | 'code'
            | 'workflow'
            | 'other') || 'other',
        filename: (event.data.metadata?.filename as string) || 'artifact',
        url: (event.data.metadata?.url as string) || '',
        size: (event.data.metadata?.size as number) || 0,
        mime_type: (event.data.metadata?.mime_type as string) || 'application/octet-stream',
        preview_text: (event.data.metadata?.preview_text as string) || undefined,
        preview_truncated: (event.data.metadata?.preview_truncated as boolean) || false,
        metadata: (event.data.metadata?.metadata as Record<string, unknown>) || {},
      };
    } else if (event.data.block_type === 'web_preview') {
      next[event.data.block_index] = {
        type: 'web_preview',
        agent_id: event.data.agent_id ?? null,
        presentation: presentationFromMetadata(event.data.metadata),
        url: (event.data.metadata?.url as string) || '',
        title: (event.data.metadata?.title as string) || undefined,
        description: (event.data.metadata?.description as string) || undefined,
      };
    } else if (event.data.block_type === 'deployment_status') {
      next[event.data.block_index] = {
        type: 'deployment_status',
        agent_id: event.data.agent_id ?? null,
        presentation: presentationFromMetadata(event.data.metadata),
        deployment_id: (event.data.metadata?.deployment_id as string) || '',
        kind:
          event.data.metadata?.kind === 'source_zip' || event.data.metadata?.kind === 'container'
            ? event.data.metadata.kind
            : 'static_site',
        status:
          event.data.metadata?.status === 'published' ||
          event.data.metadata?.status === 'failed' ||
          event.data.metadata?.status === 'publishing' ||
          event.data.metadata?.status === 'queued' ||
          event.data.metadata?.status === 'stopped' ||
          event.data.metadata?.status === 'not_supported'
            ? event.data.metadata.status
            : 'failed',
        title: (event.data.metadata?.title as string) || null,
        url: (event.data.metadata?.url as string) || null,
        download_url: (event.data.metadata?.download_url as string) || null,
        error: (event.data.metadata?.error as string) || null,
        logs_preview: (event.data.metadata?.logs_preview as string) || null,
      };
    } else {
      next[event.data.block_index] = {
        type: 'text',
        agent_id: event.data.agent_id ?? null,
        presentation: presentationFromMetadata(event.data.metadata),
        text: '',
      };
    }
    return next;
  }

  if (event.event === 'agent_switch') {
    const next = updateTaskStatuses(blocks, event);
    next.push({
      type: 'agent_switch',
      presentation: defaultExecutionPresentation('Agent 切换'),
      from_agent: event.data.from_agent,
      to_agent: event.data.to_agent,
      task: event.data.task ?? `${event.data.to_agent} 接手任务`,
    });
    return next;
  }

  if (event.event === 'tool_call') return applyToolCall(blocks, event);
  if (event.event === 'tool_result') return applyToolResult(blocks, event);

  if (event.event !== 'delta') return blocks;

  const next = [...blocks];
  const block = next[event.data.block_index];
  if (!block) return next;

  if (block.type === 'text' && event.data.text_delta) {
    next[event.data.block_index] = {
      ...block,
      agent_id: block.agent_id ?? event.data.agent_id ?? null,
      text: `${block.text}${event.data.text_delta}`,
    };
  }
  if (block.type === 'code' && event.data.code_delta) {
    next[event.data.block_index] = {
      ...block,
      agent_id: block.agent_id ?? event.data.agent_id ?? null,
      code: `${block.code}${event.data.code_delta}`,
    };
  }
  if (block.type === 'workflow' && (event.data.text_delta || event.data.code_delta)) {
    next[event.data.block_index] = {
      ...block,
      agent_id: block.agent_id ?? event.data.agent_id ?? null,
      raw_definition: `${block.raw_definition ?? ''}${event.data.text_delta ?? event.data.code_delta ?? ''}`,
    };
  }
  if (block.type === 'process') {
    next[event.data.block_index] = applyProcessDelta(block, event.data.metadata);
  }
  return next;
}

function processStatus(value: unknown): ProcessBlock['status'] {
  if (
    value === 'running' ||
    value === 'done' ||
    value === 'partial' ||
    value === 'error' ||
    value === 'interrupted'
  ) {
    return value;
  }
  return 'done';
}

function processStepStatus(value: unknown): ProcessBlock['steps'][number]['status'] {
  if (
    value === 'done' ||
    value === 'running' ||
    value === 'error' ||
    value === 'skipped' ||
    value === 'interrupted'
  ) {
    return value;
  }
  return 'done';
}

function processStepKind(value: unknown): ProcessBlock['steps'][number]['kind'] {
  const allowed = [
    'routing',
    'planning',
    'dispatch',
    'tool',
    'review',
    'evaluation',
    'workflow',
    'deployment',
    'artifact',
    'repair',
    'summary',
  ] as const;
  return typeof value === 'string' && allowed.includes(value as (typeof allowed)[number])
    ? (value as ProcessBlock['steps'][number]['kind'])
    : 'summary';
}

function clarificationMode(value: unknown): ClarificationBlock['mode'] {
  if (
    value === 'auto' ||
    value === 'requirement_alignment' ||
    value === 'grill_me' ||
    value === 'grill_with_docs' ||
    value === 'setup_matt_pocock_skills'
  ) {
    return value;
  }
  return 'auto';
}

function clarificationStatus(value: unknown): ClarificationBlock['status'] {
  if (value === 'waiting' || value === 'resolved' || value === 'cancelled') {
    return value;
  }
  return 'waiting';
}

function clarificationQuestion(value: unknown): ClarificationBlock['current_question'] {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;
  return {
    id: String(raw.id ?? 'question'),
    question: String(raw.question ?? ''),
    reason: typeof raw.reason === 'string' ? raw.reason : null,
    recommended_answer:
      typeof raw.recommended_answer === 'string' ? raw.recommended_answer : null,
    options: Array.isArray(raw.options)
      ? raw.options.filter((item): item is string => typeof item === 'string')
      : [],
    status:
      raw.status === 'answered' || raw.status === 'skipped' || raw.status === 'pending'
        ? raw.status
        : 'pending',
    answer: typeof raw.answer === 'string' ? raw.answer : null,
  };
}

function clarificationQuestions(value: unknown): ClarificationBlock['questions'] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => clarificationQuestion(item))
    .filter((item): item is ClarificationBlock['questions'][number] => Boolean(item));
}

function applyStreamEventToMessage(message: DemoMessage, event: StreamEvent): DemoMessage {
  if (message.status === 'done' && event.event === 'error') {
    return message;
  }
  if (event.event === 'start' || event.event === 'message_start') {
    if (message.status === 'done') return message;
    return { ...message, status: 'streaming' as const };
  }
  if (event.event === 'done' || event.event === 'message_done') {
    return {
      ...message,
      status: 'done' as const,
      content: completeRunningTasks(message.content),
    };
  }
  if (event.event === 'error' || event.event === 'message_error') {
    const errorMessage = event.data.error ?? event.data.error_code ?? 'unknown error';
    const nextContent =
      message.content.length > 0
        ? failRunningTasks(message.content)
        : appendText([], `调用未完成：${errorMessage}`);
    return {
      ...message,
      status: 'error' as const,
      content: nextContent,
    };
  }
  if (event.event === 'interrupted' || event.event === 'message_interrupted') {
    return {
      ...message,
      status: 'interrupted' as const,
      content:
        message.content.length > 0
          ? interruptRunningBlocks(message.content)
          : [{ type: 'text', text: '已打断本次回复，可以继续补充要求。' }],
    };
  }
  return {
    ...message,
    content: applyDelta(message.content, event),
  };
}

function applyTurnControlToConversations(
  messagesByConversation: Record<string, DemoMessage[]>,
  controlBlock: TurnControlBlock,
): Record<string, DemoMessage[]> {
  const controlId = controlBlock.control_id;
  if (!controlId) return messagesByConversation;
  let changed = false;
  const next = Object.fromEntries(
    Object.entries(messagesByConversation).map(([conversationId, messages]) => {
      const nextMessages = messages.map((message) => {
        let messageChanged = false;
        const content = message.content.map((block) => {
          if (
            block.type === 'turn_control' &&
            (block as TurnControlBlock).control_id === controlId
          ) {
            messageChanged = true;
            return controlBlock;
          }
          return block;
        });
        if (!messageChanged) return message;
        changed = true;
        return { ...message, content };
      });
      return [conversationId, nextMessages];
    }),
  );
  return changed ? next : messagesByConversation;
}

function streamEventMessageId(parentMessageId: string, event: StreamEvent): string {
  const data = event.data as { message_id?: unknown };
  return typeof data.message_id === 'string' && data.message_id ? data.message_id : parentMessageId;
}

function streamEventConversationId(event: StreamEvent): string | null {
  const data = event.data as { conversation_id?: unknown };
  return typeof data.conversation_id === 'string' && data.conversation_id
    ? data.conversation_id
    : null;
}

function streamEventAgentId(event: StreamEvent): string | null {
  const data = event.data as { agent_id?: unknown };
  return typeof data.agent_id === 'string' && data.agent_id ? data.agent_id : null;
}

function streamEventReplyToId(event: StreamEvent, parentMessage?: DemoMessage): string | null {
  const data = event.data as { reply_to_id?: unknown };
  if (typeof data.reply_to_id === 'string') return data.reply_to_id;
  return parentMessage?.reply_to_id ?? null;
}

function streamEventCreatedAt(event: StreamEvent): string {
  const data = event.data as { created_at?: unknown };
  return typeof data.created_at === 'string' && data.created_at
    ? data.created_at
    : new Date().toISOString();
}

function findMessageLocation(
  messagesByConversation: Record<string, DemoMessage[]>,
  messageId: string,
): { conversationId: string; message: DemoMessage } | null {
  for (const [conversationId, messages] of Object.entries(messagesByConversation)) {
    const message = messages.find((item) => item.id === messageId);
    if (message) return { conversationId, message };
  }
  return null;
}

function streamEventQueuedNext(event: StreamEvent): {
  userMessage: DemoMessage;
  agentMessage: DemoMessage;
  queueRemainingCount: number;
} | null {
  const data = event.data as {
    queued_next?: {
      user_message?: unknown;
      agent_message?: unknown;
      queue_remaining_count?: unknown;
    };
  };
  const payload = data.queued_next;
  if (!payload || typeof payload !== 'object') return null;
  const userMessage = payload.user_message;
  const agentMessage = payload.agent_message;
  if (!isMessageLike(userMessage) || !isMessageLike(agentMessage)) return null;
  return {
    userMessage: userMessage as DemoMessage,
    agentMessage: agentMessage as DemoMessage,
    queueRemainingCount:
      typeof payload.queue_remaining_count === 'number' ? payload.queue_remaining_count : 0,
  };
}

function isMessageLike(value: unknown): value is Message {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<Message>;
  return (
    typeof candidate.id === 'string' &&
    typeof candidate.conversation_id === 'string' &&
    typeof candidate.role === 'string' &&
    Array.isArray(candidate.content)
  );
}

function upsertMessages(current: DemoMessage[], messages: DemoMessage[]): DemoMessage[] {
  const byId = new Map(current.map((message) => [message.id, message]));
  for (const message of messages) {
    byId.set(message.id, message);
  }
  return sortMessagesForDisplay([...byId.values()]);
}

function ensureStreamTargetMessage(
  messagesByConversation: Record<string, DemoMessage[]>,
  conversationId: string,
  targetMessageId: string,
  event: StreamEvent,
  parentMessage?: DemoMessage,
): Record<string, DemoMessage[]> {
  const next = { ...messagesByConversation };
  const current = next[conversationId] ?? [];
  if (current.some((message) => message.id === targetMessageId)) {
    next[conversationId] = current;
    return next;
  }
  next[conversationId] = [
    ...current,
    {
      id: targetMessageId,
      conversation_id: conversationId,
      role: 'agent',
      agent_id: streamEventAgentId(event),
      reply_to_id: streamEventReplyToId(event, parentMessage),
      status: 'streaming',
      is_pinned: false,
      created_at: streamEventCreatedAt(event),
      content: [],
    },
  ];
  return next;
}

function updateConversationPreview(
  conversations: DemoConversation[],
  conversationId: string,
  touchedMessage?: DemoMessage | null,
): DemoConversation[] {
  return conversations.map((conversation) =>
    conversation.id === conversationId
      ? {
          ...conversation,
          last_message_at: new Date().toISOString(),
          last_message_preview:
            touchedMessage?.status === 'streaming'
              ? 'Agent 正在流式回复...'
              : touchedMessage
                ? (previewFromMessage(touchedMessage) ?? conversation.last_message_preview ?? null)
                : conversation.last_message_preview,
        }
      : conversation,
  );
}

export const useChatStore = create<ChatState>((set) => ({
  conversations: [],
  messagesByConversation: {},
  activeStreams: {},
  selectedConversationId: '',
  search: '',
  highlightedMessageId: null,
  setSelectedConversationId: (conversationId) => set({ selectedConversationId: conversationId }),
  setSearch: (search) => set({ search }),
  setHighlightedMessageId: (messageId) => set({ highlightedMessageId: messageId }),
  toggleMessagePin: (messageId) => {
    set((state) => ({
      messagesByConversation: Object.fromEntries(
        Object.entries(state.messagesByConversation).map(([conversationId, messages]) => [
          conversationId,
          messages.map((message) =>
            message.id === messageId ? { ...message, is_pinned: !message.is_pinned } : message,
          ),
        ]),
      ),
    }));
  },
  toggleConversationPin: (conversationId) => {
    set((state) => ({
      conversations: state.conversations.map((conversation) =>
        conversation.id === conversationId
          ? { ...conversation, is_pinned: !conversation.is_pinned }
          : conversation,
      ),
    }));
  },
  toggleConversationArchive: (conversationId) => {
    set((state) => {
      const target = state.conversations.find((conversation) => conversation.id === conversationId);
      const willArchive = !target?.is_archived;
      const nextVisible = state.conversations.find(
        (conversation) => conversation.id !== conversationId && !conversation.is_archived,
      );
      return {
        conversations: state.conversations.map((conversation) =>
          conversation.id === conversationId
            ? { ...conversation, is_archived: !conversation.is_archived }
            : conversation,
        ),
        selectedConversationId:
          willArchive && state.selectedConversationId === conversationId
            ? (nextVisible?.id ?? '')
            : state.selectedConversationId,
      };
    });
  },
  applyStreamEvent: (messageId, event) => {
    set((state) => {
      if (event.event === 'turn_control') {
        return {
          messagesByConversation: applyTurnControlToConversations(
            state.messagesByConversation,
            event.data.turn_control,
          ),
        };
      }
      const targetMessageId = streamEventMessageId(messageId, event);
      const isChildLifecycle =
        event.event === 'message_start' ||
        event.event === 'message_done' ||
        event.event === 'message_error' ||
        event.event === 'message_interrupted';
      const parentLocation = findMessageLocation(state.messagesByConversation, messageId);
      if (targetMessageId !== messageId || isChildLifecycle) {
        const conversationId =
          streamEventConversationId(event) ??
          parentLocation?.conversationId ??
          state.selectedConversationId;
        if (!conversationId) return {};
        const nextMessagesByConversation = ensureStreamTargetMessage(
          state.messagesByConversation,
          conversationId,
          targetMessageId,
          event,
          parentLocation?.message,
        );
        const updatedMessages = (nextMessagesByConversation[conversationId] ?? []).map(
          (message) => {
            if (message.id !== targetMessageId) return message;
            return applyStreamEventToMessage(message, event);
          },
        );
        nextMessagesByConversation[conversationId] = sortMessagesForDisplay(updatedMessages);
        const touchedMessage = nextMessagesByConversation[conversationId].find(
          (message) => message.id === targetMessageId,
        );
        return {
          messagesByConversation: nextMessagesByConversation,
          conversations: updateConversationPreview(
            state.conversations,
            conversationId,
            touchedMessage,
          ),
        };
      }

      let touchedConversationId: string | null = null;
      let touchedMessage: DemoMessage | null = null;
      const nextMessagesByConversation = Object.fromEntries(
        Object.entries(state.messagesByConversation).map(([conversationId, messages]) => {
          const nextMessages = messages.map((message) => {
            if (message.id !== messageId) return message;
            touchedConversationId = conversationId;
            const nextMessage = applyStreamEventToMessage(message, event);
            touchedMessage = nextMessage;
            return nextMessage;
          });
          return [conversationId, nextMessages];
        }),
      );

      const queuedNext = streamEventQueuedNext(event);
      let nextActiveStreams = state.activeStreams;
      if (queuedNext) {
        const queuedConversationId = queuedNext.agentMessage.conversation_id;
        nextMessagesByConversation[queuedConversationId] = upsertMessages(
          nextMessagesByConversation[queuedConversationId] ?? [],
          [queuedNext.userMessage, queuedNext.agentMessage],
        );
        touchedConversationId = queuedConversationId;
        touchedMessage = queuedNext.agentMessage;
        if (
          queuedNext.agentMessage.role === 'agent' &&
          queuedNext.agentMessage.agent_id &&
          (queuedNext.agentMessage.status === 'pending' ||
            queuedNext.agentMessage.status === 'streaming')
        ) {
          nextActiveStreams = {
            ...nextActiveStreams,
            [queuedNext.agentMessage.id]: {
              messageId: queuedNext.agentMessage.id,
              conversationId: queuedNext.agentMessage.conversation_id,
              agentId: queuedNext.agentMessage.agent_id,
              startedAt: new Date().toISOString(),
              interrupting: false,
            },
          };
        }
      }

      const nextConversations = touchedConversationId
        ? state.conversations.map((conversation) =>
            conversation.id === touchedConversationId
              ? {
                  ...conversation,
                  last_message_at: new Date().toISOString(),
                  last_message_preview:
                    touchedMessage?.status === 'streaming'
                      ? 'Agent 正在流式回复...'
                      : touchedMessage
                        ? (previewFromMessage(touchedMessage) ??
                          conversation.last_message_preview ??
                          null)
                        : conversation.last_message_preview,
                }
              : conversation,
          )
        : state.conversations;

      return {
        messagesByConversation: nextMessagesByConversation,
        conversations: nextConversations,
        activeStreams: nextActiveStreams,
      };
    });
  },
  startActiveStream: (message) => {
    set((state) => ({
      activeStreams: {
        ...state.activeStreams,
        [message.id]: {
          messageId: message.id,
          conversationId: message.conversation_id,
          agentId: message.agent_id ?? null,
          startedAt: new Date().toISOString(),
          interrupting: false,
        },
      },
    }));
  },
  setActiveStreamInterrupting: (messageId, interrupting) => {
    set((state) => {
      const stream = state.activeStreams[messageId];
      if (!stream) return {};
      return {
        activeStreams: {
          ...state.activeStreams,
          [messageId]: { ...stream, interrupting },
        },
      };
    });
  },
  finishActiveStream: (messageId) => {
    set((state) => {
      const activeStreams = { ...state.activeStreams };
      delete activeStreams[messageId];
      return { activeStreams };
    });
  },
  resetMessageForRetry: (messageId) => {
    set((state) => ({
      messagesByConversation: Object.fromEntries(
        Object.entries(state.messagesByConversation).map(([conversationId, messages]) => [
          conversationId,
          messages.map((message) =>
            message.id === messageId
              ? {
                  ...message,
                  status: 'streaming' as const,
                  content: [{ type: 'text', text: '' }],
                }
              : message,
          ),
        ]),
      ),
    }));
  },
  addConversation: (conversation) => {
    set((state) => ({
      conversations: [conversation as DemoConversation, ...state.conversations],
      messagesByConversation: {
        ...state.messagesByConversation,
        [conversation.id]: state.messagesByConversation[conversation.id] ?? [],
      },
      selectedConversationId: conversation.id,
    }));
  },
  hydrateConversations: (conversations) => {
    set((state) => {
      const remoteIds = new Set(conversations.map((c) => c.id));
      const selected = state.selectedConversationId;
      const nextSelected =
        selected && remoteIds.has(selected) ? selected : (conversations[0]?.id ?? '');
      return {
        conversations: conversations as DemoConversation[],
        selectedConversationId: nextSelected,
      };
    });
  },
  hydrateMessages: (conversationId, messages) => {
    set((state) => {
      const incoming = messages as DemoMessage[];
      const activeStreams = mergeHydratedActiveStreams(state.activeStreams, incoming);
      return {
        activeStreams,
        messagesByConversation: {
          ...state.messagesByConversation,
          [conversationId]: sortMessagesForDisplay(
            mergeHydratedMessages(
              state.messagesByConversation[conversationId] ?? [],
              incoming,
              activeStreams,
              conversationId,
            ),
          ),
        },
      };
    });
  },
  appendRemoteExchange: (conversationId, userMessage, agentMessage) => {
    set((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        [conversationId]: sortMessagesForDisplay([
          ...(state.messagesByConversation[conversationId] ?? []),
          userMessage as DemoMessage,
          agentMessage as DemoMessage,
        ]),
      },
      conversations: state.conversations.map((item) =>
        item.id === conversationId
          ? {
              ...item,
              last_message_at: userMessage.created_at,
              last_message_preview:
                (userMessage.content?.[0] as { text?: string } | undefined)?.text ??
                item.last_message_preview ??
                null,
            }
        : item,
      ),
    }));
  },
  appendQueuedMessage: (conversationId, queuedMessage) => {
    set((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        [conversationId]: upsertMessages(state.messagesByConversation[conversationId] ?? [], [
          queuedMessage as DemoMessage,
        ]),
      },
      conversations: state.conversations.map((item) =>
        item.id === conversationId
          ? {
              ...item,
              last_message_at: queuedMessage.created_at,
              last_message_preview: '1 条消息已排队',
            }
          : item,
      ),
    }));
  },
  updateConversationLocal: (conversation) => {
    set((state) => {
      const nextConversation = conversation as DemoConversation;
      const exists = state.conversations.some((item) => item.id === conversation.id);
      const conversations = exists
        ? state.conversations.map((item) => (item.id === conversation.id ? nextConversation : item))
        : [nextConversation, ...state.conversations];
      const nextVisible = conversations.find(
        (item) => item.id !== conversation.id && !item.is_archived,
      );

      return {
        conversations,
        selectedConversationId:
          conversation.is_archived && state.selectedConversationId === conversation.id
            ? (nextVisible?.id ?? '')
            : state.selectedConversationId,
      };
    });
  },
  updateMessageLocal: (message) => {
    set((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        [message.conversation_id]: upsertMessages(
          state.messagesByConversation[message.conversation_id] ?? [],
          [message as DemoMessage],
        ),
      },
      conversations: updateConversationPreview(
        state.conversations,
        message.conversation_id,
        message as DemoMessage,
      ),
    }));
  },
  replaceMessageLocal: (oldMessageId, message) => {
    set((state) => {
      const current = state.messagesByConversation[message.conversation_id] ?? [];
      const replaced = current.some((item) => item.id === oldMessageId);
      const next = replaced
        ? current.map((item) => (item.id === oldMessageId ? (message as DemoMessage) : item))
        : [...current, message as DemoMessage];
      return {
        messagesByConversation: {
          ...state.messagesByConversation,
          [message.conversation_id]: sortMessagesForDisplay(next),
        },
      };
    });
  },
  removeMessageLocal: (messageId) => {
    set((state) => {
      let touchedConversationId: string | null = null;
      const messagesByConversation = Object.fromEntries(
        Object.entries(state.messagesByConversation).map(([conversationId, messages]) => {
          const nextMessages = messages.filter((message) => message.id !== messageId);
          if (nextMessages.length !== messages.length) {
            touchedConversationId = conversationId;
          }
          return [conversationId, nextMessages];
        }),
      );
      return {
        messagesByConversation,
        conversations: touchedConversationId
          ? updateConversationPreview(
              state.conversations,
              touchedConversationId,
              messagesByConversation[touchedConversationId]?.at(-1) ?? null,
            )
          : state.conversations,
      };
    });
  },
  clearChat: () =>
    set({
      conversations: [],
      messagesByConversation: {},
      selectedConversationId: '',
      search: '',
      highlightedMessageId: null,
      activeStreams: {},
    }),
}));

function mergeHydratedMessages(
  current: DemoMessage[],
  incoming: DemoMessage[],
  activeStreams: ChatState['activeStreams'],
  conversationId: string,
): DemoMessage[] {
  const currentById = new Map(current.map((message) => [message.id, message]));
  const mergedById = new Map<string, DemoMessage>();
  const protectedLocalMessageIds = new Set<string>();

  for (const message of current) {
    const activeStream = activeStreams[message.id];
    if (activeStream?.conversationId !== conversationId) continue;
    if (message.status !== 'streaming') continue;

    protectedLocalMessageIds.add(message.id);
    if (message.reply_to_id && currentById.has(message.reply_to_id)) {
      protectedLocalMessageIds.add(message.reply_to_id);
    }
  }

  for (const message of incoming) {
    const currentMessage = currentById.get(message.id);
    const activeStream = activeStreams[message.id];
    if (
      activeStream?.conversationId === conversationId &&
      currentMessage?.status === 'streaming'
    ) {
      mergedById.set(message.id, currentMessage);
      continue;
    }
    if (
      activeStream?.conversationId === conversationId &&
      message.role === 'agent' &&
      (message.status === 'pending' || message.status === 'streaming')
    ) {
      mergedById.set(message.id, message);
      continue;
    }
    if (message.status === 'streaming') {
      mergedById.set(message.id, {
        ...message,
        status: 'error' as const,
        content:
          currentMessage?.content.length
            ? currentMessage.content
            : message.content.length > 0
            ? message.content
            : [{ type: 'text', text: '回复已中断，请重试这条消息。' }],
      });
      continue;
    }
    mergedById.set(message.id, message);
  }

  for (const message of current) {
    if (!protectedLocalMessageIds.has(message.id)) continue;
    if (mergedById.has(message.id)) continue;
    mergedById.set(message.id, message);
  }

  return sortMessagesForDisplay([...mergedById.values()]);
}

function mergeHydratedActiveStreams(
  current: ChatState['activeStreams'],
  messages: DemoMessage[],
): ChatState['activeStreams'] {
  const next = { ...current };
  for (const message of messages) {
    if (message.role !== 'agent') continue;
    if (
      message.status === 'done' ||
      message.status === 'error' ||
      message.status === 'interrupted'
    ) {
      delete next[message.id];
      continue;
    }
    if (
      (message.status === 'pending' || message.status === 'streaming') &&
      message.agent_id
    ) {
      next[message.id] = next[message.id] ?? {
        messageId: message.id,
        conversationId: message.conversation_id,
        agentId: message.agent_id,
        startedAt: new Date().toISOString(),
        interrupting: false,
      };
    }
  }
  return next;
}
