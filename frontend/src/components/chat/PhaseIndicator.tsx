/**
 * Small pill badge showing the current conversation phase, plus an optional
 * held-set chip with a one-click reset ("Search all").
 *
 * - "Query Definition"   = purple
 * - "Exploring Results"  = emerald
 */

import type { ConversationPhase, ActiveSubgroupSummary } from '../../types/chat';

interface PhaseIndicatorProps {
  phase: ConversationPhase | null;
  heldSet?: ActiveSubgroupSummary | null;
  onReset?: () => void;
}

const PHASE_CONFIG: Record<string, { label: string; classes: string }> = {
  query_definition: {
    label: 'Query Definition',
    classes: 'bg-purple-100 text-purple-700',
  },
  corpus_exploration: {
    label: 'Exploring Results',
    classes: 'bg-emerald-100 text-emerald-700',
  },
};

export default function PhaseIndicator({ phase, heldSet, onReset }: PhaseIndicatorProps) {
  const cfg = phase ? PHASE_CONFIG[phase] : null;

  if (!cfg && !heldSet) return null;

  return (
    <span className="inline-flex items-center gap-2 flex-wrap">
      {cfg && (
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${cfg.classes}`}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-current opacity-60" />
          {cfg.label}
        </span>
      )}
      {heldSet && (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-800 border border-emerald-200">
          <span>
            Exploring {heldSet.count} <bdi>{heldSet.defining_query}</bdi>
          </span>
          {onReset && (
            <button
              type="button"
              onClick={onReset}
              className="underline decoration-dotted hover:text-emerald-900 focus:outline-none focus:ring-1 focus:ring-emerald-400 rounded"
              aria-label="Clear the held result set and search the whole collection"
            >
              Search all
            </button>
          )}
        </span>
      )}
    </span>
  );
}
