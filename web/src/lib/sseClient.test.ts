import { describe, it, expect, vi } from 'vitest';
import { parseSSEFrame, streamChat, ChatRequestError } from './sseClient';
import type { SSEEvent } from './types';

const enc = new TextEncoder();

/**
 * Build a fake `fetch` that returns a 200 streaming Response whose body emits
 * the given byte chunks in order. This lets us drive the residual-buffer logic
 * with deliberately split frames.
 */
function streamingFetch(chunks: Uint8Array[], opts: { signal?: AbortSignal } = {}) {
  return vi.fn(async (_url: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const signal = init?.signal ?? opts.signal;
    const body = new ReadableStream<Uint8Array>({
      async start(controller) {
        for (const chunk of chunks) {
          if (signal?.aborted) break;
          controller.enqueue(chunk);
          // Yield to the event loop so an abort triggered between reads lands.
          await new Promise((r) => setTimeout(r, 0));
        }
        controller.close();
      },
    });
    return new Response(body, {
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
    });
  });
}

/** Build a fake fetch that returns a non-OK status with a JSON body. */
function statusFetch(status: number, jsonBody: unknown) {
  return vi.fn(
    async (): Promise<Response> =>
      new Response(JSON.stringify(jsonBody), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
  );
}

/**
 * Build a fake fetch whose 200 stream emits `goodChunks` then has its reader
 * throw a GENUINE read failure (a plain Error, NOT an AbortError and no
 * `signal.aborted`). This exercises the real-error rethrow branch in
 * streamChat — distinct from the silent user-abort path.
 */
function midStreamErrorFetch(goodChunks: Uint8Array[], error: Error) {
  return vi.fn(async (): Promise<Response> => {
    let index = 0;
    const body = new ReadableStream<Uint8Array>({
      async pull(controller) {
        if (index < goodChunks.length) {
          controller.enqueue(goodChunks[index]);
          index += 1;
          return;
        }
        // All good chunks delivered — now fail with a real read error.
        controller.error(error);
      },
    });
    return new Response(body, {
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
    });
  });
}

async function collect(gen: AsyncGenerator<SSEEvent>): Promise<SSEEvent[]> {
  const out: SSEEvent[] = [];
  for await (const ev of gen) out.push(ev);
  return out;
}

// Convenience: a token-bearing Ollama-native frame line.
const frame = (content: string, model = 'llama4:scout', done = false) =>
  `data: ${JSON.stringify({
    model,
    created_at: '2026-06-05T00:00:00Z',
    message: { role: 'assistant', content },
    done,
  })}\n\n`;

describe('parseSSEFrame (pure)', () => {
  it('extracts message.content from an Ollama-native frame', () => {
    const raw = JSON.stringify({
      model: 'llama4:scout',
      message: { role: 'assistant', content: 'Hel' },
      done: false,
    });
    expect(parseSSEFrame(`data: ${raw}`)).toEqual({
      type: 'token',
      content: 'Hel',
      model: 'llama4:scout',
    });
  });

  it('recognises the [DONE] sentinel', () => {
    expect(parseSSEFrame('data: [DONE]')).toEqual({ type: 'done' });
  });

  it('surfaces an in-band {"error"} frame', () => {
    expect(parseSSEFrame('data: {"error": "upstream stream broken"}')).toEqual({
      type: 'error',
      message: 'upstream stream broken',
    });
  });

  it('ignores blank lines and SSE comment/keepalive lines', () => {
    expect(parseSSEFrame('')).toBeNull();
    expect(parseSSEFrame('   ')).toBeNull();
    expect(parseSSEFrame(': keepalive')).toBeNull();
  });

  it('surfaces an error for a JSON payload that is not an object (e.g. a bare number)', () => {
    expect(parseSSEFrame('data: 42')).toEqual({
      type: 'error',
      message: 'unexpected stream frame',
    });
  });

  it('does NOT read OpenAI choices[].delta shape (regression guard)', () => {
    // The real Argus wire format is Ollama-native; a frame WITHOUT message.content
    // must not yield phantom token text.
    const openAiShape = JSON.stringify({
      choices: [{ delta: { content: 'should-be-ignored' } }],
    });
    const ev = parseSSEFrame(`data: ${openAiShape}`);
    // No message.content present -> empty token (no phantom text from delta).
    expect(ev).not.toEqual({ type: 'token', content: 'should-be-ignored', model: undefined });
  });
});

describe('streamChat (orchestration)', () => {
  const req = { messages: [{ role: 'user' as const, content: 'hi' }], stream: true };

  it('emits a single token then done for a one-frame stream', async () => {
    const fetchImpl = streamingFetch([enc.encode(frame('Hello') + 'data: [DONE]\n\n')]);
    const events = await collect(streamChat(req, { fetchImpl }));
    expect(events).toEqual([
      { type: 'token', content: 'Hello', model: 'llama4:scout' },
      { type: 'done' },
    ]);
  });

  it('accumulates content across multiple frames in order', async () => {
    const payload = frame('Hel') + frame('lo') + frame(' sea') + 'data: [DONE]\n\n';
    const fetchImpl = streamingFetch([enc.encode(payload)]);
    const events = await collect(streamChat(req, { fetchImpl }));
    const tokens = events.filter((e) => e.type === 'token').map((e) => (e as { content: string }).content);
    expect(tokens).toEqual(['Hel', 'lo', ' sea']);
    expect(events.at(-1)).toEqual({ type: 'done' });
  });

  it('reassembles a frame split across TWO reader chunks (chunk-boundary buffering)', async () => {
    // Split the SINGLE frame mid-JSON so the \n\n delimiter arrives in chunk 2.
    const full = frame('Hello world') + 'data: [DONE]\n\n';
    const bytes = enc.encode(full);
    const splitAt = Math.floor(bytes.length / 2);
    const chunkA = bytes.slice(0, splitAt);
    const chunkB = bytes.slice(splitAt);
    const fetchImpl = streamingFetch([chunkA, chunkB]);
    const events = await collect(streamChat(req, { fetchImpl }));
    expect(events).toEqual([
      { type: 'token', content: 'Hello world', model: 'llama4:scout' },
      { type: 'done' },
    ]);
  });

  it('reassembles when multiple frames are split at arbitrary byte boundaries', async () => {
    const full = frame('a') + frame('b') + frame('c') + 'data: [DONE]\n\n';
    const bytes = enc.encode(full);
    // Emit one byte at a time — the worst case for residual buffering.
    const chunks: Uint8Array[] = [];
    for (let i = 0; i < bytes.length; i++) chunks.push(bytes.slice(i, i + 1));
    const fetchImpl = streamingFetch(chunks);
    const events = await collect(streamChat(req, { fetchImpl }));
    const tokens = events.filter((e) => e.type === 'token').map((e) => (e as { content: string }).content);
    expect(tokens).toEqual(['a', 'b', 'c']);
    expect(events.at(-1)).toEqual({ type: 'done' });
  });

  it('terminates on [DONE] even if trailing bytes follow', async () => {
    const payload = frame('x') + 'data: [DONE]\n\n';
    const fetchImpl = streamingFetch([enc.encode(payload)]);
    const events = await collect(streamChat(req, { fetchImpl }));
    expect(events.filter((e) => e.type === 'done')).toHaveLength(1);
  });

  it('surfaces an in-band error frame mid-stream and stops', async () => {
    const payload =
      frame('partial ') + 'data: {"error": "upstream stream broken"}\n\n' + 'data: [DONE]\n\n';
    const fetchImpl = streamingFetch([enc.encode(payload)]);
    const events = await collect(streamChat(req, { fetchImpl }));
    expect(events[0]).toEqual({ type: 'token', content: 'partial ', model: 'llama4:scout' });
    expect(events[1]).toEqual({ type: 'error', message: 'upstream stream broken' });
    // No tokens are emitted after the error event.
    expect(events.some((e, i) => i > 1 && e.type === 'token')).toBe(false);
  });

  it('handles an empty stream (only [DONE]) with a single done event', async () => {
    const fetchImpl = streamingFetch([enc.encode('data: [DONE]\n\n')]);
    const events = await collect(streamChat(req, { fetchImpl }));
    expect(events).toEqual([{ type: 'done' }]);
  });

  it('ignores blank / keepalive lines interleaved with frames', async () => {
    const payload = ': keepalive\n\n' + frame('ok') + '\n\n' + 'data: [DONE]\n\n';
    const fetchImpl = streamingFetch([enc.encode(payload)]);
    const events = await collect(streamChat(req, { fetchImpl }));
    const tokens = events.filter((e) => e.type === 'token').map((e) => (e as { content: string }).content);
    expect(tokens).toEqual(['ok']);
  });

  it('throws a typed ChatRequestError on a pre-stream non-OK status (502)', async () => {
    const fetchImpl = statusFetch(502, {
      error: 'upstream model service unavailable',
      upstream_status: 503,
    });
    await expect(async () => {
      await collect(streamChat(req, { fetchImpl }));
    }).rejects.toBeInstanceOf(ChatRequestError);
  });

  it('on user-initiated abort: stops yielding, retains partial output, throws no error', async () => {
    const controller = new AbortController();
    // A long stream; we abort after the first token is consumed.
    const payload = frame('first') + frame('second') + frame('third') + 'data: [DONE]\n\n';
    // Emit each frame as its own chunk with an await tick so abort can land between.
    const frames = [frame('first'), frame('second'), frame('third'), 'data: [DONE]\n\n'];
    const fetchImpl = streamingFetch(frames.map((f) => enc.encode(f)));
    void payload;

    const received: SSEEvent[] = [];
    const gen = streamChat(req, { fetchImpl, signal: controller.signal });
    for await (const ev of gen) {
      received.push(ev);
      if (ev.type === 'token' && ev.content === 'first') {
        controller.abort();
      }
    }
    // Partial output retained: at least the first token survived.
    const tokens = received.filter((e) => e.type === 'token').map((e) => (e as { content: string }).content);
    expect(tokens).toContain('first');
    // No error surfaced for a user-initiated abort.
    expect(received.some((e) => e.type === 'error')).toBe(false);
    // We stopped early — not all three tokens were appended.
    expect(tokens).not.toContain('third');
  });

  it('does not throw when fetch itself rejects with an AbortError (pre-stream abort)', async () => {
    const controller = new AbortController();
    const fetchImpl = vi.fn(async () => {
      const err = new DOMException('aborted', 'AbortError');
      throw err;
    });
    controller.abort();
    const events = await collect(streamChat(req, { fetchImpl, signal: controller.signal }));
    // Pre-stream abort yields nothing and surfaces no error.
    expect(events).toEqual([]);
  });

  it('yields a single done event when a 200 response has no body stream', async () => {
    // A 200 with a null body (no readable stream) is finalised cleanly.
    const fetchImpl = vi.fn(async (): Promise<Response> => new Response(null, { status: 200 }));
    const events = await collect(streamChat(req, { fetchImpl }));
    expect(events).toEqual([{ type: 'done' }]);
  });

  it('rethrows a genuine PRE-stream fetch rejection (no signal) as a real error', async () => {
    // fetch() itself rejects with a non-Abort error (e.g. connection refused)
    // and there is no AbortController — streamChat must rethrow, not swallow.
    const connError = new TypeError('Failed to fetch');
    const fetchImpl = vi.fn(async () => {
      throw connError;
    });
    await expect(collect(streamChat(req, { fetchImpl }))).rejects.toBe(connError);
  });

  it('throws ChatRequestError with a generic message when the 502 body is non-JSON', async () => {
    // Error response whose body is not valid JSON — the parse falls back to the
    // generic status-based message rather than crashing (REQ-UI-005).
    const fetchImpl = vi.fn(
      async (): Promise<Response> =>
        new Response('<html>502 Bad Gateway</html>', {
          status: 502,
          headers: { 'content-type': 'text/html' },
        }),
    );
    await expect(collect(streamChat(req, { fetchImpl }))).rejects.toMatchObject({
      name: 'ChatRequestError',
      status: 502,
      message: 'request failed with status 502',
    });
  });

  it('rethrows a genuine mid-stream read error (not an abort) and retains partial tokens', async () => {
    // No AbortController / signal here — this is a real network/read failure,
    // so streamChat must rethrow rather than finalise silently.
    const readError = new Error('network read failed');
    const fetchImpl = midStreamErrorFetch(
      [enc.encode(frame('partial ')), enc.encode(frame('answer '))],
      readError,
    );

    const received: SSEEvent[] = [];
    let thrown: unknown;
    try {
      for await (const ev of streamChat(req, { fetchImpl })) {
        received.push(ev);
      }
    } catch (err) {
      thrown = err;
    }

    // The real read error is surfaced (rethrown), distinct from a silent abort.
    expect(thrown).toBe(readError);
    // Tokens emitted before the failure are preserved for the caller.
    const tokens = received
      .filter((e) => e.type === 'token')
      .map((e) => (e as { content: string }).content);
    expect(tokens).toEqual(['partial ', 'answer ']);
    // No error EVENT was emitted — a real read failure propagates as a thrown
    // exception, not as an in-band { type: 'error' } event.
    expect(received.some((e) => e.type === 'error')).toBe(false);
  });
});
