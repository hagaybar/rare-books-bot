/**
 * Compare mode -- side-by-side model comparison for admin/full users.
 *
 * Lets the user select up to 3 model configurations (interpreter + narrator),
 * enter a query, and see results rendered side-by-side with metrics and ratings.
 */

import { useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import type { ModelPair, ComparisonResult, CompareResponse } from '../types/chat';
import { AVAILABLE_MODELS } from '../types/chat';
import { authenticatedFetch } from '../api/auth';
import ModelSelector from './ModelSelector';

// ---------------------------------------------------------------------------
// Star Rating sub-component
// ---------------------------------------------------------------------------

function StarRating({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          onClick={() => onChange(star)}
          className="p-0.5 transition-colors"
          title={`${star} star${star > 1 ? 's' : ''}`}
        >
          <svg
            className={`w-5 h-5 ${
              star <= value ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300'
            }`}
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.562.562 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.562.562 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z"
            />
          </svg>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Result card sub-component
// ---------------------------------------------------------------------------

function ResultCard({
  result,
  rating,
  onRate,
}: {
  result: ComparisonResult;
  rating: number;
  onRate: (v: number) => void;
}) {
  const { config, response, metrics, error } = result;

  return (
    <div className="flex flex-col bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      {/* Header with model names */}
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-2.5">
        <div className="flex items-center gap-2 text-xs">
          <span className="font-semibold text-gray-700">I:</span>
          <span className="text-gray-600">{config.interpreter}</span>
          <span className="text-gray-300">|</span>
          <span className="font-semibold text-gray-700">N:</span>
          <span className="text-gray-600">{config.narrator}</span>
        </div>
      </div>

      {/* Metrics bar */}
      <div className="flex items-center gap-4 px-4 py-2 border-b border-gray-100 text-xs text-gray-500">
        <span title="Latency">
          <svg className="w-3.5 h-3.5 inline mr-1 text-gray-400" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {(metrics.latency_ms / 1000).toFixed(1)}s
        </span>
        <span title="Cost">
          ${metrics.cost_usd.toFixed(4)}
        </span>
        <span title="Tokens (in/out)">
          {metrics.tokens.input.toLocaleString()} / {metrics.tokens.output.toLocaleString()} tok
        </span>
      </div>

      {/* Content */}
      <div className="flex-1 px-4 py-3 overflow-y-auto max-h-96">
        {error ? (
          <div className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
            Error: {error}
          </div>
        ) : response ? (
          <div className="prose prose-sm max-w-none text-gray-800 chat-markdown-content">
            <ReactMarkdown>{response.message}</ReactMarkdown>
          </div>
        ) : (
          <p className="text-sm text-gray-400 italic">No response</p>
        )}
      </div>

      {/* Rating */}
      <div className="border-t border-gray-100 px-4 py-2.5 flex items-center justify-between">
        <span className="text-xs text-gray-400">Rate this response</span>
        <StarRating value={rating} onChange={onRate} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CompareMode component
// ---------------------------------------------------------------------------

export default function CompareMode() {
  const [configs, setConfigs] = useState<ModelPair[]>([
    { interpreter: AVAILABLE_MODELS[0], narrator: AVAILABLE_MODELS[0] },
  ]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<ComparisonResult[]>([]);
  const [ratings, setRatings] = useState<Record<number, number>>({});

  const inputRef = useRef<HTMLTextAreaElement>(null);

  const handleCompare = async () => {
    const trimmed = query.trim();
    if (!trimmed || loading || configs.length === 0) return;

    setError(null);
    setLoading(true);
    setResults([]);
    setRatings({});

    try {
      const res = await authenticatedFetch('/chat/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: trimmed,
          configs,
          token_saving: true,
        }),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Compare API error ${res.status}: ${text}`);
      }

      const data = (await res.json()) as CompareResponse;
      setResults(data.comparisons);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleCompare();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setQuery(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <h2 className="text-lg font-semibold text-gray-900">Model Comparison</h2>
        <p className="text-xs text-gray-500 mt-0.5">
          Compare model configurations side-by-side on the same query
        </p>
      </div>

      {/* Configuration + query section */}
      <div className="border-b border-gray-200 bg-white px-6 py-4 space-y-4">
        <ModelSelector configs={configs} onChange={setConfigs} />

        {/* Query input */}
        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">
            Query
          </label>
          <div className="flex items-end gap-2">
            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                value={query}
                onChange={handleInput}
                onKeyDown={handleKeyDown}
                placeholder="Enter a query to compare across model configs..."
                rows={1}
                disabled={loading}
                className="w-full resize-none rounded-xl border border-gray-300 bg-gray-50 px-4 py-2.5
                  text-sm text-gray-900 placeholder:text-gray-400
                  focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-shadow"
                style={{ maxHeight: '120px' }}
              />
            </div>
            <button
              type="button"
              onClick={handleCompare}
              disabled={loading || !query.trim() || configs.length === 0}
              className="shrink-0 px-4 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-medium
                flex items-center gap-2
                hover:bg-blue-700 active:bg-blue-800
                disabled:bg-gray-300 disabled:cursor-not-allowed
                transition-colors shadow-sm cursor-pointer"
            >
              {loading ? (
                <>
                  <div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
                  Comparing...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
                  </svg>
                  Compare
                </>
              )}
            </button>
          </div>
          <p className="text-[10px] text-gray-400 mt-1">
            Press Enter to compare, Shift+Enter for new line
          </p>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="border-b border-red-200 bg-red-50 px-6 py-2">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-red-500 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
            <span className="text-sm text-red-700 flex-1">{error}</span>
            <button
              type="button"
              onClick={() => setError(null)}
              className="text-red-400 hover:text-red-600 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Results area */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading && results.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-3" />
              <p className="text-sm text-gray-500">Running comparison across {configs.length} configuration{configs.length > 1 ? 's' : ''}...</p>
              <p className="text-xs text-gray-400 mt-1">This may take a minute</p>
            </div>
          </div>
        )}

        {results.length > 0 && (
          <div
            className={`grid gap-4 ${
              results.length === 1
                ? 'grid-cols-1 max-w-2xl mx-auto'
                : results.length === 2
                  ? 'grid-cols-1 lg:grid-cols-2'
                  : 'grid-cols-1 lg:grid-cols-3'
            }`}
          >
            {results.map((result, index) => (
              <ResultCard
                key={index}
                result={result}
                rating={ratings[index] ?? 0}
                onRate={(v) => setRatings((prev) => ({ ...prev, [index]: v }))}
              />
            ))}
          </div>
        )}

        {!loading && results.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-sm">
              <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-gray-100 flex items-center justify-center">
                <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
                </svg>
              </div>
              <p className="text-sm text-gray-500">
                Select model configurations and enter a query to compare responses side-by-side.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
