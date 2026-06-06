import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { ChatMessage } from '../lib/types';

interface MessageBubbleProps {
  message: ChatMessage;
  /** True while this (assistant) message is still streaming. */
  streaming?: boolean;
}

/**
 * Renders one message. Assistant messages render as markdown with fenced code
 * blocks highlighted via the locally bundled highlight.js theme (REQ-UI-002).
 * User messages render as plain text (they are user input — never parsed as
 * markdown, avoiding any injection surface).
 */
export function MessageBubble({ message, streaming }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  return (
    <div
      className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
      data-role={message.role}
    >
      <div
        className={[
          'max-w-[80%] rounded-2xl px-4 py-3 text-[0.95rem]',
          isUser
            ? 'bg-accent text-accent-fg'
            : 'bg-surface text-text border border-border',
        ].join(' ')}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap break-words m-0">{message.content}</p>
        ) : (
          <div className="prose">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
              {message.content}
            </ReactMarkdown>
            {streaming && message.content === '' && (
              <span className="text-text-muted" aria-hidden="true">
                …
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
