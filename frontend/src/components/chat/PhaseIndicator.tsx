/**
 * Small pill badge showing the current conversation phase.
 *
 * - "Query Definition"   = purple
 * - "Exploring Results"  = emerald
 */

import type { ConversationPhase } from '../../types/chat';

interface PhaseIndicatorProps {
  phase: ConversationPhase | null;
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

export default function PhaseIndicator({ phase }: PhaseIndicatorProps) {
  if (!phase) return null;

  const cfg = PHASE_CONFIG[phase];
  if (!cfg) return null;

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${cfg.classes}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-60" />
      {cfg.label}
    </span>
  );
}
