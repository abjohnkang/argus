interface ModelBadgeProps {
  modelName: string | null;
}

/**
 * Optional active-model-name display (REQ-UI-004 Optional/WHERE clause — NOT
 * acceptance-gated). Falls back to a neutral label when the name is unknown.
 */
export function ModelBadge({ modelName }: ModelBadgeProps) {
  return (
    <span className="rounded-full border border-border bg-surface-muted px-2.5 py-0.5 text-xs text-text-muted">
      {modelName ?? 'local model'}
    </span>
  );
}
