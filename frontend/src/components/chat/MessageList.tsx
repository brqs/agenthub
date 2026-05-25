import { useEffect, useRef } from 'react';
import { MessageBubble } from './MessageBubble';
import type { DemoMessage } from '@/lib/mockData';

export function MessageList({ messages }: { messages: DemoMessage[] }) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 scrollbar-thin">
      <div className="mx-auto flex max-w-5xl flex-col gap-5">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}

