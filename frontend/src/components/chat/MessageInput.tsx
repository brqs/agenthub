import {
  AlertCircle,
  AtSign,
  FileText,
  Image as ImageIcon,
  Loader2,
  MessageCircleQuestion,
  MoreHorizontal,
  Paperclip,
  RotateCcw,
  Route,
  Send,
  Slash,
  Square,
  X,
  Zap,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { AgentMentionPicker } from './AgentMentionPicker';
import { extractApiError } from '@/lib/api';
import { uploadFile } from '@/lib/adapters/uploads';
import type { DemoConversation } from '@/lib/mockData';
import type { Agent, AttachmentPreview, UploadOut } from '@/lib/types';

export interface MentionInsertRequest {
  agentId: string;
  requestId: number;
}

const slashCommands = [
  {
    value: '/grill-me',
    label: '/grill-me',
    description: '开始需求追问，先锁定关键规格',
  },
  {
    value: '/grill-with-docs',
    label: '/grill-with-docs',
    description: '结合 Workspace 文档澄清术语',
  },
  {
    value: '/setup-matt-pocock-skills',
    label: '/setup-matt-pocock-skills',
    description: '初始化本会话 Workspace 协作文档',
  },
];

type UploadStatus = 'queued' | 'uploading' | 'processing' | 'ready' | 'failed';

interface LocalUploadItem {
  localId: string;
  uploadId?: string;
  file: File;
  filename: string;
  contentType: string;
  sizeBytes: number;
  status: UploadStatus;
  progress: number;
  preview?: AttachmentPreview | null;
  errorMessage?: string;
}

const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;
const MAX_ATTACHMENTS_PER_MESSAGE = 10;

export function MessageInput({
  conversation,
  onSend,
  onQueue,
  isSending = false,
  isQueueing = false,
  isOffline = false,
  isStreaming = false,
  isInterrupting = false,
  onInterrupt,
  onGuidance,
  onSideChat,
  onStopAndRun,
  agents = [],
  mentionInsertRequest = null,
}: {
  conversation: DemoConversation;
  onSend: (text: string, attachmentIds?: string[]) => void | Promise<void>;
  onQueue?: (text: string, attachmentIds?: string[]) => void | Promise<void>;
  isSending?: boolean;
  isQueueing?: boolean;
  isOffline?: boolean;
  isStreaming?: boolean;
  isInterrupting?: boolean;
  onInterrupt?: () => void | Promise<void>;
  onGuidance?: (text: string) => void | Promise<void>;
  onSideChat?: (text: string) => void | Promise<void>;
  onStopAndRun?: (text: string) => void | Promise<void>;
  agents?: Agent[];
  mentionInsertRequest?: MentionInsertRequest | null;
}) {
  const [text, setText] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [uploadItems, setUploadItems] = useState<LocalUploadItem[]>([]);
  const [controlMenuOpen, setControlMenuOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const uploadControllers = useRef<Map<string, AbortController>>(new Map());
  const handledMentionRequestId = useRef<number | null>(null);
  const mentionQuery = useMemo(() => {
    if (conversation.mode !== 'group') return null;
    const match = text.match(/@([\w-]*)$/);
    return match?.[1] ?? null;
  }, [conversation.mode, text]);
  const slashMatches = useMemo(() => {
    const trimmed = text.trimStart();
    if (!trimmed.startsWith('/')) return [];
    const query = trimmed.slice(1).toLowerCase();
    return slashCommands.filter((command) =>
      command.value.slice(1).toLowerCase().startsWith(query),
    );
  }, [text]);
  const availableAgents = agents.filter((agent) => conversation.agent_ids.includes(agent.id));
  const isUnavailable = isSending || isQueueing || isOffline;
  const hasText = Boolean(text.trim());
  const readyAttachmentIds = uploadItems
    .filter((item) => item.status === 'ready' && item.uploadId)
    .map((item) => item.uploadId as string);
  const hasAttachments = uploadItems.length > 0;
  const hasReadyAttachment = readyAttachmentIds.length > 0;
  const hasBlockingAttachment = uploadItems.some((item) => item.status !== 'ready');
  const canSubmitMessage = hasText || hasReadyAttachment;

  async function submit() {
    const value = text.trim();
    if ((!value && !hasReadyAttachment) || isUnavailable) return;
    if (hasBlockingAttachment) {
      setSubmitError('请等待附件上传完成，或先移除/重试失败附件。');
      return;
    }
    setSubmitError(null);
    try {
      if (isStreaming) {
        if (!onQueue) return;
        if (readyAttachmentIds.length) {
          await onQueue(value, readyAttachmentIds);
        } else {
          await onQueue(value);
        }
      } else {
        if (readyAttachmentIds.length) {
          await onSend(value, readyAttachmentIds);
        } else {
          await onSend(value);
        }
      }
      setText('');
      setUploadItems([]);
      setControlMenuOpen(false);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : String(error));
    }
  }

  async function interrupt() {
    if (!isStreaming || isInterrupting || !onInterrupt) return;
    setSubmitError(null);
    try {
      await onInterrupt();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : String(error));
    }
  }

  async function submitControl(action: 'guidance' | 'side_chat' | 'stop_and_run') {
    const value = text.trim();
    if (!value || isUnavailable) return;
    const handler =
      action === 'guidance' ? onGuidance : action === 'side_chat' ? onSideChat : onStopAndRun;
    if (!handler) return;
    setSubmitError(null);
    try {
      await handler(value);
      setText('');
      setControlMenuOpen(false);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : String(error));
    }
  }

  useEffect(() => {
    if (!mentionInsertRequest || conversation.mode !== 'group') return;
    if (handledMentionRequestId.current === mentionInsertRequest.requestId) return;
    handledMentionRequestId.current = mentionInsertRequest.requestId;

    const mention = `@${mentionInsertRequest.agentId}`;
    const textarea = textareaRef.current;
    const selectionStart = textarea?.selectionStart ?? text.length;
    const selectionEnd = textarea?.selectionEnd ?? selectionStart;
    const prefix = selectionStart > 0 && !/\s/.test(text[selectionStart - 1] ?? '') ? ' ' : '';
    const suffix =
      selectionEnd < text.length && !/\s/.test(text[selectionEnd] ?? '') ? ' ' : ' ';
    const insertedText = `${prefix}${mention}${suffix}`;
    const nextText = `${text.slice(0, selectionStart)}${insertedText}${text.slice(selectionEnd)}`;
    const nextCaret = selectionStart + insertedText.length;

    setText(nextText);
    window.requestAnimationFrame(() => {
      textarea?.focus();
      textarea?.setSelectionRange(nextCaret, nextCaret);
    });
  }, [conversation.mode, mentionInsertRequest, text]);

  useEffect(() => {
    function handleFillMessageInput(event: Event) {
      const detail = (event as CustomEvent<{ text?: unknown }>).detail;
      if (typeof detail?.text !== 'string' || !detail.text.trim()) return;
      const nextText = detail.text;
      setText(nextText);
      setSubmitError(null);
      window.requestAnimationFrame(() => {
        textareaRef.current?.focus();
        const nextCaret = nextText.length;
        textareaRef.current?.setSelectionRange(nextCaret, nextCaret);
      });
    }

    window.addEventListener('agenthub:fill-message-input', handleFillMessageInput);
    return () => {
      window.removeEventListener('agenthub:fill-message-input', handleFillMessageInput);
    };
  }, []);

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  }

  function handlePaste(event: React.ClipboardEvent<HTMLTextAreaElement>) {
    const files = Array.from(event.clipboardData.files).filter((file) =>
      file.type.startsWith('image/'),
    );
    if (!files.length) return;
    void addFiles(files);
  }

  function pickAgent(agent: Agent) {
    setText((current) => current.replace(/@[\w-]*$/, `@${agent.id} `));
  }

  function pickSlashCommand(command: (typeof slashCommands)[number]) {
    setText(`${command.value} `);
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function addFiles(files: File[]) {
    if (isOffline) {
      setSubmitError('当前离线，恢复网络后再上传附件。');
      return;
    }
    const availableSlots = MAX_ATTACHMENTS_PER_MESSAGE - uploadItems.length;
    if (availableSlots <= 0) {
      setSubmitError(`每条消息最多添加 ${MAX_ATTACHMENTS_PER_MESSAGE} 个附件。`);
      return;
    }
    const acceptedFiles = files.slice(0, availableSlots);
    if (acceptedFiles.length < files.length) {
      setSubmitError(`每条消息最多添加 ${MAX_ATTACHMENTS_PER_MESSAGE} 个附件，已忽略多余文件。`);
    }
    const nextItems = acceptedFiles.map(createLocalUploadItem);
    setUploadItems((current) => [...current, ...nextItems]);
    await Promise.all(nextItems.map((item) => uploadLocalItem(item)));
  }

  async function uploadLocalItem(item: LocalUploadItem) {
    if (item.sizeBytes > MAX_UPLOAD_BYTES) {
      setUploadItems((current) =>
        current.map((entry) =>
          entry.localId === item.localId
            ? { ...entry, status: 'failed', errorMessage: '文件超过 100 MB 限制。' }
            : entry,
        ),
      );
      return;
    }

    const controller = new AbortController();
    uploadControllers.current.set(item.localId, controller);
    setUploadItems((current) =>
      current.map((entry) =>
        entry.localId === item.localId ? { ...entry, status: 'uploading', progress: 1 } : entry,
      ),
    );

    try {
      const upload = await uploadFile({
        file: item.file,
        filename: item.filename,
        purpose: 'message_attachment',
        conversationId: conversation.id,
        clientPlatform: 'web',
        signal: controller.signal,
        onProgress: (progress) => {
          setUploadItems((current) =>
            current.map((entry) =>
              entry.localId === item.localId ? { ...entry, progress } : entry,
            ),
          );
        },
      });
      setUploadItems((current) =>
        current.map((entry) =>
          entry.localId === item.localId ? localItemFromUpload(entry, upload) : entry,
        ),
      );
    } catch (error) {
      if (controller.signal.aborted) return;
      setUploadItems((current) =>
        current.map((entry) =>
          entry.localId === item.localId
            ? { ...entry, status: 'failed', errorMessage: extractApiError(error) }
            : entry,
        ),
      );
    } finally {
      uploadControllers.current.delete(item.localId);
    }
  }

  function removeUpload(localId: string) {
    uploadControllers.current.get(localId)?.abort();
    uploadControllers.current.delete(localId);
    setUploadItems((current) => current.filter((item) => item.localId !== localId));
  }

  function retryUpload(localId: string) {
    const item = uploadItems.find((entry) => entry.localId === localId);
    if (!item) return;
    void uploadLocalItem({ ...item, status: 'queued', progress: 0, errorMessage: undefined });
  }

  function handleDrop(event: React.DragEvent<HTMLElement>) {
    event.preventDefault();
    const files = Array.from(event.dataTransfer.files);
    if (files.length) void addFiles(files);
  }

  return (
    <footer
      className="min-w-0 max-w-full shrink-0 overflow-hidden border-t border-slate-200 bg-slate-100 px-3 pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-2 dark:border-slate-800 dark:bg-slate-950 sm:px-5 sm:py-3 max-[800px]:py-2 [@media(max-height:800px)]:py-2"
      onDragOver={(event) => event.preventDefault()}
      onDrop={handleDrop}
    >
      {conversation.mode === 'group' && (
        <div className="mb-2 flex items-center gap-2 text-xs text-slate-500 max-[800px]:hidden [@media(max-height:800px)]:hidden">
          <AtSign className="h-3.5 w-3.5" />
          输入 @ 可指定 Agent，默认由 Orchestrator 协调
        </div>
      )}
      {mentionQuery !== null && (
        <AgentMentionPicker agents={availableAgents} query={mentionQuery} onPick={pickAgent} />
      )}
      {slashMatches.length > 0 && (
        <div className="mb-2 overflow-hidden rounded-md border border-slate-200 bg-white shadow-lg dark:border-slate-800 dark:bg-slate-900">
          {slashMatches.map((command) => (
            <button
              key={command.value}
              type="button"
              onClick={() => pickSlashCommand(command)}
              className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <Slash className="h-4 w-4 shrink-0 text-brand" />
              <span className="min-w-0">
                <span className="block font-medium text-slate-900 dark:text-slate-100">
                  {command.label}
                </span>
                <span className="block truncate text-xs text-slate-500 dark:text-slate-400">
                  {command.description}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
      {isOffline && (
        <p className="mb-2 text-xs font-medium text-amber-700 dark:text-amber-300">
          当前离线，恢复网络后可继续发送
        </p>
      )}
      {submitError && (
        <p className="mobile-text-safe mb-2 text-xs font-medium text-red-600 dark:text-red-400">
          {submitError}
        </p>
      )}
      {hasAttachments && (
        <div className="mb-2 flex max-w-full gap-2 overflow-x-auto pb-1 scrollbar-thin">
          {uploadItems.map((item) => (
            <UploadChip
              key={item.localId}
              item={item}
              onRetry={() => retryUpload(item.localId)}
              onRemove={() => removeUpload(item.localId)}
            />
          ))}
        </div>
      )}
      <div className="flex min-w-0 max-w-full items-end gap-2 rounded-md border border-slate-300 bg-white p-2.5 focus-within:border-brand dark:border-slate-800 dark:bg-slate-900 sm:gap-3 [@media(max-height:800px)]:p-2">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            event.target.value = '';
            if (files.length) void addFiles(files);
          }}
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isOffline || uploadItems.length >= MAX_ATTACHMENTS_PER_MESSAGE}
          className="shrink-0 rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-40 dark:hover:bg-slate-800 dark:hover:text-white"
          title="添加附件"
          aria-label="添加附件"
        >
          <Paperclip className="h-4 w-4" />
        </button>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            if (submitError) setSubmitError(null);
          }}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          rows={1}
          disabled={isUnavailable}
          placeholder={isOffline ? '当前离线，恢复网络后可继续发送' : `发消息到 ${conversation.title}`}
          className="mobile-text-safe max-h-28 min-h-9 min-w-0 flex-1 resize-none bg-transparent py-2 text-base text-slate-950 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed disabled:opacity-60 dark:text-slate-100 dark:placeholder:text-slate-600 sm:text-sm [@media(max-height:800px)]:min-h-8 [@media(max-height:800px)]:py-1.5"
        />
        {isStreaming && hasText && (onGuidance || onSideChat || onStopAndRun) && (
          <div className="relative shrink-0">
            <button
              type="button"
              onClick={() => setControlMenuOpen((open) => !open)}
              disabled={isUnavailable}
              className="flex h-10 w-10 items-center justify-center rounded-md border border-slate-300 text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
              title="更多运行中操作"
              aria-label="More active turn actions"
            >
              <MoreHorizontal className="h-4 w-4" />
            </button>
            {controlMenuOpen && (
              <div className="absolute bottom-12 right-0 z-30 w-56 overflow-hidden rounded-md border border-slate-200 bg-white p-1 text-sm shadow-xl dark:border-slate-800 dark:bg-slate-900">
                {onGuidance && (
                  <button
                    type="button"
                    onClick={() => void submitControl('guidance')}
                    aria-label="Guide current reply"
                    className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    <Route className="h-4 w-4 text-brand" />
                    引导当前回复
                  </button>
                )}
                {onSideChat && (
                  <button
                    type="button"
                    onClick={() => void submitControl('side_chat')}
                    aria-label="Ask side question"
                    className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    <MessageCircleQuestion className="h-4 w-4 text-brand" />
                    旁路询问
                  </button>
                )}
                {onStopAndRun && (
                  <button
                    type="button"
                    onClick={() => void submitControl('stop_and_run')}
                    aria-label="Stop and run draft"
                    className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    <Zap className="h-4 w-4 text-brand" />
                    停止并立即执行
                  </button>
                )}
              </div>
            )}
          </div>
        )}
        {isStreaming && canSubmitMessage && (
          <button
            type="button"
            onClick={() => void interrupt()}
            disabled={isOffline || isInterrupting || !onInterrupt}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-slate-300 text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
            title={isInterrupting ? '正在停止' : '停止回复'}
            aria-label={isInterrupting ? '正在停止' : '停止回复'}
          >
            <Square className="h-4 w-4 fill-current" />
          </button>
        )}
        <button
          type="button"
          onClick={() => void (isStreaming && !canSubmitMessage ? interrupt() : submit())}
          disabled={
            isStreaming && !canSubmitMessage
              ? isOffline || isInterrupting || !onInterrupt
              : !canSubmitMessage || isUnavailable || hasBlockingAttachment || (isStreaming && !onQueue)
          }
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-brand text-white transition hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-40"
          title={isStreaming ? (canSubmitMessage ? '发送到队列' : '停止回复') : '发送'}
          aria-label={isStreaming ? (canSubmitMessage ? '发送到队列' : '停止回复') : '发送'}
        >
          {isStreaming && !canSubmitMessage ? (
            <Square className="h-4 w-4 fill-current" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </button>
      </div>
    </footer>
  );
}

function createLocalUploadItem(file: File): LocalUploadItem {
  return {
    localId: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    file,
    filename: file.name || 'clipboard-image.png',
    contentType: file.type || 'application/octet-stream',
    sizeBytes: file.size,
    status: 'queued',
    progress: 0,
  };
}

function localItemFromUpload(item: LocalUploadItem, upload: UploadOut): LocalUploadItem {
  return {
    ...item,
    uploadId: upload.id,
    filename: upload.filename,
    contentType: upload.content_type,
    sizeBytes: upload.size_bytes,
    status:
      upload.status === 'ready' ? 'ready' : upload.status === 'processing' ? 'processing' : 'failed',
    progress: 100,
    preview: upload.preview,
    errorMessage: upload.error_message ?? undefined,
  };
}

function UploadChip({
  item,
  onRetry,
  onRemove,
}: {
  item: LocalUploadItem;
  onRetry: () => void;
  onRemove: () => void;
}) {
  const Icon = item.contentType.startsWith('image/') ? ImageIcon : FileText;
  const failed = item.status === 'failed';
  const busy =
    item.status === 'queued' || item.status === 'uploading' || item.status === 'processing';

  return (
    <div className="mobile-text-safe flex min-h-11 min-w-52 max-w-72 shrink-0 items-center gap-2 rounded-md border border-slate-300 bg-white px-2.5 py-2 text-xs shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <Icon className="h-4 w-4 shrink-0 text-brand" />
      <div className="min-w-0 flex-1">
        <div
          className="truncate font-medium text-slate-800 dark:text-slate-100"
          title={item.filename}
        >
          {item.filename}
        </div>
        <div className="mt-0.5 flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
          {busy && <Loader2 className="h-3 w-3 animate-spin" />}
          {failed && <AlertCircle className="h-3 w-3 text-rose-500" />}
          <span className="truncate">
            {failed ? item.errorMessage ?? '上传失败' : item.status === 'ready' ? '已就绪' : `上传中 ${item.progress}%`}
          </span>
        </div>
      </div>
      {failed && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
          aria-label={`重试 ${item.filename}`}
        >
          <RotateCcw className="h-3.5 w-3.5" />
        </button>
      )}
      <button
        type="button"
        onClick={onRemove}
        className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
        aria-label={`移除 ${item.filename}`}
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
