import { useEffect, useState } from 'react';
import { MessageList } from './MessageList';
import { Composer } from './Composer';
import { LoadingState } from './LoadingState';
import { ModelBadge } from './ModelBadge';
import { useChat } from '../lib/useChat';
import { waitUntilReady } from '../lib/health';
import type { HealthStatus } from '../lib/types';

interface ChatViewProps {
  /** Injectable fetch for tests; defaults to global fetch in production. */
  fetchImpl?: typeof fetch;
  /** Skip readiness polling and treat the backend as ready (test convenience). */
  initialHealth?: HealthStatus;
}

/**
 * Top-level chat experience: readiness gating + the single conversation.
 *
 * WHILE health is `loading`, the composer is disabled and the loading banner
 * shows (REQ-UI-003). Once `ready`, the composer enables and stays enabled.
 */
export function ChatView({ fetchImpl, initialHealth = 'loading' }: ChatViewProps) {
  const [health, setHealth] = useState<HealthStatus>(initialHealth);
  const { messages, phase, error, modelName, send, stop } = useChat({ fetchImpl });

  useEffect(() => {
    if (initialHealth === 'ready') return;
    const controller = new AbortController();
    waitUntilReady({
      fetchImpl,
      signal: controller.signal,
      onLoading: () => setHealth('loading'),
    })
      .then(() => setHealth('ready'))
      .catch(() => {
        /* aborted on unmount — ignore */
      });
    return () => controller.abort();
  }, [fetchImpl, initialHealth]);

  const streaming = phase === 'streaming';
  const composerDisabled = health !== 'ready' || streaming;

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <h1 className="text-sm font-semibold tracking-wide">Argus</h1>
        <ModelBadge modelName={modelName} />
      </header>

      {health === 'loading' && <LoadingState />}

      <MessageList messages={messages} streaming={streaming} />

      {error && (
        <div
          role="alert"
          className="mx-4 mb-2 rounded-lg border border-danger/50 bg-danger/10 px-4 py-2 text-sm text-danger"
        >
          {error}
        </div>
      )}

      <Composer
        disabled={composerDisabled}
        streaming={streaming}
        onSend={send}
        onStop={stop}
      />
    </div>
  );
}
