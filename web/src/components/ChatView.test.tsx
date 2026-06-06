import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatView } from './ChatView';

const enc = new TextEncoder();

const frame = (content: string, model = 'llama4:scout') =>
  `data: ${JSON.stringify({ model, message: { role: 'assistant', content }, done: false })}\n\n`;

/**
 * Build a fetch double routing /health and /v1/chat/completions. The chat
 * stream emits `chunks` in order with an await tick between each so streaming
 * is observable token-by-token and an abort can land mid-stream.
 */
function makeFetch(opts: {
  health?: 'ready' | 'loading';
  chatChunks?: string[];
  chatStatus?: number;
  chatErrorBody?: unknown;
  onAbort?: () => void;
}) {
  const health = opts.health ?? 'ready';
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    if (url === '/health') {
      return health === 'ready'
        ? new Response(JSON.stringify({ status: 'ready' }), { status: 200 })
        : new Response(JSON.stringify({ status: 'loading' }), { status: 503 });
    }
    if (url === '/v1/chat/completions') {
      if (opts.chatStatus && opts.chatStatus !== 200) {
        return new Response(JSON.stringify(opts.chatErrorBody ?? { error: 'fail' }), {
          status: opts.chatStatus,
        });
      }
      const signal = init?.signal;
      const chunks = opts.chatChunks ?? [];
      const body = new ReadableStream<Uint8Array>({
        async start(controller) {
          for (const chunk of chunks) {
            if (signal?.aborted) {
              opts.onAbort?.();
              break;
            }
            controller.enqueue(enc.encode(chunk));
            await new Promise((r) => setTimeout(r, 5));
          }
          controller.close();
        },
      });
      return new Response(body, { status: 200, headers: { 'content-type': 'text/event-stream' } });
    }
    throw new Error(`unexpected fetch to ${url}`);
  });
}

describe('ChatView — streaming happy path (Scenario 1, 4)', () => {
  it('renders the user message immediately and streams the assistant reply as markdown', async () => {
    const user = userEvent.setup();
    const fetchImpl = makeFetch({
      health: 'ready',
      chatChunks: [
        frame('Here is code:\n\n```python\n'),
        frame("print('hi')\n```\n"),
        frame('- a list item'),
        'data: [DONE]\n\n',
      ],
    });

    render(<ChatView fetchImpl={fetchImpl} initialHealth="ready" />);

    const input = screen.getByLabelText('Message Argus');
    await user.type(input, 'show me code');
    await user.click(screen.getByLabelText('Send message'));

    // User message appears immediately.
    expect(screen.getByText('show me code')).toBeInTheDocument();
    // Composer cleared on dispatch.
    expect(input).toHaveValue('');

    // Assistant content streams in and renders as markdown. highlight.js splits
    // code tokens across <span>s, so assert on the code block's textContent
    // rather than a single text node.
    await waitFor(() => {
      const codeBlock = document.querySelector('pre code');
      expect(codeBlock?.textContent).toContain("print('hi')");
    });
    await waitFor(() => {
      expect(screen.getByText('a list item')).toBeInTheDocument();
    });

    // Fenced code rendered as a <pre><code> block.
    expect(document.querySelector('pre code')).not.toBeNull();

    // Model badge picked up frame.model.
    expect(screen.getByText('llama4:scout')).toBeInTheDocument();

    // Composer returns to ready (Send shown, Stop gone) after [DONE].
    await waitFor(() => {
      expect(screen.getByLabelText('Send message')).toBeInTheDocument();
    });
  });
});

describe('ChatView — Stop generation (Scenario 2)', () => {
  it('aborts mid-stream, retains partial output, resets composer, shows no error', async () => {
    const user = userEvent.setup();
    let aborted = false;
    // A long stream (many slow chunks) so Stop reliably lands mid-flight.
    const chunks = [frame('partial ')];
    for (let i = 0; i < 30; i++) chunks.push(frame(`more${i} `));
    chunks.push('data: [DONE]\n\n');
    const fetchImpl = makeFetch({
      health: 'ready',
      chatChunks: chunks,
      onAbort: () => {
        aborted = true;
      },
    });

    render(<ChatView fetchImpl={fetchImpl} initialHealth="ready" />);
    await user.type(screen.getByLabelText('Message Argus'), 'hello');
    await user.click(screen.getByLabelText('Send message'));

    // Wait for the first token to render, then Stop.
    await waitFor(() => expect(screen.getByText(/partial/)).toBeInTheDocument());
    const stop = await screen.findByLabelText('Stop generating');
    await user.click(stop);

    // Observable outcome: the abort reached the fake stream.
    await waitFor(() => expect(aborted).toBe(true));

    // Composer returns to a ready state (Send replaces Stop).
    await waitFor(() => expect(screen.getByLabelText('Send message')).toBeInTheDocument());
    // Partial output retained.
    expect(screen.getByText(/partial/)).toBeInTheDocument();
    // No error banner for a user stop.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('Stop after completion is a no-op: button absent once [DONE], message unaffected (Edge case 2)', async () => {
    const user = userEvent.setup();
    const fetchImpl = makeFetch({
      health: 'ready',
      chatChunks: [frame('done message'), 'data: [DONE]\n\n'],
    });

    render(<ChatView fetchImpl={fetchImpl} initialHealth="ready" />);
    await user.type(screen.getByLabelText('Message Argus'), 'hi');
    await user.click(screen.getByLabelText('Send message'));

    // Once the stream reaches [DONE], streaming === false: the StopButton is
    // gone and Send is back. There is no Stop control to activate, so a "Stop
    // after completion" is structurally a no-op.
    await waitFor(() => expect(screen.getByLabelText('Send message')).toBeInTheDocument());
    expect(screen.queryByLabelText('Stop generating')).not.toBeInTheDocument();

    // The completed assistant message is intact and no error appeared.
    expect(screen.getByText('done message')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    // Composer remains ready for the next message.
    expect(screen.getByLabelText('Message Argus')).not.toBeDisabled();
  });
});

describe('ChatView — loading state (Scenario 3)', () => {
  it('disables the composer while /health is 503 and enables it on 200', async () => {
    let ready = false;
    const fetchImpl = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
      const url = String(input);
      if (url === '/health') {
        return ready
          ? new Response(JSON.stringify({ status: 'ready' }), { status: 200 })
          : new Response(JSON.stringify({ status: 'loading' }), { status: 503 });
      }
      throw new Error('no chat expected');
    });

    render(<ChatView fetchImpl={fetchImpl} initialHealth="loading" />);

    // Loading banner shown, composer disabled.
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByLabelText('Message Argus')).toBeDisabled();

    // Flip to ready; the poller picks it up.
    ready = true;
    await waitFor(
      () => expect(screen.getByLabelText('Message Argus')).not.toBeDisabled(),
      { timeout: 4000 },
    );
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});

describe('ChatView — error path (Scenario 5)', () => {
  it('surfaces a 502 error, preserves typed input, stays usable', async () => {
    const user = userEvent.setup();
    const fetchImpl = makeFetch({
      health: 'ready',
      chatStatus: 502,
      chatErrorBody: { error: 'upstream model service unavailable', upstream_status: 503 },
    });

    render(<ChatView fetchImpl={fetchImpl} initialHealth="ready" />);
    const input = screen.getByLabelText('Message Argus');
    await user.type(input, 'will fail');
    await user.click(screen.getByLabelText('Send message'));

    // Error surfaced.
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('upstream model service unavailable'),
    );

    // Composer is usable again for a retry.
    await waitFor(() => expect(screen.getByLabelText('Send message')).toBeInTheDocument());
    expect(input).not.toBeDisabled();
  });

  it('surfaces an in-band error frame mid-stream and retains partial output', async () => {
    const user = userEvent.setup();
    const fetchImpl = makeFetch({
      health: 'ready',
      chatChunks: [
        frame('partial answer'),
        'data: {"error": "upstream stream broken"}\n\n',
        'data: [DONE]\n\n',
      ],
    });

    render(<ChatView fetchImpl={fetchImpl} initialHealth="ready" />);
    await user.type(screen.getByLabelText('Message Argus'), 'hi');
    await user.click(screen.getByLabelText('Send message'));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('upstream stream broken'),
    );
    // Partial output kept.
    expect(screen.getByText('partial answer')).toBeInTheDocument();
  });
});

describe('ChatView — composer keyboard behavior (Edge cases 1, 3)', () => {
  it('Enter sends, Shift+Enter inserts a newline, empty submit is ignored', async () => {
    const user = userEvent.setup();
    const fetchImpl = makeFetch({ health: 'ready', chatChunks: [frame('ok'), 'data: [DONE]\n\n'] });

    render(<ChatView fetchImpl={fetchImpl} initialHealth="ready" />);
    const input = screen.getByLabelText('Message Argus') as HTMLTextAreaElement;

    // Empty Enter: no request, no user message.
    input.focus();
    await user.keyboard('{Enter}');
    expect(fetchImpl).not.toHaveBeenCalledWith('/v1/chat/completions', expect.anything());

    // Shift+Enter inserts a newline without submitting.
    await user.type(input, 'line one');
    await user.keyboard('{Shift>}{Enter}{/Shift}');
    await user.type(input, 'line two');
    expect(input.value).toBe('line one\nline two');
    expect(fetchImpl).not.toHaveBeenCalledWith('/v1/chat/completions', expect.anything());

    // Plain Enter submits.
    await user.keyboard('{Enter}');
    await waitFor(() =>
      expect(fetchImpl).toHaveBeenCalledWith('/v1/chat/completions', expect.anything()),
    );
    // The user message preserved the embedded newline (rendered with
    // whitespace-pre-wrap). getByText normalizes whitespace, so match on the
    // raw textContent instead.
    const userBubble = document.querySelector('[data-role="user"]');
    expect(userBubble?.textContent).toBe('line one\nline two');
  });
});

describe('ChatView — empty stream (Edge case 4)', () => {
  it('terminates cleanly when the stream contains only [DONE]', async () => {
    const user = userEvent.setup();
    const fetchImpl = makeFetch({ health: 'ready', chatChunks: ['data: [DONE]\n\n'] });

    render(<ChatView fetchImpl={fetchImpl} initialHealth="ready" />);
    await user.type(screen.getByLabelText('Message Argus'), 'hi');
    await user.click(screen.getByLabelText('Send message'));

    // No hang: composer returns to ready, no error.
    await waitFor(() => expect(screen.getByLabelText('Send message')).toBeInTheDocument());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('ChatView — privacy (Scenario 6)', () => {
  it('only ever fetches same-origin relative paths', async () => {
    const user = userEvent.setup();
    const fetchImpl = makeFetch({ health: 'ready', chatChunks: [frame('hi'), 'data: [DONE]\n\n'] });

    render(<ChatView fetchImpl={fetchImpl} initialHealth="ready" />);
    await user.type(screen.getByLabelText('Message Argus'), 'hi');
    await user.click(screen.getByLabelText('Send message'));
    await waitFor(() => expect(screen.getByLabelText('Send message')).toBeInTheDocument());

    // Every URL passed to fetch is a relative same-origin path — no http(s) host.
    for (const call of fetchImpl.mock.calls) {
      const url = call[0] as string;
      expect(url.startsWith('/')).toBe(true);
      expect(url).not.toMatch(/^https?:\/\//);
    }
  });
});

// Suppress unused-import lint for act (kept available for future timing needs).
void act;
