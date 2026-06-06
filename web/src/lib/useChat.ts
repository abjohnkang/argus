import { useCallback, useRef, useState } from 'react';
import { streamChat, ChatRequestError } from './sseClient';
import type { ChatMessage } from './types';

export type ChatPhase = 'idle' | 'streaming';

export interface UseChat {
  messages: ChatMessage[];
  phase: ChatPhase;
  error: string | null;
  modelName: string | null;
  /** Send a user message and stream the assistant reply. */
  send: (text: string) => void;
  /** Abort the in-flight stream, retaining partial output (REQ-UI-004). */
  stop: () => void;
}

export interface UseChatOptions {
  /** Injectable fetch for tests; defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

/**
 * Owns the single in-memory conversation and the streaming lifecycle.
 *
 * No persistence: the messages live only in component state, so a reload
 * starts fresh (Exclusions — no persistence).
 */
export function useChat(options: UseChatOptions = {}): UseChat {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [phase, setPhase] = useState<ChatPhase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [modelName, setModelName] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    controllerRef.current?.abort();
  }, []);

  const send = useCallback(
    (text: string) => {
      const content = text.trim();
      // Empty / whitespace-only submissions are ignored (Edge case 3).
      if (content === '' || phase === 'streaming') return;

      setError(null);
      const userMessage: ChatMessage = { role: 'user', content };
      // Snapshot the history for the request body (state update is async).
      const history = [...messages, userMessage];
      setMessages([...history, { role: 'assistant', content: '' }]);
      setPhase('streaming');

      const controller = new AbortController();
      controllerRef.current = controller;

      // Mutate the last (assistant) message's content as tokens arrive.
      const appendToken = (token: string) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === 'assistant') {
            next[next.length - 1] = { ...last, content: last.content + token };
          }
          return next;
        });
      };

      void (async () => {
        try {
          const stream = streamChat(
            { messages: history, stream: true },
            { signal: controller.signal, fetchImpl: options.fetchImpl },
          );
          for await (const event of stream) {
            if (event.type === 'token') {
              if (event.model) setModelName(event.model);
              if (event.content) appendToken(event.content);
            } else if (event.type === 'error') {
              // Mid-stream in-band error: retain partial output, surface error.
              setError(event.message);
              break;
            } else if (event.type === 'done') {
              break;
            }
          }
        } catch (err) {
          // Pre-stream failure (e.g. 502) or a real network drop. A
          // user-initiated abort never reaches here — streamChat returns
          // silently on abort. The composer clears on any submit dispatch;
          // the user's message remains visible in the chat list and can be
          // resent, so no input is lost. Partial output already rendered
          // stays in place (REQ-UI-005).
          if (err instanceof ChatRequestError) {
            setError(err.message);
          } else {
            setError('The connection was interrupted. Please try again.');
          }
        } finally {
          // Only clear the controller if it is still the current one (guards
          // against a race where a new send replaced it).
          if (controllerRef.current === controller) controllerRef.current = null;
          setPhase('idle');
        }
      })();
    },
    [messages, phase, options.fetchImpl],
  );

  return { messages, phase, error, modelName, send, stop };
}
