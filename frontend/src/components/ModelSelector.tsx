/**
 * Model configuration selector for compare mode.
 *
 * Renders a list of interpreter + narrator model pairs with dropdowns.
 * Supports up to 3 configurations with add/remove controls.
 */

import type { ModelPair } from '../types/chat';
import { AVAILABLE_MODELS } from '../types/chat';

interface ModelSelectorProps {
  configs: ModelPair[];
  onChange: (configs: ModelPair[]) => void;
}

const MAX_CONFIGS = 3;

export default function ModelSelector({ configs, onChange }: ModelSelectorProps) {
  const handleUpdate = (index: number, field: keyof ModelPair, value: string) => {
    const updated = configs.map((c, i) =>
      i === index ? { ...c, [field]: value } : c,
    );
    onChange(updated);
  };

  const handleAdd = () => {
    if (configs.length >= MAX_CONFIGS) return;
    onChange([...configs, { interpreter: AVAILABLE_MODELS[0], narrator: AVAILABLE_MODELS[0] }]);
  };

  const handleRemove = (index: number) => {
    if (configs.length <= 1) return;
    onChange(configs.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
        Model Configurations
      </p>

      {configs.map((config, index) => (
        <div
          key={index}
          className="flex items-center gap-3 bg-white border border-gray-200 rounded-lg px-3 py-2"
        >
          {/* Config label */}
          <span className="text-xs font-medium text-gray-400 shrink-0 w-5">
            {index + 1}.
          </span>

          {/* Interpreter dropdown */}
          <div className="flex-1 min-w-0">
            <label className="block text-[10px] text-gray-400 mb-0.5">Interpreter</label>
            <select
              value={config.interpreter}
              onChange={(e) => handleUpdate(index, 'interpreter', e.target.value)}
              className="w-full text-sm border border-gray-200 rounded-md px-2 py-1
                bg-gray-50 text-gray-800 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              {AVAILABLE_MODELS.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          </div>

          {/* Narrator dropdown */}
          <div className="flex-1 min-w-0">
            <label className="block text-[10px] text-gray-400 mb-0.5">Narrator</label>
            <select
              value={config.narrator}
              onChange={(e) => handleUpdate(index, 'narrator', e.target.value)}
              className="w-full text-sm border border-gray-200 rounded-md px-2 py-1
                bg-gray-50 text-gray-800 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              {AVAILABLE_MODELS.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          </div>

          {/* Remove button */}
          <button
            type="button"
            onClick={() => handleRemove(index)}
            disabled={configs.length <= 1}
            className="shrink-0 p-1 text-gray-400 hover:text-red-500
              disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="Remove configuration"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      ))}

      {/* Add button */}
      {configs.length < MAX_CONFIGS && (
        <button
          type="button"
          onClick={handleAdd}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium
            text-blue-600 bg-blue-50 rounded-lg
            hover:bg-blue-100 transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Add Configuration
        </button>
      )}
    </div>
  );
}
