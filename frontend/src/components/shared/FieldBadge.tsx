/**
 * Small badge showing a metadata field name with color coding.
 *
 * Used across Workbench, Coverage, and Query Debugger to provide
 * consistent visual identification of field types.
 */

type FieldType = 'date' | 'place' | 'publisher' | 'agent';

interface FieldBadgeProps {
  field: FieldType;
  /** Optional size variant */
  size?: 'sm' | 'md';
  /** Optional extra CSS classes */
  className?: string;
}

const FIELD_STYLES: Record<FieldType, { bg: string; text: string; label: string }> = {
  date: { bg: 'bg-blue-100', text: 'text-blue-800', label: 'Date' },
  place: { bg: 'bg-green-100', text: 'text-green-800', label: 'Place' },
  publisher: { bg: 'bg-purple-100', text: 'text-purple-800', label: 'Publisher' },
  agent: { bg: 'bg-amber-100', text: 'text-amber-800', label: 'Agent' },
};

export default function FieldBadge({ field, size = 'sm', className = '' }: FieldBadgeProps) {
  const style = FIELD_STYLES[field];
  if (!style) return null;

  const sizeClasses = size === 'sm'
    ? 'px-1.5 py-0.5 text-[10px]'
    : 'px-2 py-0.5 text-xs';

  return (
    <span
      className={`inline-flex items-center font-medium rounded-full ${style.bg} ${style.text} ${sizeClasses} ${className}`}
    >
      {style.label}
    </span>
  );
}

export type { FieldType };
