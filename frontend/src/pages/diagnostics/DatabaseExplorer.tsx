/**
 * Database Explorer -- /diagnostics/database
 *
 * Browse and search all bibliographic database tables.
 * Left sidebar shows table list with row counts; main area shows
 * paginated, searchable data for the selected table.
 */

import { useState, useCallback, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  useReactTable,
  getCoreRowModel,
  createColumnHelper,
  flexRender,
  type ColumnDef,
} from '@tanstack/react-table';

import { getTables, getTableRows } from '../../api/diagnostics.ts';
import type { TableInfo, ColumnInfo } from '../../types/diagnostics.ts';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 50;

// Tables that have an mms_id column (for MMS ID quick search)
const MMS_ID_TABLES = [
  'records',
  'imprints',
  'titles',
  'subjects',
  'agents',
  'languages',
  'notes',
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatNumber(n: number): string {
  return n.toLocaleString('en-US');
}

function truncateCell(value: unknown, maxLen: number = 120): string {
  if (value === null || value === undefined) return '\u2014';
  const str = String(value);
  if (str.length <= maxLen) return str;
  return str.slice(0, maxLen) + '\u2026';
}

// ---------------------------------------------------------------------------
// Table List Sidebar
// ---------------------------------------------------------------------------

function TableListSidebar({
  tables,
  activeTable,
  onSelect,
}: {
  tables: TableInfo[];
  activeTable: string | null;
  onSelect: (name: string) => void;
}) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
          Tables
        </h2>
      </div>
      <nav className="flex-1 overflow-y-auto py-1">
        {tables.map((table) => {
          const isActive = table.name === activeTable;
          return (
            <button
              key={table.name}
              onClick={() => onSelect(table.name)}
              className={`w-full text-left px-4 py-2.5 flex items-center justify-between transition-colors cursor-pointer ${
                isActive
                  ? 'bg-blue-50 text-blue-700 border-r-2 border-blue-600'
                  : 'text-gray-700 hover:bg-gray-50'
              }`}
            >
              <span className={`text-sm ${isActive ? 'font-semibold' : 'font-medium'}`}>
                {table.name}
              </span>
              <span
                className={`text-xs px-2 py-0.5 rounded-full ${
                  isActive
                    ? 'bg-blue-100 text-blue-700'
                    : 'bg-gray-100 text-gray-500'
                }`}
              >
                {formatNumber(table.row_count)}
              </span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Column Header Badge
// ---------------------------------------------------------------------------

function ColumnTypeBadge({ type }: { type: string }) {
  return (
    <span className="ml-1 text-[10px] font-normal text-gray-400 uppercase">
      {type}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Search Bar
// ---------------------------------------------------------------------------

function SearchBar({
  search,
  onSearchChange,
  mmsSearch,
  onMmsSearchChange,
  onMmsSearchSubmit,
  showMmsSearch,
}: {
  search: string;
  onSearchChange: (value: string) => void;
  mmsSearch: string;
  onMmsSearchChange: (value: string) => void;
  onMmsSearchSubmit: () => void;
  showMmsSearch: boolean;
}) {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      {/* General text search */}
      <div className="relative flex-1 min-w-[200px]">
        <svg
          className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z"
          />
        </svg>
        <input
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search all text columns..."
          className="w-full pl-10 pr-4 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
        {search && (
          <button
            onClick={() => onSearchChange('')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      {/* MMS ID quick search */}
      {showMmsSearch && (
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={mmsSearch}
            onChange={(e) => onMmsSearchChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onMmsSearchSubmit();
            }}
            placeholder="MMS ID..."
            className="w-40 px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 font-mono"
          />
          <button
            onClick={onMmsSearchSubmit}
            disabled={!mmsSearch.trim()}
            className="px-3 py-2 text-sm bg-amber-500 text-white rounded-lg hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Find
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pagination Controls
// ---------------------------------------------------------------------------

function PaginationControls({
  offset,
  limit,
  total,
  onPrev,
  onNext,
}: {
  offset: number;
  limit: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + limit, total);
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const hasPrev = offset > 0;
  const hasNext = offset + limit < total;

  return (
    <div className="flex items-center justify-between py-3 px-1">
      <span className="text-sm text-gray-600">
        Showing {formatNumber(start)}&ndash;{formatNumber(end)} of{' '}
        {formatNumber(total)}
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={onPrev}
          disabled={!hasPrev}
          className="px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Previous
        </button>
        <span className="text-sm text-gray-500">
          Page {currentPage} of {totalPages}
        </span>
        <button
          onClick={onNext}
          disabled={!hasNext}
          className="px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Next
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Data Table
// ---------------------------------------------------------------------------

const columnHelper = createColumnHelper<Record<string, unknown>>();

function DataTable({
  columns,
  rows,
  isLoading,
}: {
  columns: ColumnInfo[];
  rows: Record<string, unknown>[];
  isLoading: boolean;
}) {
  const tableColumns = useMemo<ColumnDef<Record<string, unknown>, unknown>[]>(
    () =>
      columns.map((col) =>
        columnHelper.accessor((row) => row[col.name], {
          id: col.name,
          header: () => (
            <span className="flex items-center gap-1 whitespace-nowrap">
              <span>{col.name}</span>
              <ColumnTypeBadge type={col.type} />
            </span>
          ),
          cell: (info) => (
            <span className="font-mono text-xs" title={String(info.getValue() ?? '')}>
              {truncateCell(info.getValue())}
            </span>
          ),
        }),
      ),
    [columns],
  );

  const table = useReactTable({
    data: rows,
    columns: tableColumns,
    getCoreRowModel: getCoreRowModel(),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="flex items-center gap-3 text-gray-500">
          <svg className="w-5 h-5 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-sm">Loading rows...</span>
        </div>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-gray-500">No rows found.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto border border-gray-200 rounded-lg">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th
                  key={header.id}
                  className="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider whitespace-nowrap"
                >
                  {header.isPlaceholder
                    ? null
                    : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody className="bg-white divide-y divide-gray-100">
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className="hover:bg-gray-50 transition-colors">
              {row.getVisibleCells().map((cell) => (
                <td
                  key={cell.id}
                  className="px-3 py-2 text-sm text-gray-800 max-w-xs truncate"
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty State
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div className="flex items-center justify-center h-full min-h-[400px]">
      <div className="text-center">
        <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-gray-100 flex items-center justify-center">
          <svg
            className="w-7 h-7 text-gray-400"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25a2.25 2.25 0 0 1-2.25-2.25v-2.25Z"
            />
          </svg>
        </div>
        <p className="text-sm text-gray-500">
          Select a table from the sidebar to browse its contents.
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function DatabaseExplorer() {
  const [activeTable, setActiveTable] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [mmsSearch, setMmsSearch] = useState('');

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setOffset(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Fetch table list
  const tablesQuery = useQuery({
    queryKey: ['diagnostics', 'tables'],
    queryFn: getTables,
    staleTime: 60_000,
  });

  // Auto-select first table when data loads
  useEffect(() => {
    if (tablesQuery.data?.tables && tablesQuery.data.tables.length > 0 && !activeTable) {
      setActiveTable(tablesQuery.data.tables[0].name);
    }
  }, [tablesQuery.data, activeTable]);

  // Find the active table info
  const activeTableInfo = useMemo(
    () => tablesQuery.data?.tables.find((t) => t.name === activeTable) ?? null,
    [tablesQuery.data, activeTable],
  );

  // Fetch rows for active table
  const rowsQuery = useQuery({
    queryKey: ['diagnostics', 'tableRows', activeTable, offset, debouncedSearch],
    queryFn: () => getTableRows(activeTable!, PAGE_SIZE, offset, debouncedSearch),
    enabled: !!activeTable,
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });

  // Handlers
  const handleSelectTable = useCallback((name: string) => {
    setActiveTable(name);
    setOffset(0);
    setSearch('');
    setDebouncedSearch('');
    setMmsSearch('');
  }, []);

  const handlePrev = useCallback(() => {
    setOffset((prev) => Math.max(0, prev - PAGE_SIZE));
  }, []);

  const handleNext = useCallback(() => {
    setOffset((prev) => prev + PAGE_SIZE);
  }, []);

  const handleSearchChange = useCallback((value: string) => {
    setSearch(value);
  }, []);

  const handleMmsSearchSubmit = useCallback(() => {
    const trimmed = mmsSearch.trim();
    if (!trimmed) return;
    setSearch(trimmed);
    setOffset(0);
  }, [mmsSearch]);

  // Determine whether to show MMS ID search
  const showMmsSearch = activeTable ? MMS_ID_TABLES.includes(activeTable) : false;

  // Loading state for tables
  if (tablesQuery.isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex items-center gap-3 text-gray-500">
          <svg className="w-5 h-5 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-sm">Loading database schema...</span>
        </div>
      </div>
    );
  }

  // Error state for tables
  if (tablesQuery.isError) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-red-100 flex items-center justify-center">
            <svg className="w-7 h-7 text-red-500" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
          </div>
          <p className="text-sm text-red-600 mb-2 font-medium">Failed to load tables</p>
          <p className="text-xs text-gray-500">
            {tablesQuery.error instanceof Error
              ? tablesQuery.error.message
              : 'Unknown error'}
          </p>
        </div>
      </div>
    );
  }

  const tables = tablesQuery.data?.tables ?? [];

  return (
    <div className="flex h-[calc(100vh-8rem)] border border-gray-200 rounded-lg overflow-hidden bg-white">
      {/* Left sidebar -- table list */}
      <aside className="w-1/4 min-w-[200px] max-w-[280px] border-r border-gray-200 bg-gray-50/50 overflow-hidden flex flex-col">
        <TableListSidebar
          tables={tables}
          activeTable={activeTable}
          onSelect={handleSelectTable}
        />
      </aside>

      {/* Main area -- data browser */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {!activeTable || !activeTableInfo ? (
          <EmptyState />
        ) : (
          <>
            {/* Header */}
            <div className="px-5 py-4 border-b border-gray-200 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">
                    {activeTableInfo.name}
                  </h2>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {activeTableInfo.columns.length} columns &middot;{' '}
                    {formatNumber(activeTableInfo.row_count)} rows
                  </p>
                </div>
                {rowsQuery.isFetching && (
                  <svg className="w-4 h-4 animate-spin text-blue-500" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                )}
              </div>
              <SearchBar
                search={search}
                onSearchChange={handleSearchChange}
                mmsSearch={mmsSearch}
                onMmsSearchChange={setMmsSearch}
                onMmsSearchSubmit={handleMmsSearchSubmit}
                showMmsSearch={showMmsSearch}
              />
            </div>

            {/* Table content */}
            <div className="flex-1 overflow-auto px-5 py-3">
              <DataTable
                columns={activeTableInfo.columns}
                rows={rowsQuery.data?.rows ?? []}
                isLoading={rowsQuery.isLoading}
              />
            </div>

            {/* Pagination */}
            <div className="px-5 border-t border-gray-200">
              <PaginationControls
                offset={offset}
                limit={PAGE_SIZE}
                total={rowsQuery.data?.total ?? 0}
                onPrev={handlePrev}
                onNext={handleNext}
              />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
