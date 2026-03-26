import { useState, useEffect, useRef } from 'react';
import { useNetworkStore } from '../../stores/networkStore';
import { CONNECTION_TYPE_CONFIG } from '../../types/network';
import type { ConnectionType } from '../../types/network';

function useDebouncedCallback(callback: (val: number) => void, delay: number) {
  const timerRef = useRef<ReturnType<typeof setTimeout>>();
  return (val: number) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => callback(val), delay);
  };
}

const CENTURIES = [
  { value: null, label: 'All' },
  { value: 15, label: '15th (1400s)' },
  { value: 16, label: '16th (1500s)' },
  { value: 17, label: '17th (1600s)' },
  { value: 18, label: '18th (1700s)' },
  { value: 19, label: '19th (1800s)' },
  { value: 20, label: '20th (1900s)' },
];

const ROLES = [
  { value: null, label: 'All Roles' },
  { value: 'author', label: 'Author' },
  { value: 'printer', label: 'Printer' },
  { value: 'publisher', label: 'Publisher' },
  { value: 'editor', label: 'Editor' },
  { value: 'translator', label: 'Translator' },
];

export default function ControlBar() {
  const {
    connectionTypes,
    toggleConnectionType,
    century,
    setCentury,
    role,
    setRole,
    agentLimit,
    setAgentLimit,
  } = useNetworkStore();

  return (
    <div className="px-4 py-3 bg-white border-b flex flex-wrap items-center gap-4">
      {/* Connection type toggles */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-gray-700">Connections:</span>
        {(Object.entries(CONNECTION_TYPE_CONFIG) as [ConnectionType, typeof CONNECTION_TYPE_CONFIG[ConnectionType]][]).map(
          ([type, config]) => {
            const active = connectionTypes.includes(type);
            const [r, g, b] = config.color;
            return (
              <button
                key={type}
                onClick={() => toggleConnectionType(type)}
                className={`px-2 py-1 text-xs rounded border transition-colors ${
                  active
                    ? 'text-white border-transparent'
                    : 'text-gray-500 border-gray-300 bg-white hover:bg-gray-50'
                }`}
                style={active ? { backgroundColor: `rgb(${r},${g},${b})` } : undefined}
              >
                {config.label}
              </button>
            );
          }
        )}
      </div>

      {/* Century filter */}
      <div className="flex items-center gap-1">
        <span className="text-sm text-gray-600">Century:</span>
        <select
          value={century ?? ''}
          onChange={(e) => setCentury(e.target.value ? Number(e.target.value) : null)}
          className="text-sm border border-gray-300 rounded px-2 py-1"
        >
          {CENTURIES.map((c) => (
            <option key={c.label} value={c.value ?? ''}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      {/* Role filter */}
      <div className="flex items-center gap-1">
        <span className="text-sm text-gray-600">Role:</span>
        <select
          value={role ?? ''}
          onChange={(e) => setRole(e.target.value || null)}
          className="text-sm border border-gray-300 rounded px-2 py-1"
        >
          {ROLES.map((r) => (
            <option key={r.label} value={r.value ?? ''}>
              {r.label}
            </option>
          ))}
        </select>
      </div>

      {/* Agent count slider (debounced to avoid rapid API calls while dragging) */}
      <AgentSlider />
    </div>
  );
}

function AgentSlider() {
  const { agentLimit, setAgentLimit } = useNetworkStore();
  const [localValue, setLocalValue] = useState(agentLimit);
  const debouncedSet = useDebouncedCallback(setAgentLimit, 300);

  // Sync local value when store changes externally (e.g., reset)
  useEffect(() => { setLocalValue(agentLimit); }, [agentLimit]);

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-gray-600">Agents:</span>
      <input
        type="range"
        min={50}
        max={500}
        step={10}
        value={localValue}
        onChange={(e) => {
          const val = Number(e.target.value);
          setLocalValue(val);
          debouncedSet(val);
        }}
        className="w-24"
      />
      <span className="text-sm text-gray-500 w-8">{localValue}</span>
    </div>
  );
}
