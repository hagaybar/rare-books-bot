/**
 * Reusable result card for a single matched bibliographic record.
 *
 * Shows title, author, date, place, publisher, subjects, and an
 * expandable evidence section with MARC field citations.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { Candidate } from '../../types/chat';
import ConfidenceBadge from './ConfidenceBadge';
import PrimoLink from './PrimoLink';

interface CandidateCardProps {
  candidate: Candidate;
  index: number;
  /** Optional resolved Primo URL (from batch fetch) */
  primoUrl?: string;
}

/** Format a date range smartly: single year or range. */
function formatDate(start: number | null, end: number | null): string | null {
  if (start === null && end === null) return null;
  if (start !== null && end !== null) {
    if (start === end) return String(start);
    return `${start}\u2013${end}`;
  }
  if (start !== null) return `${start}\u2013`;
  return `\u2013${end}`;
}

/** Format place: show normalized, with raw in parentheses if different. */
function formatPlace(norm: string | null, raw: string | null): string | null {
  if (!norm && !raw) return null;
  if (!norm) return raw;
  if (!raw) return norm;
  // Deduplicate: if casefold-equal, just show the normalized form
  if (norm.toLowerCase() === raw.replace(/[[\]:;,.\s]+/g, ' ').trim().toLowerCase()) {
    return norm;
  }
  return `${norm} (${raw})`;
}

/** Render a single evidence value for display. */
function renderValue(val: unknown): string {
  if (val === null || val === undefined) return '\u2014';
  if (typeof val === 'string') return val;
  if (typeof val === 'number') return String(val);
  if (Array.isArray(val)) return val.join(', ');
  return JSON.stringify(val);
}

export default function CandidateCard({
  candidate,
  index,
  primoUrl,
}: CandidateCardProps) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [descExpanded, setDescExpanded] = useState(false);

  const dateDisplay = formatDate(candidate.date_start, candidate.date_end);
  const placeDisplay = formatPlace(candidate.place_norm, candidate.place_raw);
  const hasImprint = dateDisplay || placeDisplay || candidate.publisher;
  const subjects = candidate.subjects.slice(0, 3);

  const descriptionLong =
    candidate.description && candidate.description.length > 200;

  return (
    <div className="border border-gray-200 rounded-lg p-4 shadow-sm bg-white hover:shadow-md transition-shadow">
      {/* Header row: index + title + Primo link */}
      <div className="flex items-start gap-2">
        <span className="shrink-0 w-6 h-6 rounded-full bg-blue-50 text-blue-700 text-xs font-semibold flex items-center justify-center mt-0.5">
          {index}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-start gap-2">
            <h3 className="text-sm font-semibold text-gray-900 leading-snug flex-1">
              {candidate.title ?? 'Untitled'}
            </h3>
            <PrimoLink mmsId={candidate.record_id} url={primoUrl} />
          </div>

          {/* Author */}
          {candidate.author && (
            <p className="text-xs text-gray-600 mt-0.5">{candidate.author}</p>
          )}
        </div>
      </div>

      {/* Imprint row */}
      {hasImprint ? (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-600">
          {dateDisplay && (
            <span className="inline-flex items-center gap-1">
              <svg className="w-3.5 h-3.5 text-gray-400 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
              </svg>
              {dateDisplay}
            </span>
          )}
          {placeDisplay && (
            <span className="inline-flex items-center gap-1">
              <svg className="w-3.5 h-3.5 text-gray-400 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
              </svg>
              {placeDisplay}
            </span>
          )}
          {candidate.publisher && (
            <span className="inline-flex items-center gap-1">
              <svg className="w-3.5 h-3.5 text-gray-400 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
              </svg>
              {candidate.publisher}
            </span>
          )}
        </div>
      ) : (
        <p className="mt-2 text-xs text-gray-400 italic">No imprint data</p>
      )}

      {/* Subjects */}
      {subjects.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {subjects.map((subj) => (
            <span
              key={subj}
              className="inline-block px-2 py-0.5 rounded-full bg-gray-100 text-[11px] text-gray-700 leading-tight"
            >
              {subj}
            </span>
          ))}
        </div>
      )}

      {/* Description */}
      {candidate.description && (
        <div className="mt-2">
          <p className="text-xs text-gray-600 leading-relaxed">
            {descriptionLong && !descExpanded
              ? candidate.description.slice(0, 200) + '...'
              : candidate.description}
          </p>
          {descriptionLong && (
            <button
              type="button"
              onClick={() => setDescExpanded(!descExpanded)}
              className="text-[11px] text-blue-600 hover:text-blue-800 mt-0.5"
            >
              {descExpanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </div>
      )}

      {/* Evidence toggle */}
      {candidate.evidence.length > 0 && (
        <div className="mt-3 border-t border-gray-100 pt-2">
          <button
            type="button"
            onClick={() => setEvidenceOpen(!evidenceOpen)}
            className="flex items-center gap-1.5 text-[11px] font-medium text-gray-500 hover:text-gray-700 transition-colors"
          >
            <svg
              className={`w-3.5 h-3.5 transition-transform ${evidenceOpen ? 'rotate-90' : ''}`}
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
            Evidence ({candidate.evidence.length} field{candidate.evidence.length !== 1 ? 's' : ''})
          </button>

          {evidenceOpen && (
            <div className="mt-2 space-y-1.5">
              {candidate.evidence.map((ev, i) => (
                <div
                  key={`${ev.field}-${i}`}
                  className="flex items-start gap-2 text-[11px] text-gray-600 bg-gray-50 rounded px-2.5 py-1.5"
                >
                  <span className="font-mono font-medium text-gray-800 shrink-0">
                    {ev.field}
                  </span>
                  <span className="text-gray-400">{ev.operator}</span>
                  <span className="text-gray-700 break-all">
                    {renderValue(ev.matched_against)}
                  </span>
                  {ev.confidence !== null && (
                    <ConfidenceBadge confidence={ev.confidence} />
                  )}
                  {ev.source && (
                    <span className="text-gray-400 font-mono shrink-0">
                      [{ev.source}]
                    </span>
                  )}
                  {ev.extraction_error && (
                    <span className="text-red-500 text-[10px]" title={ev.extraction_error}>
                      (error)
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Record ID footer */}
      <div className="mt-2 flex items-center justify-between">
        <span className="text-[10px] text-gray-400 font-mono">
          ID: {candidate.record_id}
        </span>
        <Link
          to="/operator/workbench"
          className="text-[10px] text-gray-400 hover:text-indigo-600 transition-colors flex items-center gap-1"
          title="Flag a metadata issue for this record"
        >
          <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 3v1.5M3 21v-6m0 0l2.77-.693a9 9 0 016.208.682l.108.054a9 9 0 006.086.71l3.114-.732a48.524 48.524 0 01-.005-10.499l-3.11.732a9 9 0 01-6.085-.711l-.108-.054a9 9 0 00-6.208-.682L3 4.5M3 15V4.5" />
          </svg>
          Flag issue
        </Link>
      </div>
    </div>
  );
}
