import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchHealth, waitUntilReady } from './health';

function healthResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('fetchHealth', () => {
  it('maps 200 {"status":"ready"} to "ready"', async () => {
    const fetchImpl = vi.fn(async () => healthResponse(200, { status: 'ready' }));
    await expect(fetchHealth({ fetchImpl })).resolves.toBe('ready');
  });

  it('maps 503 {"status":"loading"} to "loading"', async () => {
    const fetchImpl = vi.fn(async () => healthResponse(503, { status: 'loading' }));
    await expect(fetchHealth({ fetchImpl })).resolves.toBe('loading');
  });

  it('treats a network error as "loading" (never throws, keeps the UI polling)', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError('Failed to fetch');
    });
    await expect(fetchHealth({ fetchImpl })).resolves.toBe('loading');
  });

  it('treats an unexpected status as "loading"', async () => {
    const fetchImpl = vi.fn(async () => healthResponse(500, {}));
    await expect(fetchHealth({ fetchImpl })).resolves.toBe('loading');
  });

  it('requests the same-origin relative /health path', async () => {
    const fetchImpl = vi.fn(async () => healthResponse(200, { status: 'ready' }));
    await fetchHealth({ fetchImpl });
    expect(fetchImpl).toHaveBeenCalledWith('/health', expect.any(Object));
  });
});

describe('waitUntilReady (503 -> 200 transition)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('polls while loading and resolves once ready is observed', async () => {
    const sequence = ['loading', 'loading', 'ready'];
    let call = 0;
    const fetchImpl = vi.fn(async () => {
      const status = sequence[Math.min(call, sequence.length - 1)];
      call += 1;
      return status === 'ready'
        ? healthResponse(200, { status: 'ready' })
        : healthResponse(503, { status: 'loading' });
    });

    const onLoading = vi.fn();
    const promise = waitUntilReady({ fetchImpl, intervalMs: 1000, onLoading });

    // Drain the polling loop deterministically under fake timers.
    await vi.runAllTimersAsync();
    await expect(promise).resolves.toBeUndefined();

    // Three polls total (loading, loading, ready); onLoading fired for the two
    // loading observations.
    expect(fetchImpl).toHaveBeenCalledTimes(3);
    expect(onLoading).toHaveBeenCalledTimes(2);
  });

  it('does not poll again once ready on the first observation', async () => {
    const fetchImpl = vi.fn(async () => healthResponse(200, { status: 'ready' }));
    const promise = waitUntilReady({ fetchImpl, intervalMs: 1000 });
    await vi.runAllTimersAsync();
    await promise;
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
