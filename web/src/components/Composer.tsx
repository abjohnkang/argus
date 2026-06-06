import { useState, useRef, useEffect, type KeyboardEvent } from 'react';
import { StopButton } from './StopButton';

interface ComposerProps {
  /** When true, the model is loading or a stream is active — input is blocked. */
  disabled: boolean;
  /** True while a stream is in flight — show Stop instead of Send. */
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

/**
 * Message input. Enter submits; Shift+Enter inserts a newline (REQ-UI-002,
 * Edge case 1). The textarea is disabled WHILE the backend is loading
 * (REQ-UI-003). Input is preserved across send failures — it is cleared only
 * when a non-empty message is actually dispatched.
 */
export function Composer({ disabled, streaming, onSend, onStop }: ComposerProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Re-focus the composer when it becomes enabled (e.g. after the model
  // finishes loading, or a stream ends) so keyboard users keep flow.
  useEffect(() => {
    if (!disabled) textareaRef.current?.focus();
  }, [disabled]);

  const submit = () => {
    const text = value.trim();
    if (text === '' || disabled) return;
    onSend(value);
    setValue('');
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
    // Shift+Enter falls through to the default newline insertion.
  };

  return (
    <form
      className="flex items-end gap-2 border-t border-border bg-bg px-4 py-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label htmlFor="composer-input" className="sr-only">
        Message Argus
      </label>
      <textarea
        id="composer-input"
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={1}
        placeholder={disabled && !streaming ? 'Waiting for the model…' : 'Message Argus…'}
        aria-label="Message Argus"
        className="max-h-40 min-h-[2.75rem] flex-1 resize-none rounded-lg border border-border bg-surface px-3 py-2.5 text-text placeholder:text-text-muted focus-visible:outline focus-visible:outline-2 disabled:opacity-50"
      />
      {streaming ? (
        <StopButton onStop={onStop} />
      ) : (
        <button
          type="submit"
          disabled={disabled || value.trim() === ''}
          aria-label="Send message"
          className="rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-accent-fg hover:opacity-90 focus-visible:outline focus-visible:outline-2 disabled:opacity-40"
        >
          Send
        </button>
      )}
    </form>
  );
}
