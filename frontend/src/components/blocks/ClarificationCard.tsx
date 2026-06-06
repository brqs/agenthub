import { CheckCircle2, CircleHelp, FileText, Settings2 } from 'lucide-react';
import type { ClarificationBlock as ClarificationBlockData } from '@/lib/types';

const modeLabels: Record<ClarificationBlockData['mode'], string> = {
  auto: '自动澄清',
  grill_me: '/grill-me',
  grill_with_docs: '/grill-with-docs',
  setup_matt_pocock_skills: '/setup-matt-pocock-skills',
};

const statusLabels: Record<ClarificationBlockData['status'], string> = {
  waiting: '等待补充',
  resolved: '已确认',
  cancelled: '已取消',
};

export function ClarificationCard({ block }: { block: ClarificationBlockData }) {
  const question = block.current_question;
  const answered = block.questions.filter((item) => item.status !== 'pending');
  const waiting = block.status === 'waiting';

  return (
    <section className="mobile-text-safe overflow-hidden rounded-md border border-indigo-200 bg-indigo-50/70 text-slate-900 shadow-sm dark:border-indigo-500/40 dark:bg-indigo-950/30 dark:text-slate-100">
      <header className="flex min-w-0 items-center justify-between gap-3 border-b border-indigo-200/70 px-4 py-3 dark:border-indigo-500/30">
        <div className="flex min-w-0 items-center gap-2">
          <ModeIcon mode={block.mode} />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{block.title}</div>
            <div className="text-xs text-indigo-700 dark:text-indigo-300">
              {modeLabels[block.mode]}
            </div>
          </div>
        </div>
        <span
          className={[
            'shrink-0 rounded-md border px-2 py-1 text-xs font-medium',
            waiting
              ? 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-500/50 dark:bg-amber-950/30 dark:text-amber-200'
              : 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-500/50 dark:bg-emerald-950/30 dark:text-emerald-200',
          ].join(' ')}
        >
          {statusLabels[block.status]}
        </span>
      </header>

      <div className="space-y-3 px-4 py-4">
        {waiting && (
          <p className="text-xs leading-5 text-slate-600 dark:text-slate-300">
            点击推荐答案或选项只会填入输入框；请确认内容后手动发送。
          </p>
        )}
        {question && (
          <div className="space-y-3">
            <div>
              <p className="text-sm font-semibold leading-6">{question.question}</p>
              {question.reason && (
                <p className="mt-1 text-xs leading-5 text-slate-600 dark:text-slate-300">
                  {question.reason}
                </p>
              )}
            </div>

            {question.recommended_answer && (
              <button
                type="button"
                onClick={() => fillMessageInput(question.recommended_answer ?? '')}
                className="w-full rounded-md border border-indigo-200 bg-white px-3 py-2 text-left text-sm leading-6 text-slate-800 transition hover:border-indigo-400 hover:bg-indigo-50 dark:border-indigo-500/40 dark:bg-slate-950/40 dark:text-slate-100 dark:hover:bg-indigo-950/50"
              >
                <span className="block text-xs font-medium uppercase tracking-wide text-indigo-600 dark:text-indigo-300">
                  推荐答案
                </span>
                {question.recommended_answer}
              </button>
            )}

            {waiting && question.options && question.options.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {question.options.map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => fillMessageInput(option)}
                    className="rounded-md border border-indigo-200 bg-white px-2.5 py-1.5 text-xs font-medium text-indigo-800 transition hover:border-indigo-400 hover:bg-indigo-50 dark:border-indigo-500/40 dark:bg-slate-950/40 dark:text-indigo-200 dark:hover:bg-indigo-950/50"
                  >
                    {option}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {answered.length > 0 && (
          <div className="space-y-2 border-t border-indigo-200/70 pt-3 dark:border-indigo-500/30">
            {answered.map((item) => (
              <div key={item.id} className="text-xs leading-5 text-slate-600 dark:text-slate-300">
                <span className="font-medium text-slate-800 dark:text-slate-100">
                  {item.question}
                </span>
                {item.answer ? `：${item.answer}` : null}
              </div>
            ))}
          </div>
        )}

        {block.summary && (
          <p className="rounded-md bg-white/70 px-3 py-2 text-sm leading-6 text-slate-700 dark:bg-slate-950/40 dark:text-slate-200">
            {block.summary}
          </p>
        )}
      </div>
    </section>
  );
}

function ModeIcon({ mode }: { mode: ClarificationBlockData['mode'] }) {
  const className = "h-4 w-4 text-indigo-600 dark:text-indigo-300";
  if (mode === 'setup_matt_pocock_skills') return <Settings2 className={className} />;
  if (mode === 'grill_with_docs') return <FileText className={className} />;
  if (mode === 'auto') return <CircleHelp className={className} />;
  return <CheckCircle2 className={className} />;
}

function fillMessageInput(text: string) {
  if (!text.trim()) return;
  window.dispatchEvent(
    new CustomEvent('agenthub:fill-message-input', {
      detail: { text },
    }),
  );
}
