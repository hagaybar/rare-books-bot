import { useState, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  createColumnHelper,
  flexRender,
  type SortingState,
  type RowSelectionState,
} from '@tanstack/react-table';
import { useIssues, useClusters, useSubmitCorrection, useAgentChat } from '../hooks/useMetadata';
import type { IssueRecord } from '../types/metadata';
import EditableCell from '../components/workbench/EditableCell';
import BatchToolbar from '../components/workbench/BatchToolbar';
import ClusterCard from '../components/workbench/ClusterCard';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FIELDS = ['date', 'place', 'publisher', 'agent'] as const;
type FieldTab = (typeof FIELDS)[number];

const FIELD_LABELS: Record<FieldTab, string> = {
  date: 'Date',
  place: 'Place',
  publisher: 'Publisher',
  agent: 'Agent',
};

type ViewMode = 'records' | 'clusters';

const PAGE_SIZE = 50;

const PRIMO_BASE = 'https://primo.nli.org.il/permalink/972NNL_INST/';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function confidenceColor(c: number): string {
  if (c >= 0.95) return 'bg-green-500';
  if (c >= 0.8) return 'bg-yellow-500';
  if (c >= 0.5) return 'bg-orange-500';
  return 'bg-red-500';
}

function confidenceTextColor(c: number): string {
  if (c >= 0.95) return 'text-green-700';
  if (c >= 0.8) return 'text-yellow-700';
  if (c >= 0.5) return 'text-orange-700';
  return 'text-red-700';
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function Workbench() {
  const [searchParams, setSearchParams] = useSearchParams();

  // --- Field tab from URL ---
  const fieldParam = searchParams.get('field');
  const activeField: FieldTab = FIELDS.includes(fieldParam as FieldTab)
    ? (fieldParam as FieldTab)
    : 'place';

  const setActiveField = useCallback(
    (f: FieldTab) => {
      setSearchParams({ field: f });
    },
    [setSearchParams]
  );

  // --- View toggle ---
  const [viewMode, setViewMode] = useState<ViewMode>('records');

  // --- Filters ---
  const [maxConfidence, setMaxConfidence] = useState(0.8);
  const [methodFilter, setMethodFilter] = useState('');

  const resetFilters = useCallback(() => {
    setMaxConfidence(0.8);
    setMethodFilter('');
  }, []);

  // --- Data fetching ---
  const {
    data: issuesData,
    isLoading: issuesLoading,
    isError: issuesError,
    error: issuesErrorObj,
  } = useIssues(activeField, maxConfidence, 500, 0);

  const {
    data: clustersData,
    isLoading: clustersLoading,
  } = useClusters(activeField);

  // --- Mutations ---
  const correctionMutation = useSubmitCorrection();
  const agentChatMutation = useAgentChat();

  // --- Filter issues by method ---
  const filteredIssues = useMemo(() => {
    if (!issuesData?.items) return [];
    if (!methodFilter) return issuesData.items;
    return issuesData.items.filter((r) => r.method === methodFilter);
  }, [issuesData, methodFilter]);

  // --- Unique methods for dropdown ---
  const uniqueMethods = useMemo(() => {
    if (!issuesData?.items) return [];
    const methods = new Set(issuesData.items.map((r) => r.method));
    return Array.from(methods).sort();
  }, [issuesData]);

  // --- Table state ---
  const [sorting, setSorting] = useState<SortingState>([]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  // --- Column definitions ---
  const columnHelper = createColumnHelper<IssueRecord>();

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: 'select',
        header: ({ table }) => (
          <input
            type="checkbox"
            checked={table.getIsAllPageRowsSelected()}
            onChange={table.getToggleAllPageRowsSelectedHandler()}
            className="rounded border-gray-300"
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            className="rounded border-gray-300"
          />
        ),
        size: 40,
      }),
      columnHelper.accessor('mms_id', {
        header: 'MMS ID',
        cell: (info) => (
          <span className="font-mono text-xs text-gray-900">
            {info.getValue()}
          </span>
        ),
        size: 140,
      }),
      columnHelper.accessor('raw_value', {
        header: 'Raw Value',
        cell: (info) => (
          <span className="text-sm text-gray-900">{info.getValue()}</span>
        ),
      }),
      columnHelper.accessor('norm_value', {
        header: 'Normalized',
        cell: (info) => (
          <EditableCell
            value={info.getValue()}
            onSave={(newValue) => {
              correctionMutation.mutate({
                field: activeField,
                rawValue: info.row.original.raw_value,
                canonicalValue: newValue,
              });
            }}
            isSaving={correctionMutation.isPending}
          />
        ),
      }),
      columnHelper.accessor('confidence', {
        header: 'Confidence',
        cell: (info) => {
          const c = info.getValue();
          return (
            <div className="flex items-center gap-2">
              <span
                className={`inline-block w-2.5 h-2.5 rounded-full ${confidenceColor(c)}`}
                title={`Confidence: ${c}`}
              />
              <span className={`text-sm font-medium ${confidenceTextColor(c)}`}>
                {c.toFixed(2)}
              </span>
            </div>
          );
        },
        size: 120,
      }),
      columnHelper.accessor('method', {
        header: 'Method',
        cell: (info) => (
          <span className="text-xs font-medium bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">
            {info.getValue()}
          </span>
        ),
        size: 130,
      }),
      columnHelper.display({
        id: 'primo_link',
        header: 'Primo',
        cell: ({ row }) => (
          <a
            href={`${PRIMO_BASE}${row.original.mms_id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-500 hover:text-indigo-700"
            title="Open in Primo"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
        ),
        size: 60,
      }),
    ],
    [columnHelper, activeField, correctionMutation]
  );

  // --- Table instance ---
  const table = useReactTable({
    data: filteredIssues,
    columns,
    state: { sorting, rowSelection },
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: {
      pagination: { pageSize: PAGE_SIZE },
    },
    enableRowSelection: true,
  });

  // --- Selected rows data ---
  const selectedRows = useMemo(
    () => table.getSelectedRowModel().rows.map((r) => r.original),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rowSelection, filteredIssues]
  );

  // --- Batch correction handler ---
  const handleBatchCorrection = useCallback(
    (canonicalValue: string, rows: IssueRecord[]) => {
      const uniqueRaws = new Set(rows.map((r) => r.raw_value));
      for (const rawValue of uniqueRaws) {
        correctionMutation.mutate({
          field: activeField,
          rawValue,
          canonicalValue,
        });
      }
      setRowSelection({});
    },
    [activeField, correctionMutation]
  );

  // --- Agent propose handler ---
  const handleProposeMappings = useCallback(
    (clusterId: string) => {
      agentChatMutation.mutate({
        field: activeField,
        message: `Propose mappings for cluster ${clusterId}`,
      });
    },
    [activeField, agentChatMutation]
  );

  // --- Pagination info ---
  const pageIndex = table.getState().pagination.pageIndex;
  const pageCount = table.getPageCount();

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-900 mb-2">
        Issues Workbench
      </h1>
      <p className="text-gray-500 mb-6">
        Browse and resolve low-confidence normalizations, duplicates, and
        clustering issues across metadata fields.
      </p>

      {/* --- Field Tabs --- */}
      <div className="flex items-center gap-1 mb-4">
        {FIELDS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setActiveField(f)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${
              activeField === f
                ? 'border-indigo-600 text-indigo-700 bg-white'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            {FIELD_LABELS[f]}
          </button>
        ))}

        {/* --- View Toggle --- */}
        <div className="ml-auto flex items-center bg-gray-100 rounded-lg p-0.5">
          <button
            type="button"
            onClick={() => setViewMode('records')}
            className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
              viewMode === 'records'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Records
          </button>
          <button
            type="button"
            onClick={() => setViewMode('clusters')}
            className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
              viewMode === 'clusters'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Clusters
          </button>
        </div>
      </div>

      {/* ================================================================= */}
      {/* RECORDS VIEW                                                       */}
      {/* ================================================================= */}
      {viewMode === 'records' && (
        <>
          {/* --- Filter Bar --- */}
          <div className="flex items-center gap-4 bg-white rounded-lg border border-gray-200 shadow-sm px-4 py-3 mb-4">
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-600 whitespace-nowrap">
                Max Confidence
              </label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={maxConfidence}
                onChange={(e) => setMaxConfidence(Number(e.target.value))}
                className="w-28"
              />
              <input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={maxConfidence}
                onChange={(e) => setMaxConfidence(Number(e.target.value))}
                className="w-16 border border-gray-300 rounded px-2 py-1 text-sm text-center"
              />
            </div>

            <div className="h-5 w-px bg-gray-200" />

            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-600">Method</label>
              <select
                value={methodFilter}
                onChange={(e) => setMethodFilter(e.target.value)}
                className="text-sm border border-gray-300 rounded-md px-3 py-1.5 text-gray-700 bg-white"
              >
                <option value="">All Methods</option>
                {uniqueMethods.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              onClick={resetFilters}
              className="ml-auto text-sm text-gray-500 hover:text-gray-700"
            >
              Reset filters
            </button>
          </div>

          {/* --- Batch Toolbar --- */}
          <div className="mb-3">
            <BatchToolbar
              selectedRows={selectedRows}
              field={activeField}
              onApplyCorrection={handleBatchCorrection}
              isApplying={correctionMutation.isPending}
            />
          </div>

          {/* --- Loading / Error --- */}
          {issuesLoading && (
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
              <div className="flex items-center justify-center h-64 text-gray-400">
                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-indigo-500" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Loading issues...
              </div>
            </div>
          )}

          {issuesError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-red-700">
              <h2 className="font-semibold mb-1">Failed to load issues</h2>
              <p className="text-sm">
                {issuesErrorObj instanceof Error ? issuesErrorObj.message : 'Unknown error'}
              </p>
            </div>
          )}

          {/* --- Data Table --- */}
          {!issuesLoading && !issuesError && (
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    {table.getHeaderGroups().map((headerGroup) => (
                      <tr key={headerGroup.id} className="border-b border-gray-200 bg-gray-50">
                        {headerGroup.headers.map((header) => (
                          <th
                            key={header.id}
                            className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none hover:bg-gray-100 transition-colors"
                            style={{ width: header.getSize() !== 150 ? header.getSize() : undefined }}
                            onClick={header.column.getToggleSortingHandler()}
                          >
                            <div className="flex items-center gap-1">
                              {header.isPlaceholder
                                ? null
                                : flexRender(header.column.columnDef.header, header.getContext())}
                              {header.column.getIsSorted() === 'asc' && (
                                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                  <path d="M5 13l5-5 5 5H5z" />
                                </svg>
                              )}
                              {header.column.getIsSorted() === 'desc' && (
                                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                  <path d="M5 7l5 5 5-5H5z" />
                                </svg>
                              )}
                            </div>
                          </th>
                        ))}
                      </tr>
                    ))}
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {table.getRowModel().rows.length === 0 ? (
                      <tr>
                        <td colSpan={columns.length} className="text-center py-12 text-gray-400">
                          No issues found with the current filters.
                        </td>
                      </tr>
                    ) : (
                      table.getRowModel().rows.map((row) => (
                        <tr
                          key={row.id}
                          className={`hover:bg-gray-50 transition-colors ${
                            row.getIsSelected() ? 'bg-indigo-50' : ''
                          }`}
                        >
                          {row.getVisibleCells().map((cell) => (
                            <td key={cell.id} className="px-4 py-2.5">
                              {flexRender(cell.column.columnDef.cell, cell.getContext())}
                            </td>
                          ))}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* --- Pagination --- */}
              <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50">
                <span className="text-sm text-gray-500">
                  {filteredIssues.length} total record{filteredIssues.length !== 1 ? 's' : ''}
                  {issuesData?.total != null && issuesData.total > filteredIssues.length && (
                    <span> (of {issuesData.total})</span>
                  )}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => table.previousPage()}
                    disabled={!table.getCanPreviousPage()}
                    className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  <span className="text-sm text-gray-600">
                    Page {pageIndex + 1} of {pageCount || 1}
                  </span>
                  <button
                    onClick={() => table.nextPage()}
                    disabled={!table.getCanNextPage()}
                    className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* ================================================================= */}
      {/* CLUSTERS VIEW                                                      */}
      {/* ================================================================= */}
      {viewMode === 'clusters' && (
        <>
          {clustersLoading && (
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
              <div className="flex items-center justify-center h-64 text-gray-400">
                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-indigo-500" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Loading clusters...
              </div>
            </div>
          )}

          {!clustersLoading && (!clustersData || clustersData.length === 0) && (
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
              <div className="flex items-center justify-center h-64 text-gray-400">
                No clusters found for the {FIELD_LABELS[activeField]} field.
              </div>
            </div>
          )}

          {!clustersLoading && clustersData && clustersData.length > 0 && (
            <div className="space-y-3">
              <p className="text-sm text-gray-500">
                {clustersData.length} cluster{clustersData.length !== 1 ? 's' : ''} found.
                Expand a cluster to view values and propose mappings.
              </p>
              {clustersData.map((cluster) => (
                <ClusterCard
                  key={cluster.cluster_id}
                  cluster={cluster}
                  onProposeMappings={handleProposeMappings}
                  isProposing={agentChatMutation.isPending}
                />
              ))}
            </div>
          )}

          {/* --- Agent response display --- */}
          {agentChatMutation.data && (
            <div className="mt-4 bg-blue-50 border border-blue-200 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-blue-800 mb-2">Agent Response</h3>
              <p className="text-sm text-blue-700 whitespace-pre-wrap">
                {agentChatMutation.data.response}
              </p>
              {agentChatMutation.data.proposals.length > 0 && (
                <div className="mt-3">
                  <h4 className="text-xs font-medium text-blue-700 uppercase tracking-wider mb-2">
                    Proposals
                  </h4>
                  <div className="space-y-1.5">
                    {agentChatMutation.data.proposals.map((p) => (
                      <div
                        key={p.raw_value}
                        className="flex items-center gap-2 text-sm text-blue-800 bg-white rounded px-3 py-1.5 border border-blue-100"
                      >
                        <span className="font-mono text-xs">{p.raw_value}</span>
                        <svg className="w-3 h-3 text-blue-400 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                        </svg>
                        <span className="font-medium">{p.canonical_value}</span>
                        <span className="text-xs text-blue-500 ml-auto">
                          {(p.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
