import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { LockKeyhole, Share2 } from 'lucide-react';
import { getPublicConversationShare, type PublicSharedMessage } from '@/lib/adapters/shares';

export function SharePage() {
  const { token = '' } = useParams();
  const query = useQuery({
    queryKey: ['conversation-share', token],
    queryFn: () => getPublicConversationShare(token),
    enabled: Boolean(token),
    retry: false,
  });

  if (query.isLoading) {
    return <ShareShell>正在加载分享内容...</ShareShell>;
  }
  if (query.error || !query.data) {
    return (
      <ShareShell>
        <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-rose-700">
          分享链接不存在、已过期或已被撤销。
        </div>
      </ShareShell>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 px-4 py-8 text-slate-950 dark:bg-slate-950 dark:text-slate-100">
      <main className="mx-auto max-w-4xl space-y-4">
        <header className="rounded-md border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand">
            <Share2 className="h-4 w-4" />
            AgentHub 只读分享
          </div>
          <h1 className="mt-3 text-2xl font-semibold">{query.data.title}</h1>
          <p className="mt-2 text-sm text-slate-500">
            这是一个只读快照。你不能在这里发送消息、调用 Agent 或修改产物。
          </p>
        </header>
        <section className="space-y-3">
          {query.data.messages.map((message) => (
            <SharedMessageCard key={message.id} message={message} />
          ))}
        </section>
      </main>
    </div>
  );
}

function ShareShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4 text-slate-950 dark:bg-slate-950 dark:text-slate-100">
      <div className="w-full max-w-md rounded-md border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <LockKeyhole className="h-4 w-4 text-brand" />
          AgentHub 分享
        </div>
        {children}
        <Link to="/login" className="mt-4 inline-flex text-sm font-medium text-brand hover:underline">
          返回 AgentHub
        </Link>
      </div>
    </div>
  );
}

function SharedMessageCard({ message }: { message: PublicSharedMessage }) {
  const isUser = message.role === 'user';
  return (
    <article
      className={
        isUser
          ? 'ml-auto max-w-2xl rounded-md bg-brand px-4 py-3 text-white'
          : 'max-w-3xl rounded-md border border-slate-200 bg-white px-4 py-3 shadow-sm dark:border-slate-800 dark:bg-slate-900'
      }
    >
      <div className="mb-2 text-xs font-medium opacity-75">
        {isUser ? '用户' : message.agent_id || 'Agent'}
      </div>
      <div className="space-y-2">{message.content.map((block, index) => renderSafeBlock(block, index))}</div>
    </article>
  );
}

function renderSafeBlock(block: Record<string, unknown>, index: number) {
  const type = String(block.type || 'unknown');
  if (type === 'text') {
    return (
      <p key={index} className="whitespace-pre-wrap text-sm leading-6">
        {String(block.text || '')}
      </p>
    );
  }
  if (type === 'code') {
    return (
      <pre key={index} className="overflow-x-auto rounded-md bg-slate-950 p-3 text-xs text-slate-100">
        <code>{String(block.code || '')}</code>
      </pre>
    );
  }
  if (type === 'task_card') {
    return (
      <div key={index} className="rounded-md border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-900">
        {String(block.title || '任务计划')}
      </div>
    );
  }
  if (type === 'file' || type === 'attachment') {
    return (
      <div key={index} className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm">
        {String(block.filename || '共享文件')}
      </div>
    );
  }
  return (
    <div key={index} className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
      {type}
    </div>
  );
}
