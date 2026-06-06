import type { HealthStatus } from './types';

/** Same-origin relative path so the app works behind the api origin (REQ-UI-001). */
const HEALTH_ENDPOINT = '/health';

/** Default poll cadence while the model is loading (research.md §2 suggests ~2s). */
const DEFAULT_INTERVAL_MS = 2000;

export interface FetchHealthOptions {
  fetchImpl?: typeof fetch;
  signal?: AbortSignal;
}

/**
 * Read GET /health once and reduce it to a {@link HealthStatus}.
 *
 * `200 {"status":"ready"}` -> `"ready"`. Anything else — `503`, an unexpected
 * status, or a transport error — maps to `"loading"`. This never throws: a
 * not-ready backend is a legitimate long-lived state, not an error
 * (REQ-UI-003), so the caller can keep polling indefinitely.
 */
export async function fetchHealth(options: FetchHealthOptions = {}): Promise<HealthStatus> {
  const doFetch = options.fetchImpl ?? fetch;
  try {
    const response = await doFetch(HEALTH_ENDPOINT, { signal: options.signal });
    if (response.status === 200) {
      try {
        const body = (await response.json()) as { status?: string };
        if (body.status === 'ready') return 'ready';
      } catch {
        // Body unreadable — fall through to loading.
      }
    }
    return 'loading';
  } catch {
    // Transport error (api not up yet, etc.) — keep polling.
    return 'loading';
  }
}

export interface WaitUntilReadyOptions extends FetchHealthOptions {
  intervalMs?: number;
  /** Called for each observed `loading` poll (drives the UI's loading state). */
  onLoading?: () => void;
}

/**
 * Poll GET /health until it reports `ready`, then resolve. There is no give-up
 * timeout: a first-run model pull can legitimately take a very long time
 * (research.md §2), so `loading` never converts to an error.
 *
 * Resolves immediately (after one poll) when the very first observation is
 * `ready`. Rejects only if the provided `signal` is aborted.
 */
export async function waitUntilReady(options: WaitUntilReadyOptions = {}): Promise<void> {
  const intervalMs = options.intervalMs ?? DEFAULT_INTERVAL_MS;
  for (;;) {
    if (options.signal?.aborted) throw new DOMException('aborted', 'AbortError');
    const status = await fetchHealth(options);
    if (status === 'ready') return;
    options.onLoading?.();
    await delay(intervalMs, options.signal);
  }
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    if (signal) {
      signal.addEventListener(
        'abort',
        () => {
          clearTimeout(timer);
          reject(new DOMException('aborted', 'AbortError'));
        },
        { once: true },
      );
    }
  });
}
