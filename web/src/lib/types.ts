// SPEC-UI-001 shared types.

/** A chat message in the single in-memory conversation. */
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

/** Request body for POST /v1/chat/completions (matches api/main.py ChatCompletionRequest). */
export interface ChatCompletionRequest {
  messages: ChatMessage[];
  model?: string;
  stream: boolean;
}

/**
 * A typed event emitted by the SSE stream parser.
 *
 * - `token`: assistant token text extracted from a frame's `message.content`.
 *   `model` carries `frame.model` when present (source for the model badge).
 * - `error`: an in-band `{"error": "..."}` SSE frame surfaced as a stream failure.
 * - `done`: the `data: [DONE]` sentinel — clean end of stream.
 */
export type SSEEvent =
  | { type: 'token'; content: string; model?: string }
  | { type: 'error'; message: string }
  | { type: 'done' };

/** Readiness states derived from GET /health. */
export type HealthStatus = 'loading' | 'ready';
