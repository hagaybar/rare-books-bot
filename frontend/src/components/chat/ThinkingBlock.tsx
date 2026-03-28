/**
 * ThinkingBlock -- collapsible display of reasoning/thinking steps.
 *
 * When active: muted blue/gray box with pulse animation showing the latest step.
 * When collapsed (after complete): toggle to expand all thinking steps.
 * When expanded: numbered list of all thinking steps.
 */

import { useState } from 'react';

interface ThinkingBlockProps {
  steps: string[];
  isActive: boolean;
  defaultCollapsed?: boolean;
}

export default function ThinkingBlock({
  steps,
  isActive,
  defaultCollapsed = true,
}: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(!defaultCollapsed);

  if (steps.length === 0) return null;

  // ---- Active state: show latest step with pulse animation ----
  if (isActive) {
    const latestStep = steps[steps.length - 1];
    return (
      <div className="flex justify-start">
        <div className="max-w-[75%] px-4 py-3 rounded-2xl rounded-bl-md bg-gray-100 border border-gray-200 shadow-sm animate-pulse">
          <div className="flex items-center gap-2">
            <span className="text-base" aria-hidden="true">
              {'\uD83D\uDCAD'}
            </span>
            <span className="text-sm text-gray-500 italic">{latestStep}</span>
          </div>
        </div>
      </div>
    );
  }

  // ---- Collapsed state: toggle button ----
  if (!expanded) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 transition-colors px-1 py-0.5"
      >
        <span aria-hidden="true">{'\uD83D\uDCAD'}</span>
        <span>
          Show reasoning ({steps.length} step{steps.length !== 1 ? 's' : ''})
        </span>
        <svg
          className="w-3 h-3"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M19.5 8.25l-7.5 7.5-7.5-7.5"
          />
        </svg>
      </button>
    );
  }

  // ---- Expanded state: numbered list of all steps ----
  return (
    <div className="px-3 py-2 rounded-lg bg-gray-50 border border-gray-200">
      <button
        type="button"
        onClick={() => setExpanded(false)}
        className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 transition-colors mb-1.5"
      >
        <span aria-hidden="true">{'\uD83D\uDCAD'}</span>
        <span>
          Hide reasoning ({steps.length} step{steps.length !== 1 ? 's' : ''})
        </span>
        <svg
          className="w-3 h-3 rotate-180"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M19.5 8.25l-7.5 7.5-7.5-7.5"
          />
        </svg>
      </button>
      <ol className="list-decimal list-inside space-y-0.5">
        {steps.map((step, i) => (
          <li key={i} className="text-xs text-gray-500 italic leading-relaxed">
            {step}
          </li>
        ))}
      </ol>
    </div>
  );
}
