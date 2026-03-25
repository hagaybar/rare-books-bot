import { useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import type { Cluster } from '../../types/metadata';

interface ClusterCardProps {
  cluster: Cluster;
  onProposeMappings: (clusterId: string) => void;
  isProposing: boolean;
}

const TYPE_COLORS: Record<string, string> = {
  duplicate: 'bg-orange-100 text-orange-800',
  variant: 'bg-blue-100 text-blue-800',
  spelling: 'bg-purple-100 text-purple-800',
  language: 'bg-teal-100 text-teal-800',
};

function priorityColor(score: number): string {
  if (score >= 0.8) return 'text-red-600';
  if (score >= 0.5) return 'text-orange-600';
  return 'text-gray-600';
}

export default function ClusterCard({ cluster, onProposeMappings, isProposing }: ClusterCardProps) {
  const [expanded, setExpanded] = useState(false);

  const handleToggle = useCallback(() => {
    setExpanded((prev) => !prev);
  }, []);

  const typeClass = TYPE_COLORS[cluster.cluster_type] ?? 'bg-gray-100 text-gray-800';

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
      <button
        type="button"
        onClick={handleToggle}
        className="w-full text-left px-5 py-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${typeClass}`}>
            {cluster.cluster_type}
          </span>
          <span className="text-sm font-medium text-gray-900">
            {cluster.proposed_canonical ?? cluster.cluster_id}
          </span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-gray-500">
            {cluster.values.length} value{cluster.values.length !== 1 ? 's' : ''}
          </span>
          <span className="text-gray-500">
            {cluster.total_records_affected} record{cluster.total_records_affected !== 1 ? 's' : ''}
          </span>
          <span className={`font-medium ${priorityColor(cluster.priority_score)}`}>
            P:{cluster.priority_score.toFixed(2)}
          </span>
          <svg
            className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-100 px-5 py-3">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 text-xs uppercase tracking-wider">
                <th className="pb-2 font-medium">Raw Value</th>
                <th className="pb-2 font-medium">Frequency</th>
                <th className="pb-2 font-medium">Confidence</th>
                <th className="pb-2 font-medium">Method</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {cluster.values.map((val) => (
                <tr key={val.raw_value}>
                  <td className="py-1.5 text-gray-900 font-mono text-xs">{val.raw_value}</td>
                  <td className="py-1.5 text-gray-600">{val.frequency}</td>
                  <td className="py-1.5 text-gray-600">{val.confidence.toFixed(2)}</td>
                  <td className="py-1.5 text-gray-600">{val.method}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between">
            <Link
              to={`/operator/agent?cluster=${cluster.cluster_id}&field=${cluster.field}`}
              className="text-sm text-gray-500 hover:text-indigo-600 transition-colors flex items-center gap-1"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
              Ask agent
            </Link>
            <button
              onClick={() => onProposeMappings(cluster.cluster_id)}
              disabled={isProposing}
              className="text-sm font-medium text-indigo-600 hover:text-indigo-800 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isProposing ? 'Proposing...' : 'Propose mappings'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
