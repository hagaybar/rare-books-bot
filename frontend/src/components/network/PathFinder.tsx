import { useState, useRef } from 'react';
import { searchNetworkAgents } from '../../api/network';
import type { NetworkSearchResult } from '../../api/network';
import type { PathResponse, MapEdge } from '../../types/network';
import { CONNECTION_TYPE_CONFIG } from '../../types/network';

interface Props {
  sourceName: string;
  path: PathResponse | null;
  loading: boolean;
  onSelectTarget: (norm: string) => void;
  onClear: () => void;
  onNodeClick: (norm: string, displayName: string) => void;
}

function relLabel(edge: MapEdge | undefined): string {
  if (!edge) return '';
  const cfg = CONNECTION_TYPE_CONFIG[edge.type as keyof typeof CONNECTION_TYPE_CONFIG];
  return edge.relationship || cfg?.label || edge.type;
}

/** "How are X and Y connected?" — find-path box + evidence-labeled chain (#33). */
export default function PathFinder({ sourceName, path, loading, onSelectTarget, onClear, onNodeClick }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<NetworkSearchResult[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const onChange = (v: string) => {
    setQuery(v);
    if (timer.current) clearTimeout(timer.current);
    if (v.trim().length < 2) { setResults([]); return; }
    timer.current = setTimeout(async () => setResults(await searchNetworkAgents(v)), 300);
  };
  const pick = (r: NetworkSearchResult) => {
    setQuery(r.display_name);
    setResults([]);
    onSelectTarget(r.agent_norm);
  };
  const clear = () => { setQuery(''); setResults([]); onClear(); };

  return (
    <div className="px-4 py-2 bg-white border-b text-sm" data-tour="pathfinder">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-gray-500">Find path from</span>
        <span className="font-medium text-gray-900 max-w-[180px] truncate" title={sourceName}>
          <bdi dir="auto">{sourceName}</bdi>
        </span>
        <span className="text-gray-500">to</span>
        <div className="relative">
          <input
            value={query}
            onChange={(e) => onChange(e.target.value)}
            placeholder="search a person…"
            className="text-sm border border-gray-300 rounded px-2 py-1 w-48 focus:outline-none focus:ring-1 focus:ring-blue-400"
          />
          {results.length > 0 && (
            <ul className="absolute top-full left-0 mt-1 w-64 bg-white border border-gray-200 rounded shadow-lg z-50 max-h-56 overflow-y-auto">
              {results.map((r) => (
                <li key={r.agent_norm}>
                  <button onClick={() => pick(r)} className="w-full text-start px-3 py-1.5 hover:bg-gray-50 truncate">
                    <bdi dir="auto">{r.display_name}</bdi>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {(path || loading) && (
          <button onClick={clear} className="text-xs text-gray-500 hover:text-gray-700 underline">clear</button>
        )}
      </div>

      {loading && <div className="mt-2 text-xs text-gray-400">Finding path…</div>}

      {path && !loading && (path.found ? (
        <div className="mt-2 flex items-center gap-1 flex-wrap">
          {path.nodes.map((n, i) => (
            <span key={`${n.agent_norm}-${i}`} className="flex items-center gap-1">
              {i > 0 && (
                <span
                  className="flex flex-col items-center text-[10px] text-gray-500 px-0.5"
                  title={path.edges[i - 1]?.evidence ?? undefined}
                >
                  <span aria-hidden className="leading-none">→</span>
                  <span className="leading-none">{relLabel(path.edges[i - 1])}</span>
                </span>
              )}
              <button
                onClick={() => onNodeClick(n.agent_norm, n.display_name)}
                className="px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-100 max-w-[160px] truncate"
                title={n.display_name}
              >
                <bdi dir="auto">{n.display_name}</bdi>
              </button>
            </span>
          ))}
          <span className="ml-1 text-xs text-gray-400">({path.hops} hop{path.hops === 1 ? '' : 's'})</span>
        </div>
      ) : (
        <div className="mt-2 text-xs text-gray-500">
          No path within the active connection types. Try enabling more types (e.g. “Mentioned Together”).
        </div>
      ))}
    </div>
  );
}
