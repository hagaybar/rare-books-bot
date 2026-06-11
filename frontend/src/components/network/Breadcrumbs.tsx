import { useNetworkStore } from '../../stores/networkStore';

/** The ego-walk trail (Spinoza › Rieuwertsz › …) — issue #31. Click to jump back. */
export default function Breadcrumbs() {
  const egoTrail = useNetworkStore((s) => s.egoTrail);
  const focusAgent = useNetworkStore((s) => s.focusAgent);
  const popTrailTo = useNetworkStore((s) => s.popTrailTo);
  if (egoTrail.length === 0) return null;

  return (
    <div className="flex items-center gap-1 px-4 py-1.5 bg-white border-b text-sm overflow-x-auto no-scrollbar">
      <span className="text-gray-400 shrink-0 mr-1">Trail:</span>
      {egoTrail.map((c, i) => (
        <span key={`${c.agent_norm}-${i}`} className="flex items-center gap-1 shrink-0">
          {i > 0 && <span className="text-gray-300" aria-hidden>›</span>}
          <button
            onClick={() => popTrailTo(c.agent_norm)}
            className={`px-1 rounded hover:bg-gray-100 max-w-[160px] truncate ${
              c.agent_norm === focusAgent ? 'font-semibold text-gray-900' : 'text-blue-600'
            }`}
            title={c.display_name}
          >
            <bdi dir="auto">{c.display_name}</bdi>
          </button>
        </span>
      ))}
    </div>
  );
}
