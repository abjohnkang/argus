import { useEffect, useRef } from 'react';
import { MessageBubble } from './MessageBubble';
import type { ChatMessage } from '../lib/types';

interface MessageListProps {
  messages: ChatMessage[];
  streaming: boolean;
}

/**
 * Scrollable conversation. The streaming assistant message region is announced
 * politely to assistive tech via aria-live (WCAG 2.1 AA — status updates
 * perceivable without sight).
 */
export function MessageList({ messages, streaming }: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Guard: scrollIntoView is absent in some environments (e.g. jsdom).
    endRef.current?.scrollIntoView?.({ block: 'end' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-text-muted">
        <p>Ask Argus anything. Your conversation never leaves this device.</p>
      </div>
    );
  }

  return (
    <div
      className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-6"
      aria-live="polite"
      aria-relevant="additions text"
    >
      {messages.map((message, index) => {
        const isLast = index === messages.length - 1;
        return (
          <MessageBubble
            key={index}
            message={message}
            streaming={streaming && isLast && message.role === 'assistant'}
          />
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
