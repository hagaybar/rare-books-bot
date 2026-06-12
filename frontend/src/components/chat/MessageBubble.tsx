/**
 * Chat message bubble component.
 *
 * User messages: right-aligned, blue background, white text.
 * Bot messages: left-aligned, white background, dark text with results.
 */

import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import type { ChatMessage, GroundingData } from '../../types/chat';
import CandidateCard from '../shared/CandidateCard';
import ConfidenceBadge from '../shared/ConfidenceBadge';
import GroundingSources from './GroundingSources';
import PhaseIndicator from './PhaseIndicator';
import ThinkingBlock from './ThinkingBlock';

interface MessageBubbleProps {
  message: ChatMessage;
  primoUrls: Record<string, string>;
}

/** Maximum candidates to render inline. */
const MAX_INLINE_CANDIDATES = 10;

/**
 * Strip follow-up suggestions that the LLM may have embedded at the end
 * of the narrative text, e.g.:
 *
 *   "You might also ask:" / "Suggested follow-ups:" / "Some questions..."
 *   - question one
 *   - question two
 *
 * Follow-up suggestions are no longer a product feature; this is the safety
 * net that keeps them out of the narrative even if the LLM appends such a
 * section despite its instructions.
 */
function stripTrailingFollowups(markdown: string): string {
  // Remove common follow-up header sections at the end:
  // "**Suggested follow-ups:**", "### Follow-up questions", etc.,
  // followed by a list of items until end of string
  const cleaned = markdown.replace(
    /\n+(?:#{1,4}\s*)?(?:\*{0,2})(?:suggested\s+follow[\s-]*ups?|you\s+(?:might|could)\s+(?:also\s+)?(?:ask|explore|consider)|follow[\s-]*up\s+questions?|further\s+(?:questions?|exploration)|want\s+to\s+(?:know|explore)\s+more)(?:\*{0,2}):?\s*\n(?:[-*\d.]\s+.+\n?)*$/i,
    '',
  );

  return cleaned.trimEnd();
}

export default function MessageBubble({
  message,
  primoUrls,
}: MessageBubbleProps) {
  const [queryDetailsOpen, setQueryDetailsOpen] = useState(false);
  const [narrativeOpen, setNarrativeOpen] = useState(false);
  const isUser = message.role === 'user';

  // ---- User message ----
  if (isUser) {
    return (
      <div className="flex justify-end">
        <div dir="auto" className="max-w-[75%] px-4 py-2.5 rounded-2xl rounded-br-md bg-blue-600 text-white text-sm leading-relaxed shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  // ---- Bot message ----
  const isStreaming = message.streamingState === 'streaming';
  const isThinking = message.streamingState === 'thinking';
  const isStreamComplete = message.streamingState === 'complete' || !message.streamingState;
  const thinkingSteps = message.thinkingSteps ?? [];

  const navigate = useNavigate();
  const candidates = message.candidateSet?.candidates ?? [];

  // Chat -> map (issue #34): plot this result set's printing places as an
  // overlay on the cities map. Hand off via sessionStorage (no URL-size limits).
  const showOnMap = () => {
    const places: Record<string, number> = {};
    for (const c of candidates) {
      if (c.place_norm) places[c.place_norm] = (places[c.place_norm] ?? 0) + 1;
    }
    sessionStorage.setItem('chatMapOverlay', JSON.stringify({
      label: message.candidateSet?.query_text ?? 'chat results',
      total: message.candidateSet?.total_count ?? candidates.length,
      located: Object.values(places).reduce((a, b) => a + b, 0),
      places,
    }));
    navigate('/network?overlay=chat');
  };
  const displayCandidates = candidates.slice(0, MAX_INLINE_CANDIDATES);
  const totalCount = message.candidateSet?.total_count ?? candidates.length;
  const executionTime = message.metadata?.execution_time_ms as number | undefined;
  const filtersCount = message.metadata?.filters_count as number | undefined;
  const agentNarrative = message.metadata?.agent_narrative as string | undefined;

  // Extract grounding data from metadata (may be undefined)
  const grounding = message.metadata?.grounding as GroundingData | undefined;
  const hasGrounding =
    grounding &&
    ((grounding.records?.length ?? 0) > 0 ||
     (grounding.agents?.length ?? 0) > 0 ||
     (grounding.links?.length ?? 0) > 0);

  // Strip any followup section the LLM embedded in the narrative text
  const cleanedContent = useMemo(
    () => stripTrailingFollowups(message.content),
    [message.content],
  );

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-3">
        {/* Thinking block (active during thinking, collapsible after) */}
        {thinkingSteps.length > 0 && (
          <ThinkingBlock
            steps={thinkingSteps}
            isActive={isThinking}
            defaultCollapsed={isStreamComplete}
          />
        )}

        {/* Phase + confidence header */}
        {isStreamComplete && (message.phase || message.confidence !== null) && (
          <div className="flex items-center gap-2 flex-wrap">
            <PhaseIndicator phase={message.phase} />
            {message.confidence !== null && (
              <span className="inline-flex items-center gap-1 text-[11px] text-gray-500">
                Confidence: <ConfidenceBadge confidence={message.confidence} showLabel />
              </span>
            )}
          </div>
        )}

        {/* Clarification prompt */}
        {isStreamComplete && message.clarificationNeeded && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
            <div className="flex items-start gap-2">
              <svg className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
              </svg>
              <div dir="auto" className="text-sm text-amber-800 leading-relaxed">
                <ReactMarkdown>{message.clarificationNeeded}</ReactMarkdown>
              </div>
            </div>
          </div>
        )}

        {/* Main message text -- thinking, streaming, or complete */}
        {!message.clarificationNeeded && (isThinking || isStreaming || isStreamComplete) && (
        <div className="px-4 py-3 rounded-2xl rounded-bl-md bg-white border border-gray-200 text-sm text-gray-800 leading-relaxed shadow-sm">
          {isThinking ? (
            /* Thinking: show blinking cursor as typing indicator */
            <div dir="auto" className="chat-markdown-content prose prose-sm prose-gray max-w-none [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1">
              <span
                className="inline-block w-[2px] h-[1em] bg-gray-400 align-text-bottom"
                style={{ animation: 'blink-cursor 1s step-end infinite' }}
                aria-hidden="true"
              />
            </div>
          ) : isStreaming ? (
            /* Streaming: show text so far with blinking cursor */
            <div dir="auto" className="chat-markdown-content prose prose-sm prose-gray max-w-none [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1">
              <ReactMarkdown>{message.content}</ReactMarkdown>
              <span
                className="inline-block w-[2px] h-[1em] bg-gray-600 ml-0.5 align-text-bottom"
                style={{ animation: 'blink-cursor 1s step-end infinite' }}
                aria-hidden="true"
              />
            </div>
          ) : cleanedContent ? (
            /* Complete with content: normal render */
            <div dir="auto" className="chat-markdown-content prose prose-sm prose-gray max-w-none [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1">
              <ReactMarkdown>{cleanedContent}</ReactMarkdown>
            </div>
          ) : (
            /* Complete but empty content: show fallback */
            <div dir="auto" className="chat-markdown-content prose prose-sm prose-gray max-w-none [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1">
              <p className="text-gray-400 italic">No response text available.</p>
            </div>
          )}

          {/* Execution time + query details */}
          <div className="mt-2 flex items-center gap-3 flex-wrap">
            {executionTime !== undefined && (
              <span className="text-[11px] text-gray-400">
                {executionTime < 1000
                  ? `${Math.round(executionTime)}ms`
                  : `${(executionTime / 1000).toFixed(1)}s`}
              </span>
            )}
            {filtersCount !== undefined && filtersCount > 0 && (
              <button
                type="button"
                onClick={() => setQueryDetailsOpen(!queryDetailsOpen)}
                className="text-[11px] text-gray-400 hover:text-gray-600 transition-colors"
              >
                {queryDetailsOpen ? 'Hide' : 'Show'} query details ({filtersCount} filter{filtersCount !== 1 ? 's' : ''})
              </button>
            )}
          </div>
          {queryDetailsOpen && message.candidateSet && (
            <div className="mt-2 p-2 rounded bg-gray-50 font-mono text-[10px] text-gray-500 overflow-x-auto">
              <pre className="whitespace-pre-wrap break-all">{message.candidateSet.sql}</pre>
            </div>
          )}
        </div>
        )}

        {/* Agent narrative (biographical context) */}
        {agentNarrative && (
          <div className="rounded-lg border border-blue-100 bg-blue-50 ml-2">
            <button
              type="button"
              onClick={() => setNarrativeOpen(!narrativeOpen)}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-blue-700 hover:text-blue-900 transition-colors"
            >
              <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
              </svg>
              <span className="font-medium">About the people</span>
              <svg
                className={`w-3 h-3 ml-auto transition-transform ${narrativeOpen ? 'rotate-180' : ''}`}
                fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
              </svg>
            </button>
            {narrativeOpen && (
              <div className="px-3 pb-3 text-sm text-blue-900 leading-relaxed">
                <div dir="auto" className="chat-markdown-content prose prose-sm prose-blue max-w-none [&_p]:my-1 [&_ul]:my-1 [&_li]:my-0.5">
                  <ReactMarkdown>{agentNarrative}</ReactMarkdown>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Grounding: Sources & References */}
        {hasGrounding && grounding && (
          <GroundingSources grounding={grounding} />
        )}

        {/* Candidate cards */}
        {displayCandidates.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs text-gray-500 font-medium px-1 flex items-center gap-3">
              <span>
                {totalCount} result{totalCount !== 1 ? 's' : ''} found
                {displayCandidates.length < totalCount &&
                  ` (showing first ${displayCandidates.length})`}
              </span>
              {candidates.some((c) => c.place_norm) && (
                <button
                  type="button"
                  onClick={showOnMap}
                  className="text-blue-500 hover:text-blue-700 font-medium"
                  title="Plot these results' printing places on the map"
                >
                  Show on map →
                </button>
              )}
            </p>
            {displayCandidates.map((c, i) => (
              <CandidateCard
                key={c.record_id}
                candidate={c}
                index={i + 1}
                primoUrl={primoUrls[c.record_id]}
              />
            ))}
          </div>
        )}

      </div>
    </div>
  );
}
