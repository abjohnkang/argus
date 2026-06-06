/**
 * Indeterminate "model is loading" banner shown WHILE GET /health is 503
 * (REQ-UI-003). Status is conveyed by text (role="status"), not color alone
 * (WCAG 2.1 AA), and never times out into an error.
 */
export function LoadingState() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-3 border-b border-border bg-surface-muted px-4 py-3 text-sm text-text-muted"
    >
      <span
        className="h-3 w-3 animate-pulse rounded-full bg-accent"
        aria-hidden="true"
      />
      <span>The model is loading. This can take a while on first run — the composer will enable automatically.</span>
    </div>
  );
}
