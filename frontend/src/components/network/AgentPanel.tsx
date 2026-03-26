import { useState } from 'react';
import type { AgentDetail } from '../../types/network';
import { CONNECTION_TYPE_CONFIG } from '../../types/network';

interface Props {
  agent: AgentDetail;
  onClose: () => void;
  onAgentClick: (agentNorm: string) => void;
}

export default function AgentPanel({ agent, onClose, onAgentClick }: Props) {
  const [expandedSummary, setExpandedSummary] = useState(false);

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
  const truncatedSummary =
    summaryText.length > 500 && !expandedSummary
      ? summaryText.slice(0, 500) + '...'
      : summaryText;

  return (
    <div className="w-80 bg-white border-l shadow-lg overflow-y-auto flex-shrink-0">
      {/* Header */}
      <div className="p-4 border-b">
        <div className="flex justify-between items-start">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              {agent.display_name}
            </h2>
            {years && (
              <p className="text-sm text-gray-500">
                {years} &middot; {agent.place_norm ?? 'Unknown'}
              </p>
            )}
            {agent.occupations.length > 0 && (
              <p className="text-sm text-gray-400 mt-1">
                {agent.occupations.join(', ')}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
          >
            &times;
          </button>
        </div>
      </div>

      {/* Wikipedia Summary */}
      {summaryText && (
        <div className="p-4 border-b">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Wikipedia</h3>
          <p className="text-sm text-gray-600 leading-relaxed">
            {truncatedSummary}
          </p>
          {summaryText.length > 500 && (
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
      <div className="p-4 border-b">
        <h3 className="text-sm font-medium text-gray-700 mb-2">
          Connections ({agent.connections.length})
        </h3>
        {Object.entries(groupedConnections).map(([type, conns]) => {
          const config =
            CONNECTION_TYPE_CONFIG[type as keyof typeof CONNECTION_TYPE_CONFIG];
          const [r, g, b] = config?.color ?? [156, 163, 175];
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
              {conns.slice(0, 20).map((conn) => (
                <button
                  key={`${conn.agent_norm}-${type}`}
                  onClick={() => onAgentClick(conn.agent_norm)}
                  className="block w-full text-left px-2 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded truncate"
                >
                  {conn.relationship ? `${conn.relationship}: ` : ''}
                  {conn.display_name}
                </button>
              ))}
              {conns.length > 20 && (
                <p className="text-xs text-gray-400 px-2">
                  +{conns.length - 20} more
                </p>
              )}
            </div>
          );
        })}
        {agent.connections.length === 0 && (
          <p className="text-sm text-gray-400">No connections found</p>
        )}
      </div>

      {/* Catalog */}
      <div className="p-4">
        <h3 className="text-sm font-medium text-gray-700 mb-2">In Catalog</h3>
        <p className="text-sm text-gray-600 mb-2">
          {agent.record_count} record{agent.record_count !== 1 ? 's' : ''}
        </p>
        <a
          href={`/chat?q=${encodeURIComponent(`books by ${agent.display_name}`)}`}
          className="text-sm text-blue-500 hover:text-blue-700 block mb-1"
        >
          View in Chat &rarr;
        </a>
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
    </div>
  );
}
