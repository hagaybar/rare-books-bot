/**
 * Collapsible "Sources & References" section that renders grounding data
 * from the API response (records, agents, links).
 *
 * Default state: collapsed, showing only a header with counts.
 * Expanded: record cards with catalog links, agent profiles with external links.
 */

import { useState } from 'react';
import type { GroundingData } from '../../types/chat';

interface GroundingSourcesProps {
  grounding: GroundingData;
}

export default function GroundingSources({ grounding }: GroundingSourcesProps) {
  const [open, setOpen] = useState(false);

  const recordCount = grounding.records.length;
  const agentCount = grounding.agents.length;
  const linkCount = grounding.links.length;

  // Nothing to show
  if (recordCount === 0 && agentCount === 0 && linkCount === 0) {
    return null;
  }

  // Build summary label
  const parts: string[] = [];
  if (recordCount > 0) {
    parts.push(`${recordCount} record${recordCount !== 1 ? 's' : ''}`);
  }
  if (agentCount > 0) {
    parts.push(`${agentCount} agent${agentCount !== 1 ? 's' : ''}`);
  }
  if (linkCount > 0 && recordCount === 0 && agentCount === 0) {
    parts.push(`${linkCount} link${linkCount !== 1 ? 's' : ''}`);
  }
  const summary = parts.join(', ');

  return (
    <div className="rounded-lg border border-gray-700 bg-gray-800/50 ml-1">
      {/* Header / toggle */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:text-gray-100 transition-colors cursor-pointer"
      >
        {/* Book/source icon */}
        <svg
          className="w-4 h-4 shrink-0 text-gray-400"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"
          />
        </svg>
        <span className="font-medium">Sources &amp; References</span>
        <span className="text-xs text-gray-500">({summary})</span>
        <svg
          className={`w-3 h-3 ml-auto transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
        </svg>
      </button>

      {/* Expanded content */}
      {open && (
        <div className="px-3 pb-3 space-y-4">
          {/* Records section */}
          {recordCount > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Collection Records
              </h4>
              <div className="space-y-2">
                {grounding.records.map((rec) => (
                  <div
                    key={rec.mms_id}
                    className="rounded-md border border-gray-700 bg-gray-800 p-3"
                  >
                    <h5 className="text-sm font-medium text-gray-200 leading-snug">
                      {rec.title}
                    </h5>

                    {/* Metadata row */}
                    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-400">
                      {rec.date_display && (
                        <span className="inline-flex items-center gap-1">
                          <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
                          </svg>
                          {rec.date_display}
                        </span>
                      )}
                      {rec.place && (
                        <span className="inline-flex items-center gap-1">
                          <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
                          </svg>
                          {rec.place}
                        </span>
                      )}
                      {rec.publisher && (
                        <span className="inline-flex items-center gap-1">
                          <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
                          </svg>
                          {rec.publisher}
                        </span>
                      )}
                    </div>

                    {/* Primo link */}
                    {rec.primo_url && (
                      <a
                        href={rec.primo_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-2 inline-flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 hover:underline transition-colors"
                      >
                        <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                        </svg>
                        View in Catalog
                      </a>
                    )}

                    {/* MMS ID */}
                    <span className="block mt-1 text-[10px] text-gray-600 font-mono">
                      {rec.mms_id}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Agents section */}
          {agentCount > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                People &amp; Agents
              </h4>
              <div className="space-y-2">
                {grounding.agents.map((agent) => {
                  const dates =
                    agent.birth_year || agent.death_year
                      ? `${agent.birth_year ?? '?'}\u2013${agent.death_year ?? '?'}`
                      : null;

                  return (
                    <div
                      key={agent.canonical_name}
                      className="rounded-md border border-gray-700 bg-gray-800 p-3"
                    >
                      <div className="flex items-start gap-2">
                        {/* Person icon */}
                        <svg
                          className="w-4 h-4 text-gray-500 mt-0.5 shrink-0"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth={1.5}
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"
                          />
                        </svg>
                        <div className="flex-1 min-w-0">
                          <span className="text-sm font-medium text-gray-200">
                            {agent.canonical_name}
                          </span>
                          {dates && (
                            <span className="ml-2 text-xs text-gray-500">({dates})</span>
                          )}
                          {agent.occupations.length > 0 && (
                            <p className="text-xs text-gray-400 mt-0.5">
                              {agent.occupations.join(', ')}
                            </p>
                          )}
                        </div>
                      </div>

                      {/* External links */}
                      {agent.links.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {agent.links.map((link) => (
                            <a
                              key={link.url}
                              href={link.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px]
                                bg-gray-700 text-blue-400 hover:text-blue-300 hover:bg-gray-600
                                transition-colors"
                            >
                              <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                              </svg>
                              {link.source}
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Standalone links (when no records/agents but links exist) */}
          {recordCount === 0 && agentCount === 0 && linkCount > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Reference Links
              </h4>
              <div className="flex flex-wrap gap-2">
                {grounding.links.map((link) => (
                  <a
                    key={link.url}
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs
                      bg-gray-700 text-blue-400 hover:text-blue-300 hover:bg-gray-600
                      transition-colors"
                  >
                    <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                    </svg>
                    {link.label} ({link.source})
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
