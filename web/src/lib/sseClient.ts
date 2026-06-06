import type { ChatCompletionRequest, SSEEvent } from './types';

/** The chat endpoint, relative so the app stays same-origin (REQ-UI-001). */
const CHAT_ENDPOINT = '/v1/chat/completions';

/** SSE frames are delimited by a blank line. */
const FRAME_DELIMITER = '\n\n';

/**
 * Raised when POST /v1/chat/completions fails BEFORE the stream begins — a
 * non-OK HTTP status (e.g. 502 when the upstream model service is
 * unavailable). Distinct from a mid-stream in-band error frame, which is
 * surfaced as an `{ type: 'error' }` event instead. The caller surfaces this
 * as a human-readable error while preserving the user's typed input
 * (REQ-UI-005).
 */
export class ChatRequestError extends Error {
  readonly status: number;
  readonly upstreamStatus?: number | null;

  constructor(status: number, message: string, upstreamStatus?: number | null) {
    super(message);
    this.name = 'ChatRequestError';
    this.status = status;
    this.upstreamStatus = upstreamStatus;
  }
}

// @MX:ANCHOR: parseSSEFrame is the single boundary where the Ollama-native SSE
// wire format is decoded. Token text is read from `message.content` (NOT the
// OpenAI `choices[].delta.content` shape), the `[DONE]` sentinel is recognised,
// and an in-band `{"error": "..."}` frame is surfaced as a failure. Every
// streaming feature in the UI depends on this contract.
// @MX:REASON: The wire format is produced by the pass-through at
// api/inference.py:199, which deliberately does not reshape Ollama's NDJSON.
// Pinning the contract in one pure function means a backend SSE-shape change is
// a single-file edit, and high fan_in (streamChat + every test) flows through here.
/**
 * Parse a single raw SSE line (the text between two `\n\n` delimiters).
 *
 * @param raw - one SSE frame's text, e.g. `data: {"message":{"content":"Hi"}}`.
 * @returns the typed event, or `null` for blank lines and SSE comment/keepalive
 *          lines (`:` prefix) that carry no payload.
 */
export function parseSSEFrame(raw: string): SSEEvent | null {
  const line = raw.trim();
  if (line === '') return null;
  // SSE comment / keepalive line — ignore.
  if (line.startsWith(':')) return null;
  // Only `data:` lines carry our payload; ignore any other SSE field.
  if (!line.startsWith('data:')) return null;

  const payload = line.slice('data:'.length).trim();
  if (payload === '') return null;
  if (payload === '[DONE]') return { type: 'done' };

  let frame: unknown;
  try {
    frame = JSON.parse(payload);
  } catch {
    // A malformed payload is treated as a stream failure rather than crashing.
    return { type: 'error', message: 'malformed stream frame' };
  }

  if (frame && typeof frame === 'object') {
    const obj = frame as Record<string, unknown>;
    // In-band error frame takes precedence (api/inference.py:202).
    if (typeof obj.error === 'string') {
      return { type: 'error', message: obj.error };
    }
    const message = obj.message as Record<string, unknown> | undefined;
    const content = message && typeof message.content === 'string' ? message.content : '';
    const model = typeof obj.model === 'string' ? obj.model : undefined;
    return { type: 'token', content, model };
  }
  return { type: 'error', message: 'unexpected stream frame' };
}

/** Options for {@link streamChat}. `fetchImpl` is injectable for testing. */
export interface StreamChatOptions {
  signal?: AbortSignal;
  fetchImpl?: typeof fetch;
}

/**
 * POST a chat request and yield typed SSE events as they arrive.
 *
 * Consumes `response.body` via a reader, decodes bytes with TextDecoder,
 * buffers across chunk boundaries, splits complete `\n\n`-delimited frames,
 * and delegates frame decoding to {@link parseSSEFrame}.
 *
 * Termination:
 *  - yields `{ type: 'done' }` and returns on the `[DONE]` sentinel;
 *  - yields `{ type: 'error' }` and returns on an in-band error frame;
 *  - returns silently on a user-initiated abort (partial output is retained by
 *    the consumer; no error is surfaced);
 *  - throws {@link ChatRequestError} on a pre-stream non-OK HTTP status.
 */
export async function* streamChat(
  request: ChatCompletionRequest,
  options: StreamChatOptions = {},
): AsyncGenerator<SSEEvent> {
  const doFetch = options.fetchImpl ?? fetch;
  const signal = options.signal;

  let response: Response;
  try {
    response = await doFetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(request),
      signal,
    });
  } catch (err) {
    // @MX:WARN: Abort/stop branch — a user-initiated abort can reject `fetch`
    // itself (pre-stream) or interrupt a read (mid-stream). We MUST distinguish
    // an intentional abort (return silently, partial output retained) from a
    // genuine network failure (surface it), or the Stop button would flash a
    // spurious error banner.
    // @MX:REASON: REQ-UI-004 requires a user stop to NOT surface as an error
    // (acceptance Scenario 2). `signal.aborted` / DOMException 'AbortError' is
    // the only reliable discriminator between the two cases.
    if (isAbort(err, signal)) return;
    throw err;
  }

  if (!response.ok) {
    let upstreamStatus: number | null | undefined;
    let detail = `request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as Record<string, unknown>;
      if (typeof body.error === 'string') detail = body.error;
      if (typeof body.upstream_status === 'number' || body.upstream_status === null) {
        upstreamStatus = body.upstream_status as number | null;
      }
    } catch {
      // Non-JSON error body — keep the generic status message.
    }
    throw new ChatRequestError(response.status, detail, upstreamStatus);
  }

  const body = response.body;
  if (!body) {
    // No stream body at all — treat as a clean (empty) termination.
    yield { type: 'done' };
    return;
  }

  const reader = body.getReader();
  const decoder = new TextDecoder();

  // @MX:WARN: Chunk-boundary residual buffer. TCP read boundaries do not align
  // with SSE frame boundaries — a single read may deliver half a frame or
  // several frames at once. `buffer` carries the incomplete tail forward; we
  // only ever consume complete `\n\n`-terminated frames. Dropping or
  // mis-slicing this residual is the most likely source of silent token
  // truncation.
  // @MX:REASON: research.md §1.4 [RISK] names this as the highest-risk parsing
  // bug. The carry-forward contract is: split on `\n\n`, the LAST element is
  // always the unterminated remainder and must be retained, never emitted.
  let buffer = '';

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let delimiterIndex: number;
      while ((delimiterIndex = buffer.indexOf(FRAME_DELIMITER)) !== -1) {
        const rawFrame = buffer.slice(0, delimiterIndex);
        buffer = buffer.slice(delimiterIndex + FRAME_DELIMITER.length);

        const event = parseSSEFrame(rawFrame);
        if (!event) continue;
        if (event.type === 'done' || event.type === 'error') {
          yield event;
          await cancelQuietly(reader);
          return;
        }
        yield event;
      }
    }

    // Flush any trailing residual that was not delimiter-terminated.
    const tail = parseSSEFrame(buffer);
    if (tail) yield tail;
  } catch (err) {
    // @MX:WARN: same abort discriminator as the pre-stream branch above — an
    // abort landing between reads rejects `reader.read()`. A user stop returns
    // silently; a real read error propagates.
    // @MX:REASON: REQ-UI-004 / REQ-UI-005 split — silent finalise on abort,
    // surface real failures.
    if (isAbort(err, signal)) return;
    throw err;
  } finally {
    await cancelQuietly(reader);
  }
}

/** True when an error or signal indicates a user-initiated abort. */
function isAbort(err: unknown, signal?: AbortSignal): boolean {
  if (signal?.aborted) return true;
  return err instanceof DOMException && err.name === 'AbortError';
}

/** Cancel a reader, swallowing the (expected) errors from an already-aborted stream. */
async function cancelQuietly(reader: ReadableStreamDefaultReader<Uint8Array>): Promise<void> {
  try {
    await reader.cancel();
  } catch {
    // Already closed / aborted — nothing to clean up.
  }
}
