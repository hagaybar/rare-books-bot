/**
 * Query Debugger -- /diagnostics/query
 *
 * Developer tool for testing query interpretation, labeling results
 * (TP/FP/FN/UNK), managing gold sets, and running regression tests.
 * Replaces the Streamlit QA Tool.
 */

import { useState, useCallback, useMemo } from 'react';
import {
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  createColumnHelper,
  flexRender,
  type SortingState,
} from '@tanstack/react-table';
import * as Tabs from '@radix-ui/react-tabs';

import {
  runQuery,
  getQueryRuns,
  submitLabels,
  getLabels,
  exportGoldSet,
  runRegression,
} from '../../api/diagnostics.ts';
import type {
  QueryRunResponse,
  QueryRunCandidate,
  LabelValue,
  LabelItem,
  RegressionResponse,
  RegressionQueryResult,
  QueryRunSummary,
} from '../../types/diagnostics.ts';
import { ISSUE_TAGS } from '../../types/diagnostics.ts';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LIMIT_OPTIONS = [10, 25, 50, 100] as const;

const LABEL_CONFIG: Record<LabelValue, { label: string; color: string; activeColor: string }> = {
  TP: { label: 'TP', color: 'border-green-300 text-green-700 hover:bg-green-50', activeColor: 'bg-green-600 text-white border-green-600' },
  FP: { label: 'FP', color: 'border-red-300 text-red-700 hover:bg-red-50', activeColor: 'bg-red-600 text-white border-red-600' },
  FN: { label: 'FN', color: 'border-amber-300 text-amber-700 hover:bg-amber-50', activeColor: 'bg-amber-500 text-white border-amber-500' },
  UNK: { label: 'UNK', color: 'border-gray-300 text-gray-600 hover:bg-gray-50', activeColor: 'bg-gray-500 text-white border-gray-500' },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function truncate(str: string | null, maxLen: number): string {
  if (!str) return '\u2014';
  if (str.length <= maxLen) return str;
  return str.slice(0, maxLen) + '\u2026';
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function downloadJson(data: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Label button group for a single candidate row. */
function LabelButtons({
  currentLabel,
  onLabel,
}: {
  currentLabel: LabelValue | null;
  onLabel: (label: LabelValue) => void;
}) {
  return (
    <div className="flex gap-1">
      {(Object.keys(LABEL_CONFIG) as LabelValue[]).map((lbl) => {
        const cfg = LABEL_CONFIG[lbl];
        const isActive = currentLabel === lbl;
        return (
          <button
            key={lbl}
            type="button"
            onClick={() => { onLabel(lbl); }}
            className={`px-2 py-0.5 text-[11px] font-semibold border rounded transition-colors ${isActive ? cfg.activeColor : cfg.color}`}
          >
            {cfg.label}
          </button>
        );
      })}
    </div>
  );
}

/** Issue tag dropdown for a single candidate row. */
function IssueTagSelect({
  currentTags,
  onTagChange,
}: {
  currentTags: string[];
  onTagChange: (tags: string[]) => void;
}) {
  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const value = e.target.value;
      if (!value) return;
      if (currentTags.includes(value)) {
        onTagChange(currentTags.filter((t) => t !== value));
      } else {
        onTagChange([...currentTags, value]);
      }
      e.target.value = '';
    },
    [currentTags, onTagChange],
  );

  return (
    <div className="flex flex-col gap-1">
      <select
        onChange={handleChange}
        defaultValue=""
        className="text-[11px] border border-gray-200 rounded px-1.5 py-0.5 bg-white text-gray-700 w-full max-w-[180px]"
      >
        <option value="" disabled>
          + Issue tag
        </option>
        {ISSUE_TAGS.map((tag) => (
          <option key={tag} value={tag}>
            {currentTags.includes(tag) ? '\u2713 ' : ''}
            {tag}
          </option>
        ))}
      </select>
      {currentTags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {currentTags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] bg-amber-100 text-amber-800 rounded"
            >
              {tag}
              <button
                type="button"
                onClick={() => { onTagChange(currentTags.filter((t) => t !== tag)); }}
                className="text-amber-600 hover:text-amber-900 font-bold ml-0.5"
              >
                x
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Spinner for loading states. */
function Spinner({ size = 'md' }: { size?: 'sm' | 'md' }) {
  const sizeClass = size === 'sm' ? 'w-4 h-4' : 'w-8 h-8';
  return (
    <svg
      className={`animate-spin ${sizeClass} text-blue-600`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

/** Status badge for regression results. */
function StatusBadge({ status }: { status: string }) {
  if (status === 'pass') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
        PASS
      </span>
    );
  }
  if (status === 'fail') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
        FAIL
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
      ERROR
    </span>
  );
}

// ---------------------------------------------------------------------------
// Results Table Column Definition
// ---------------------------------------------------------------------------

const columnHelper = createColumnHelper<QueryRunCandidate>();

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function QueryDebugger() {
  const queryClient = useQueryClient();

  // --- Query input state ---
  const [queryText, setQueryText] = useState('');
  const [limit, setLimit] = useState<number>(50);

  // --- Current run ---
  const [currentRun, setCurrentRun] = useState<QueryRunResponse | null>(null);

  // --- Labels state: record_id -> { label, issue_tags } ---
  const [labelsMap, setLabelsMap] = useState<
    Record<string, { label: LabelValue; issue_tags: string[] }>
  >({});

  // --- Right panel tab ---
  const [rightTab, setRightTab] = useState('plan');

  // --- Regression results ---
  const [regressionData, setRegressionData] = useState<RegressionResponse | null>(null);

  // --- Table sorting ---
  const [sorting, setSorting] = useState<SortingState>([]);

  // --- Run query mutation ---
  const runQueryMutation = useMutation({
    mutationFn: (params: { queryText: string; limit: number }) =>
      runQuery(params.queryText, params.limit),
    onSuccess: (data) => {
      setCurrentRun(data);
      setLabelsMap({});
      setRegressionData(null);
      // Invalidate run history so it refreshes
      void queryClient.invalidateQueries({ queryKey: ['queryRuns'] });
      // Fetch existing labels for this run
      void fetchExistingLabels(data.run_id);
    },
  });

  // --- Fetch existing labels for a run ---
  const fetchExistingLabels = useCallback(async (runId: number) => {
    try {
      const resp = await getLabels(runId);
      const map: Record<string, { label: LabelValue; issue_tags: string[] }> = {};
      for (const lbl of resp.labels) {
        map[lbl.record_id] = {
          label: lbl.label as LabelValue,
          issue_tags: lbl.issue_tags,
        };
      }
      setLabelsMap(map);
    } catch {
      // Silently ignore -- labels may not exist yet
    }
  }, []);

  // --- Submit single label mutation ---
  const submitLabelMutation = useMutation({
    mutationFn: (params: { runId: number; labels: LabelItem[] }) =>
      submitLabels(params.runId, params.labels),
  });

  // --- Handle label click ---
  const handleLabel = useCallback(
    (recordId: string, label: LabelValue) => {
      if (!currentRun) return;
      const existing = labelsMap[recordId];
      const issueTags = existing?.issue_tags ?? [];
      setLabelsMap((prev) => ({
        ...prev,
        [recordId]: { label, issue_tags: issueTags },
      }));
      submitLabelMutation.mutate({
        runId: currentRun.run_id,
        labels: [{ record_id: recordId, label, issue_tags: issueTags }],
      });
    },
    [currentRun, labelsMap, submitLabelMutation],
  );

  // --- Handle issue tag change ---
  const handleIssueTags = useCallback(
    (recordId: string, tags: string[]) => {
      if (!currentRun) return;
      const existing = labelsMap[recordId];
      const label = existing?.label ?? 'UNK';
      setLabelsMap((prev) => ({
        ...prev,
        [recordId]: { label, issue_tags: tags },
      }));
      submitLabelMutation.mutate({
        runId: currentRun.run_id,
        labels: [{ record_id: recordId, label, issue_tags: tags }],
      });
    },
    [currentRun, labelsMap, submitLabelMutation],
  );

  // --- Run history query ---
  const runHistoryQuery = useQuery({
    queryKey: ['queryRuns', 20, 0],
    queryFn: () => getQueryRuns(20, 0),
    staleTime: 30_000,
  });

  // --- Load historical run ---
  const loadHistoryRunMutation = useMutation({
    mutationFn: (params: { queryText: string; limit: number }) =>
      runQuery(params.queryText, params.limit),
    onSuccess: (data) => {
      setCurrentRun(data);
      setLabelsMap({});
      setQueryText(data.query_text);
      void queryClient.invalidateQueries({ queryKey: ['queryRuns'] });
      void fetchExistingLabels(data.run_id);
    },
  });

  // --- Export gold set mutation ---
  const exportGoldMutation = useMutation({
    mutationFn: exportGoldSet,
    onSuccess: (data) => {
      downloadJson(data, 'gold_set.json');
    },
  });

  // --- Run regression mutation ---
  const regressionMutation = useMutation({
    mutationFn: runRegression,
    onSuccess: (data) => {
      setRegressionData(data);
    },
  });

  // --- Form submit ---
  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!queryText.trim()) return;
      runQueryMutation.mutate({ queryText: queryText.trim(), limit });
    },
    [queryText, limit, runQueryMutation],
  );

  // --- Table columns (must be in component to access labelsMap, handlers) ---
  const columns = useMemo(
    () => [
      columnHelper.accessor('record_id', {
        header: 'Record ID',
        size: 120,
        cell: (info) => (
          <span className="font-mono text-xs text-gray-800">
            {info.getValue()}
          </span>
        ),
      }),
      columnHelper.accessor('title', {
        header: 'Title',
        size: 300,
        cell: (info) => (
          <span className="text-sm text-gray-900" title={info.getValue() ?? ''}>
            {truncate(info.getValue(), 80)}
          </span>
        ),
      }),
      columnHelper.accessor('match_rationale', {
        header: 'Match Rationale',
        size: 250,
        cell: (info) => (
          <span className="text-xs text-gray-600">
            {truncate(info.getValue(), 100)}
          </span>
        ),
      }),
      columnHelper.display({
        id: 'label',
        header: 'Label',
        size: 180,
        cell: (info) => {
          const recordId = info.row.original.record_id;
          const current = labelsMap[recordId]?.label ?? null;
          return (
            <LabelButtons
              currentLabel={current}
              onLabel={(lbl) => { handleLabel(recordId, lbl); }}
            />
          );
        },
      }),
      columnHelper.display({
        id: 'issue_tags',
        header: 'Issues',
        size: 200,
        cell: (info) => {
          const recordId = info.row.original.record_id;
          const current = labelsMap[recordId]?.issue_tags ?? [];
          return (
            <IssueTagSelect
              currentTags={current}
              onTagChange={(tags) => { handleIssueTags(recordId, tags); }}
            />
          );
        },
      }),
    ],
    [labelsMap, handleLabel, handleIssueTags],
  );

  // --- TanStack Table instance ---
  const table = useReactTable({
    data: currentRun?.candidates ?? [],
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  // --- Regression table columns ---
  const regressionColumns = useMemo(() => {
    const regressionHelper = createColumnHelper<RegressionQueryResult>();
    return [
      regressionHelper.accessor('query_text', {
        header: 'Query',
        size: 300,
        cell: (info) => (
          <span className="text-sm text-gray-900">
            {truncate(info.getValue(), 60)}
          </span>
        ),
      }),
      regressionHelper.accessor('status', {
        header: 'Status',
        size: 80,
        cell: (info) => <StatusBadge status={info.getValue()} />,
      }),
      regressionHelper.accessor('expected_includes', {
        header: 'Expected',
        size: 80,
        cell: (info) => (
          <span className="text-xs text-gray-600">
            {String(info.getValue().length)}
          </span>
        ),
      }),
      regressionHelper.accessor('actual_includes', {
        header: 'Actual',
        size: 80,
        cell: (info) => (
          <span className="text-xs text-gray-600">
            {String(info.getValue().length)}
          </span>
        ),
      }),
      regressionHelper.accessor('missing', {
        header: 'Missing',
        size: 80,
        cell: (info) => {
          const val = info.getValue();
          return (
            <span className={`text-xs ${val.length > 0 ? 'text-red-600 font-medium' : 'text-gray-400'}`}>
              {String(val.length)}
            </span>
          );
        },
      }),
      regressionHelper.accessor('unexpected', {
        header: 'Unexpected',
        size: 80,
        cell: (info) => {
          const val = info.getValue();
          return (
            <span className={`text-xs ${val.length > 0 ? 'text-amber-600 font-medium' : 'text-gray-400'}`}>
              {String(val.length)}
            </span>
          );
        },
      }),
      regressionHelper.accessor('error', {
        header: 'Error',
        size: 200,
        cell: (info) => {
          const val = info.getValue();
          if (!val) return <span className="text-gray-400 text-xs">{'\u2014'}</span>;
          return (
            <span className="text-xs text-red-600" title={val}>
              {truncate(val, 50)}
            </span>
          );
        },
      }),
    ];
  }, []);

  const regressionTable = useReactTable({
    data: regressionData?.results ?? [],
    columns: regressionColumns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  // --- Label summary ---
  const labelSummary = useMemo(() => {
    const counts = { TP: 0, FP: 0, FN: 0, UNK: 0, unlabeled: 0 };
    const total = currentRun?.candidates.length ?? 0;
    let labeled = 0;
    for (const val of Object.values(labelsMap)) {
      const lbl = val.label as keyof typeof counts;
      if (lbl in counts) {
        counts[lbl]++;
        labeled++;
      }
    }
    counts.unlabeled = total - labeled;
    return counts;
  }, [labelsMap, currentRun]);

  // =========================================================================
  // RENDER
  // =========================================================================

  return (
    <div className="flex flex-col gap-6 p-6 max-w-[1600px] mx-auto">
      {/* Page title */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Query Debugger</h1>
        <p className="text-sm text-gray-500 mt-1">
          Test query interpretation, label results, and run regression tests.
        </p>
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* TOP: Query Input Bar                                              */}
      {/* ----------------------------------------------------------------- */}
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[300px]">
          <label htmlFor="query-input" className="block text-sm font-medium text-gray-700 mb-1">
            Query
          </label>
          <input
            id="query-input"
            type="text"
            value={queryText}
            onChange={(e) => { setQueryText(e.target.value); }}
            placeholder="e.g. books published by Oxford between 1500 and 1599"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
          />
        </div>
        <div>
          <label htmlFor="limit-select" className="block text-sm font-medium text-gray-700 mb-1">
            Limit
          </label>
          <select
            id="limit-select"
            value={limit}
            onChange={(e) => { setLimit(Number(e.target.value)); }}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500"
          >
            {LIMIT_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>
                {String(opt)}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          disabled={runQueryMutation.isPending || !queryText.trim()}
          className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:bg-blue-300 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          {runQueryMutation.isPending && <Spinner size="sm" />}
          Run Query
        </button>
      </form>

      {/* Error state */}
      {runQueryMutation.isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-800">
            <span className="font-medium">Error:</span>{' '}
            {runQueryMutation.error instanceof Error
              ? runQueryMutation.error.message
              : 'Query execution failed'}
          </p>
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* MAIN AREA: Two-column layout                                      */}
      {/* ----------------------------------------------------------------- */}
      {!currentRun && !runQueryMutation.isPending ? (
        /* Empty state */
        <div className="flex items-center justify-center min-h-[40vh]">
          <div className="text-center max-w-md">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-blue-50 flex items-center justify-center">
              <svg className="w-8 h-8 text-blue-500" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
            </div>
            <h2 className="text-lg font-medium text-gray-900 mb-2">
              Enter a query to start debugging
            </h2>
            <p className="text-sm text-gray-500">
              Type a natural language query above and click &quot;Run Query&quot; to see the
              generated plan, SQL, and matching candidates. You can label results as
              TP/FP/FN/UNK and tag issues.
            </p>
          </div>
        </div>
      ) : runQueryMutation.isPending ? (
        /* Loading state */
        <div className="flex items-center justify-center min-h-[40vh]">
          <div className="flex flex-col items-center gap-3">
            <Spinner />
            <p className="text-sm text-gray-500">Executing query...</p>
          </div>
        </div>
      ) : currentRun ? (
        /* Results area */
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* ============================================================= */}
          {/* LEFT PANEL: Results & Labels (3/5 on desktop)                  */}
          {/* ============================================================= */}
          <div className="lg:col-span-3 flex flex-col gap-4">
            {/* Results header */}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-3">
                <h2 className="text-lg font-medium text-gray-900">
                  Results
                </h2>
                <span className="text-sm text-gray-500">
                  {String(currentRun.total_count)} candidate{currentRun.total_count !== 1 ? 's' : ''}
                  {' \u00b7 '}
                  {formatMs(currentRun.execution_time_ms)}
                </span>
              </div>
              {/* Label summary badges */}
              <div className="flex items-center gap-2 text-[11px]">
                {currentRun.candidates.length > 0 && (
                  <>
                    <span className="text-green-700 font-medium">
                      TP: {String(labelSummary.TP)}
                    </span>
                    <span className="text-red-700 font-medium">
                      FP: {String(labelSummary.FP)}
                    </span>
                    <span className="text-amber-700 font-medium">
                      FN: {String(labelSummary.FN)}
                    </span>
                    <span className="text-gray-500">
                      UNK: {String(labelSummary.UNK)}
                    </span>
                    <span className="text-gray-400">
                      Unlabeled: {String(labelSummary.unlabeled)}
                    </span>
                  </>
                )}
              </div>
            </div>

            {/* Results table */}
            {currentRun.candidates.length === 0 ? (
              <div className="text-center py-12 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-500">No candidates matched this query.</p>
              </div>
            ) : (
              <div className="overflow-x-auto border border-gray-200 rounded-lg">
                <table className="w-full">
                  <thead>
                    {table.getHeaderGroups().map((headerGroup) => (
                      <tr key={headerGroup.id} className="bg-gray-50 border-b border-gray-200">
                        {headerGroup.headers.map((header) => (
                          <th
                            key={header.id}
                            className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none hover:bg-gray-100"
                            style={{ width: header.getSize() }}
                            onClick={header.column.getToggleSortingHandler()}
                          >
                            <div className="flex items-center gap-1">
                              {header.isPlaceholder
                                ? null
                                : flexRender(header.column.columnDef.header, header.getContext())}
                              {header.column.getIsSorted() === 'asc' && ' \u2191'}
                              {header.column.getIsSorted() === 'desc' && ' \u2193'}
                            </div>
                          </th>
                        ))}
                      </tr>
                    ))}
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {table.getRowModel().rows.map((row) => (
                      <tr key={row.id} className="hover:bg-gray-50 transition-colors">
                        {row.getVisibleCells().map((cell) => (
                          <td key={cell.id} className="px-3 py-2.5 align-top">
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* ============================================================= */}
          {/* RIGHT PANEL: Plan & SQL (2/5 on desktop)                      */}
          {/* ============================================================= */}
          <div className="lg:col-span-2">
            <Tabs.Root value={rightTab} onValueChange={setRightTab}>
              <Tabs.List className="flex border-b border-gray-200 mb-4">
                <Tabs.Trigger
                  value="plan"
                  className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent data-[state=active]:border-blue-600 data-[state=active]:text-blue-600 transition-colors"
                >
                  Query Plan
                </Tabs.Trigger>
                <Tabs.Trigger
                  value="sql"
                  className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent data-[state=active]:border-blue-600 data-[state=active]:text-blue-600 transition-colors"
                >
                  SQL
                </Tabs.Trigger>
                <Tabs.Trigger
                  value="history"
                  className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent data-[state=active]:border-blue-600 data-[state=active]:text-blue-600 transition-colors"
                >
                  Run History
                </Tabs.Trigger>
              </Tabs.List>

              {/* Tab: Query Plan */}
              <Tabs.Content value="plan" className="outline-none">
                <div className="bg-gray-50 rounded-lg border border-gray-200 p-4 max-h-[600px] overflow-auto">
                  <pre className="text-xs font-mono text-gray-800 whitespace-pre-wrap break-words">
                    {JSON.stringify(currentRun.plan, null, 2)}
                  </pre>
                </div>
              </Tabs.Content>

              {/* Tab: SQL */}
              <Tabs.Content value="sql" className="outline-none">
                <div className="bg-gray-900 rounded-lg border border-gray-700 p-4 max-h-[600px] overflow-auto">
                  <pre className="text-xs font-mono text-green-400 whitespace-pre-wrap break-words">
                    {currentRun.sql || '-- No SQL generated --'}
                  </pre>
                </div>
              </Tabs.Content>

              {/* Tab: Run History */}
              <Tabs.Content value="history" className="outline-none">
                <RunHistoryPanel
                  data={runHistoryQuery.data}
                  isLoading={runHistoryQuery.isLoading}
                  onLoadRun={(run) => {
                    setQueryText(run.query_text);
                    loadHistoryRunMutation.mutate({
                      queryText: run.query_text,
                      limit,
                    });
                  }}
                  isLoadingRun={loadHistoryRunMutation.isPending}
                />
              </Tabs.Content>
            </Tabs.Root>
          </div>
        </div>
      ) : null}

      {/* ----------------------------------------------------------------- */}
      {/* BOTTOM: Gold Set & Regression                                     */}
      {/* ----------------------------------------------------------------- */}
      <div className="border-t border-gray-200 pt-6">
        <div className="flex flex-wrap items-start gap-4">
          {/* Export Gold Set */}
          <button
            type="button"
            onClick={() => { exportGoldMutation.mutate(); }}
            disabled={exportGoldMutation.isPending}
            className="px-4 py-2 text-sm font-medium border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors flex items-center gap-2"
          >
            {exportGoldMutation.isPending && <Spinner size="sm" />}
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
            Export Gold Set
          </button>

          {/* Run Regression */}
          <button
            type="button"
            onClick={() => { regressionMutation.mutate(); }}
            disabled={regressionMutation.isPending}
            className="px-4 py-2 text-sm font-medium bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-purple-300 transition-colors flex items-center gap-2"
          >
            {regressionMutation.isPending && <Spinner size="sm" />}
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z" />
            </svg>
            Run Regression
          </button>

          {/* Error messages */}
          {exportGoldMutation.isError && (
            <span className="text-sm text-red-600">
              Export failed: {exportGoldMutation.error instanceof Error ? exportGoldMutation.error.message : 'Unknown error'}
            </span>
          )}
          {regressionMutation.isError && (
            <span className="text-sm text-red-600">
              Regression failed: {regressionMutation.error instanceof Error ? regressionMutation.error.message : 'Unknown error'}
            </span>
          )}
        </div>

        {/* Regression summary */}
        {regressionData && (
          <div className="mt-4 space-y-4">
            {/* Summary bar */}
            <div className="flex items-center gap-4 p-3 bg-gray-50 rounded-lg border border-gray-200">
              <span className="text-sm font-medium text-gray-700">
                Regression Results:
              </span>
              <span className="text-sm">
                <span className="font-medium text-gray-900">{String(regressionData.total_queries)}</span>{' '}
                queries
              </span>
              <span className="text-sm text-green-700 font-medium">
                {String(regressionData.passed)} passed
              </span>
              <span className="text-sm text-red-700 font-medium">
                {String(regressionData.failed)} failed
              </span>
              {regressionData.total_queries > 0 && (
                <span className={`text-sm font-bold ${regressionData.failed === 0 ? 'text-green-700' : 'text-red-700'}`}>
                  ({Math.round((regressionData.passed / regressionData.total_queries) * 100)}% pass rate)
                </span>
              )}
            </div>

            {/* Regression results table */}
            {regressionData.results.length > 0 && (
              <div className="overflow-x-auto border border-gray-200 rounded-lg">
                <table className="w-full">
                  <thead>
                    {regressionTable.getHeaderGroups().map((headerGroup) => (
                      <tr key={headerGroup.id} className="bg-gray-50 border-b border-gray-200">
                        {headerGroup.headers.map((header) => (
                          <th
                            key={header.id}
                            className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                            style={{ width: header.getSize() }}
                          >
                            {header.isPlaceholder
                              ? null
                              : flexRender(header.column.columnDef.header, header.getContext())}
                          </th>
                        ))}
                      </tr>
                    ))}
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {regressionTable.getRowModel().rows.map((row) => (
                      <tr key={row.id} className="hover:bg-gray-50">
                        {row.getVisibleCells().map((cell) => (
                          <td key={cell.id} className="px-3 py-2 align-top">
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {regressionData.total_queries === 0 && (
              <p className="text-sm text-gray-500 py-4 text-center">
                No gold set queries found. Label some query results first, then export a gold set.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Run History Panel (separated for readability)
// ---------------------------------------------------------------------------

function RunHistoryPanel({
  data,
  isLoading,
  onLoadRun,
  isLoadingRun,
}: {
  data: { total: number; items: QueryRunSummary[] } | undefined;
  isLoading: boolean;
  onLoadRun: (run: QueryRunSummary) => void;
  isLoadingRun: boolean;
}) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Spinner size="sm" />
        <span className="text-sm text-gray-500 ml-2">Loading history...</span>
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-gray-500">No query runs yet.</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <p className="text-xs text-gray-400 mb-2">
        {String(data.total)} total runs. Showing latest {String(data.items.length)}.
      </p>
      {data.items.map((run) => (
        <button
          key={run.run_id}
          type="button"
          onClick={() => { onLoadRun(run); }}
          disabled={isLoadingRun}
          className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-blue-50 border border-transparent hover:border-blue-200 transition-colors disabled:opacity-50 group"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-900 group-hover:text-blue-700 truncate max-w-[70%]">
              {run.query_text}
            </span>
            <span className="text-xs text-gray-400 shrink-0 ml-2">
              {String(run.candidate_count)} results
            </span>
          </div>
          <span className="text-[11px] text-gray-400 mt-0.5 block">
            {formatTimestamp(run.created_at)}
          </span>
        </button>
      ))}
    </div>
  );
}
