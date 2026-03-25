/**
 * Small colored badge displaying a confidence score.
 *
 * Color bands:
 *   >= 0.95  green   "High"
 *   0.80-0.95  amber "Medium"
 *   < 0.80  red      "Low"
 */

interface ConfidenceBadgeProps {
  confidence: number | null;
  /** Show label text alongside percentage (default: false) */
  showLabel?: boolean;
}

export default function ConfidenceBadge({
  confidence,
  showLabel = false,
}: ConfidenceBadgeProps) {
  if (confidence === null || confidence === undefined) {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-100 text-gray-500">
        N/A
      </span>
    );
  }

  const pct = Math.round(confidence * 100);

  let colorClasses: string;
  let label: string;

  if (confidence >= 0.95) {
    colorClasses = 'bg-green-100 text-green-800';
    label = 'High';
  } else if (confidence >= 0.80) {
    colorClasses = 'bg-amber-100 text-amber-800';
    label = 'Medium';
  } else {
    colorClasses = 'bg-red-100 text-red-800';
    label = 'Low';
  }

  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${colorClasses}`}
      title={`Confidence: ${pct}%`}
    >
      {pct}%
      {showLabel && <span className="opacity-80">{label}</span>}
    </span>
  );
}
