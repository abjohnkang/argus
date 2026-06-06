interface StopButtonProps {
  onStop: () => void;
}

/** Abort the in-flight stream (REQ-UI-004). Shown only while streaming. */
export function StopButton({ onStop }: StopButtonProps) {
  return (
    <button
      type="button"
      onClick={onStop}
      aria-label="Stop generating"
      className="rounded-lg border border-border bg-surface-muted px-4 py-2 text-sm font-medium text-text hover:bg-border focus-visible:outline focus-visible:outline-2"
    >
      Stop
    </button>
  );
}
