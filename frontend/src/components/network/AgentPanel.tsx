import { useState } from 'react';
import type { AgentDetail } from '../../types/network';
import { CONNECTION_TYPE_CONFIG } from '../../types/network';

interface Props {
  agent: AgentDetail;
  onClose: () => void;
  onAgentClick: (agentNorm: string) => void;
  onPlaceSelect?: (placeNorm: string) => void;
  onExplore?: (agentNorm: string, displayName: string) => void;
  mobile?: boolean;
}

export default function AgentPanel({ agent, onClose, onAgentClick, onPlaceSelect, onExplore, mobile }: Props) {
  const [expandedSummary, setExpandedSummary] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  const isPublisher = agent.node_type === 'publisher';
  const years =
    agent.birth_year || agent.death_year
      ? `${agent.birth_year ?? '?'}\u2013${agent.death_year ?? '?'}`
      : null;

  // Group connections by type
  const groupedConnections = agent.connections.reduce(
    (acc, conn) => {
      if (!acc[conn.type]) acc[conn.type] = [];
      acc[conn.type].push(conn);
      return acc;
    },
    {} as Record<string, typeof agent.connections>
  );

  const summaryText = agent.wikipedia_summary ?? '';
  const summaryLimit = mobile ? 300 : 500;
  const truncatedSummary =
    summaryText.length > summaryLimit && !expandedSummary
      ? summaryText.slice(0, summaryLimit) + '...'
      : summaryText;

  const containerClass = mobile
    ? 'bg-white'
    : 'w-80 bg-white border-l shadow-lg overflow-y-auto flex-shrink-0 h-full';

  return (
    <div className={containerClass}>
      {/* Header */}
      <div className={`${mobile ? 'px-4 pt-1 pb-3' : 'p-4'} border-b`}>
        <div className="flex justify-between items-start">
          <div className="min-w-0 flex-1">
            <h2 className={`${mobile ? 'text-base' : 'text-lg'} font-semibold text-gray-900 truncate`}>
              <bdi dir="auto">{agent.display_name}</bdi>
            </h2>
            {agent.name_alt && (
              <p className="text-sm text-gray-500 truncate" title={agent.name_alt}>
                <bdi dir="auto">{agent.name_alt}</bdi>
              </p>
            )}
            {years && (
              <p className="text-sm text-gray-500">
                {isPublisher ? 'active ' : ''}{years} &middot;{' '}
                {agent.place_norm && onPlaceSelect ? (
                  <button onClick={() => onPlaceSelect(agent.place_norm!)} className="text-blue-600 hover:text-blue-800 capitalize" dir="auto">
                    {agent.place_norm}
                  </button>
                ) : (agent.place_norm ?? 'Unknown')}
              </p>
            )}
            {isPublisher ? (
              <p className="text-xs text-amber-700 mt-0.5 font-medium uppercase tracking-wide">Printing house</p>
            ) : agent.occupations.length > 0 && (
              <p className="text-sm text-gray-400 mt-0.5">
                {agent.occupations.join(', ')}
              </p>
            )}
          </div>
          {!mobile && (
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-xl leading-none ml-2"
            >
              &times;
            </button>
          )}
        </div>
      </div>

      {/* Wikipedia Summary */}
      {summaryText && (
        <div className={`${mobile ? 'px-4 py-3' : 'p-4'} border-b`}>
          <h3 className="text-sm font-medium text-gray-700 mb-1">Wikipedia</h3>
          <p className="text-sm text-gray-600 leading-relaxed">
            {truncatedSummary}
          </p>
          {summaryText.length > summaryLimit && (
            <button
              onClick={() => setExpandedSummary(!expandedSummary)}
              className="text-xs text-blue-500 hover:text-blue-700 mt-1"
            >
              {expandedSummary ? 'Show less' : 'Read more'}
            </button>
          )}
        </div>
      )}

      {/* Connections */}
      <div className={`${mobile ? 'px-4 py-3' : 'p-4'} border-b`}>
        <h3 className="text-sm font-medium text-gray-700 mb-2">
          Connections ({agent.connections.length})
        </h3>
        {Object.entries(groupedConnections).map(([type, conns]) => {
          const config =
            CONNECTION_TYPE_CONFIG[type as keyof typeof CONNECTION_TYPE_CONFIG];
          const [r, g, b] = config?.color ?? [156, 163, 175];
          const defaultLimit = mobile ? 10 : 20;
          const isExpanded = expandedGroups.has(type);
          const displayLimit = isExpanded ? conns.length : defaultLimit;
          return (
            <div key={type} className="mb-3">
              <div className="flex items-center gap-2 mb-1">
                <span
                  className="w-3 h-3 rounded-full inline-block"
                  style={{ backgroundColor: `rgb(${r},${g},${b})` }}
                />
                <span className="text-xs font-medium text-gray-500 uppercase">
                  {config?.label ?? type}
                </span>
              </div>
              <div className={isExpanded ? 'max-h-60 overflow-y-auto' : ''}>
                {conns.slice(0, displayLimit).map((conn) => (
                  <button
                    key={`${conn.agent_norm}-${type}`}
                    onClick={() => onAgentClick(conn.agent_norm)}
                    title={conn.evidence ?? conn.relationship ?? undefined}
                    className={`block w-full text-left px-2 ${mobile ? 'py-1.5' : 'py-1'} text-sm text-blue-600 hover:bg-blue-50 rounded truncate`}
                  >
                    {conn.relationship ? `${conn.relationship}: ` : ''}
                    <bdi dir="auto">{conn.display_name}</bdi>
                  </button>
                ))}
              </div>
              {conns.length > defaultLimit && !isExpanded && (
                <button
                  onClick={() => setExpandedGroups(prev => new Set([...prev, type]))}
                  className="text-xs text-blue-500 hover:text-blue-700 px-2 py-0.5"
                >
                  Show all {conns.length} connections
                </button>
              )}
              {isExpanded && conns.length > defaultLimit && (
                <button
                  onClick={() => setExpandedGroups(prev => { const s = new Set(prev); s.delete(type); return s; })}
                  className="text-xs text-gray-400 hover:text-gray-600 px-2 py-0.5"
                >
                  Show fewer
                </button>
              )}
            </div>
          );
        })}
        {agent.connections.length === 0 && (
          <p className="text-sm text-gray-400">No connections found</p>
        )}
      </div>

      {/* In our collection (issue #18) — the books we actually hold, first */}
      <div className={`${mobile ? 'px-4 py-3' : 'p-4'} border-b`}>
        <h3 className="text-sm font-medium text-gray-700 mb-2">
          {isPublisher ? 'Printed by this house' : 'In our collection'} ({agent.record_count})
        </h3>
        {agent.works.length === 0 ? (
          <p className="text-sm text-gray-400">No catalogued works for this figure.</p>
        ) : (
          <ul className="space-y-2">
            {agent.works.map((w) => (
              <li key={w.mms_id} className="text-sm">
                {w.primo_url ? (
                  <a
                    href={w.primo_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    dir="auto"
                    className="text-blue-600 hover:text-blue-800 font-medium"
                  >
                    {w.title ?? w.mms_id}
                  </a>
                ) : (
                  <span dir="auto" className="font-medium text-gray-800">{w.title ?? w.mms_id}</span>
                )}
                <div className="text-xs text-gray-500">
                  {[w.place_display, w.date_label, w.publisher_display].filter(Boolean).join(' \u00B7 ')}
                  {w.role_norm ? ` \u00B7 ${w.role_norm}` : ''}
                </div>
              </li>
            ))}
          </ul>
        )}
        {onExplore && (
          <button
            onClick={() => onExplore(agent.agent_norm, agent.display_name)}
            className="text-sm text-blue-600 hover:text-blue-800 block mt-3 font-medium"
          >
            Explore connections &rarr;
          </button>
        )}
        <a
          href={`/chat?q=${encodeURIComponent(`books ${isPublisher ? 'printed by' : 'by'} ${agent.display_name}`)}`}
          className="text-sm text-blue-500 hover:text-blue-700 block mt-2"
        >
          Ask about this {isPublisher ? 'house' : 'figure'} in Chat &rarr;
        </a>
      </div>

      {/* External authorities */}
      {Object.keys(agent.external_links).length > 0 && (
        <div className={`${mobile ? 'px-4 py-3' : 'p-4'}`}>
          <h3 className="text-sm font-medium text-gray-700 mb-2">External</h3>
          {Object.entries(agent.external_links).map(([name, url]) => (
            <a
              key={name}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-blue-500 hover:text-blue-700 block mb-1 capitalize"
            >
              {name} &rarr;
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
