import { useState, useMemo, useCallback } from 'react';
import { useCorrectionHistory } from '../../hooks/useMetadata';
import type { CorrectionEntry } from '../../types/metadata';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 25;

const FIELD_OPTIONS = ['all', 'place', 'date', 'publisher', 'agent'] as const;
const SOURCE_OPTIONS = ['all', 'human', 'agent'] as const;

const FIELD_BADGE_COLORS: Record<string, string> = {
  place: 'bg-emerald-100 text-emerald-800',
  date: 'bg-amber-100 text-amber-800',
  publisher: 'bg-sky-100 text-sky-800',
  agent: 'bg-violet-100 text-violet-800',
};

const SOURCE_BADGE_COLORS: Record<string, string> = {
  human: 'bg-blue-100 text-blue-800',
  agent: 'bg-purple-100 text-purple-800',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${String(diffMins)} min ago`;
  if (diffHours < 24) return `${String(diffHours)} hour${diffHours === 1 ? '' : 's'} ago`;
  if (diffDays < 7) return `${String(diffDays)} day${diffDays === 1 ? '' : 's'} ago`;

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function correctionsToCsv(entries: CorrectionEntry[]): string {
  const header = 'timestamp,field,raw_value,canonical_value,evidence,source,action';
  const rows = entries.map((e) => {
    const escape = (v: string) => `"${v.replace(/"/g, '""')}"`;
    return [
      escape(e.timestamp),
      escape(e.field),
      escape(e.raw_value),
      escape(e.canonical_value),
      escape(e.evidence),
      escape(e.source),
      escape(e.action),
    ].join(',');
  });
  return [header, ...rows].join('\n');
}

function downloadFile(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
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

function SummaryBar({ entries, total }: { entries: CorrectionEntry[]; total: number }) {
  const { bySource, byField } = useMemo(() => {
    const sourceMap: Record<string, number> = {};
    const fieldMap: Record<string, number> = {};
    for (const e of entries) {
      sourceMap[e.source] = (sourceMap[e.source] ?? 0) + 1;
      fieldMap[e.field] = (fieldMap[e.field] ?? 0) + 1;
    }
    return { bySource: sourceMap, byField: fieldMap };
  }, [entries]);

  const sourceText = Object.entries(bySource)
    .map(([s, c]) => `${String(c)} ${s}`)
    .join(', ');

  const fieldText = Object.entries(byField)
    .map(([f, c]) => `${String(c)} ${f}`)
    .join(', ');

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
      <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
        <p className="text-sm font-medium text-gray-500 uppercase tracking-wide">
          Total Corrections
        </p>
        <p className="mt-1 text-2xl font-semibold text-gray-900">
          {total.toLocaleString()}
        </p>
      </div>
      <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
        <p className="text-sm font-medium text-gray-500 uppercase tracking-wide">
          By Source
        </p>
        <p className="mt-1 text-sm text-gray-700">
          {sourceText || 'No data'}
        </p>
      </div>
      <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
        <p className="text-sm font-medium text-gray-500 uppercase tracking-wide">
          By Field
        </p>
        <p className="mt-1 text-sm text-gray-700">
          {fieldText || 'No data'}
        </p>
      </div>
    </div>
  );
}

function FilterBar({
  fieldFilter,
  sourceFilter,
  searchQuery,
  onFieldChange,
  onSourceChange,
  onSearchChange,
}: {
  fieldFilter: string;
  sourceFilter: string;
  searchQuery: string;
  onFieldChange: (v: string) => void;
  onSourceChange: (v: string) => void;
  onSearchChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 mb-6">
      <div>
        <label htmlFor="field-filter" className="sr-only">
          Field filter
        </label>
        <select
          id="field-filter"
          value={fieldFilter}
          onChange={(e) => onFieldChange(e.target.value)}
          className="block rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
        >
          {FIELD_OPTIONS.map((opt) => (
            <option key={opt} value={opt}>
              {opt === 'all' ? 'All Fields' : capitalize(opt)}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="source-filter" className="sr-only">
          Source filter
        </label>
        <select
          id="source-filter"
          value={sourceFilter}
          onChange={(e) => onSourceChange(e.target.value)}
          className="block rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
        >
          {SOURCE_OPTIONS.map((opt) => (
            <option key={opt} value={opt}>
              {opt === 'all' ? 'All Sources' : capitalize(opt)}
            </option>
          ))}
        </select>
      </div>

      <div className="flex-1 min-w-[200px]">
        <label htmlFor="search-input" className="sr-only">
          Search corrections
        </label>
        <input
          id="search-input"
          type="text"
          placeholder="Search raw or canonical value..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm placeholder:text-gray-400 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
        />
      </div>
    </div>
  );
}

function FieldBadge({ field }: { field: string }) {
  const colors = FIELD_BADGE_COLORS[field] ?? 'bg-gray-100 text-gray-800';
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${colors}`}>
      {capitalize(field)}
    </span>
  );
}

function SourceBadge({ source }: { source: string }) {
  const colors = SOURCE_BADGE_COLORS[source] ?? 'bg-gray-100 text-gray-800';
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${colors}`}>
      {capitalize(source)}
    </span>
  );
}

function CorrectionRow({ entry }: { entry: CorrectionEntry }) {
  return (
    <tr className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
      <td className="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">
        {formatTimestamp(entry.timestamp)}
      </td>
      <td className="px-4 py-3">
        <FieldBadge field={entry.field} />
      </td>
      <td className="px-4 py-3">
        <SourceBadge source={entry.source} />
      </td>
      <td className="px-4 py-3 text-sm">
        <span className="text-gray-700 font-mono">{entry.raw_value}</span>
        <span className="mx-2 text-gray-400" aria-label="maps to">
          &rarr;
        </span>
        <span className="text-indigo-700 font-mono font-medium">
          {entry.canonical_value}
        </span>
      </td>
      <td className="px-4 py-3 text-sm text-gray-500 max-w-xs truncate" title={entry.evidence}>
        {entry.evidence}
      </td>
    </tr>
  );
}

function Pagination({
  page,
  totalPages,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  onPageChange: (p: number) => void;
}) {
  if (totalPages <= 1) return null;

  const pages: (number | 'ellipsis')[] = [];
  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || (i >= page - 1 && i <= page + 1)) {
      pages.push(i);
    } else if (pages[pages.length - 1] !== 'ellipsis') {
      pages.push('ellipsis');
    }
  }

  return (
    <div className="flex items-center justify-center gap-1 mt-4">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        className="px-3 py-1.5 text-sm rounded-md border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Previous
      </button>
      {pages.map((p, idx) =>
        p === 'ellipsis' ? (
          <span key={`ellipsis-${String(idx)}`} className="px-2 text-gray-400">
            ...
          </span>
        ) : (
          <button
            key={p}
            type="button"
            onClick={() => onPageChange(p)}
            className={`px-3 py-1.5 text-sm rounded-md border ${
              p === page
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
            }`}
          >
            {p}
          </button>
        )
      )}
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        className="px-3 py-1.5 text-sm rounded-md border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Next
      </button>
    </div>
  );
}

function ExportToolbar({ entries }: { entries: CorrectionEntry[] }) {
  const handleCsv = useCallback(() => {
    const csv = correctionsToCsv(entries);
    downloadFile(csv, 'corrections.csv', 'text/csv;charset=utf-8;');
  }, [entries]);

  const handleJson = useCallback(() => {
    const json = JSON.stringify(entries, null, 2);
    downloadFile(json, 'corrections.json', 'application/json');
  }, [entries]);

  return (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={handleCsv}
        disabled={entries.length === 0}
        className="px-3 py-1.5 text-sm rounded-md border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Export as CSV
      </button>
      <button
        type="button"
        onClick={handleJson}
        disabled={entries.length === 0}
        className="px-3 py-1.5 text-sm rounded-md border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Export as JSON
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function ReviewSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
            <div className="h-4 bg-gray-200 rounded w-24 mb-2" />
            <div className="h-6 bg-gray-200 rounded w-16" />
          </div>
        ))}
      </div>
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-6">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="flex gap-4 mb-4">
            <div className="h-4 bg-gray-200 rounded w-24" />
            <div className="h-4 bg-gray-200 rounded w-16" />
            <div className="h-4 bg-gray-200 rounded w-16" />
            <div className="h-4 bg-gray-200 rounded flex-1" />
            <div className="h-4 bg-gray-200 rounded w-32" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function Review() {
  const [fieldFilter, setFieldFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);

  // Reset page when filters change
  const handleFieldChange = useCallback((v: string) => {
    setFieldFilter(v);
    setPage(1);
  }, []);

  const handleSourceChange = useCallback((v: string) => {
    setSourceFilter(v);
    setPage(1);
  }, []);

  const handleSearchChange = useCallback((v: string) => {
    setSearchQuery(v);
    setPage(1);
  }, []);

  // Fetch data - pass server-side filters for field and source
  const apiField = fieldFilter === 'all' ? undefined : fieldFilter;
  const apiSource = sourceFilter === 'all' ? undefined : sourceFilter;

  const { data, isLoading, isError, error } = useCorrectionHistory(
    apiField,
    apiSource
  );

  // Client-side search filter and pagination
  const { filteredEntries, totalFiltered } = useMemo(() => {
    if (!data) return { filteredEntries: [], totalFiltered: 0 };

    let entries = data.entries;

    // Apply client-side text search
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      entries = entries.filter(
        (e) =>
          e.raw_value.toLowerCase().includes(q) ||
          e.canonical_value.toLowerCase().includes(q)
      );
    }

    return { filteredEntries: entries, totalFiltered: entries.length };
  }, [data, searchQuery]);

  // Paginate
  const totalPages = Math.max(1, Math.ceil(totalFiltered / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const startIdx = (safePage - 1) * PAGE_SIZE;
  const pageEntries = filteredEntries.slice(startIdx, startIdx + PAGE_SIZE);

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-900 mb-2">
        Corrections Review
      </h1>
      <p className="text-gray-500 mb-8">
        Review corrections history. Browse all corrections applied to
        normalization maps, filter by field or source, and export results.
      </p>

      {isLoading && <ReviewSkeleton />}

      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-red-700">
          <h2 className="font-semibold mb-1">Failed to load correction history</h2>
          <p className="text-sm">
            {error instanceof Error ? error.message : 'Unknown error'}
          </p>
        </div>
      )}

      {data && (
        <>
          <SummaryBar entries={filteredEntries} total={data.total} />

          <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
            <FilterBar
              fieldFilter={fieldFilter}
              sourceFilter={sourceFilter}
              searchQuery={searchQuery}
              onFieldChange={handleFieldChange}
              onSourceChange={handleSourceChange}
              onSearchChange={handleSearchChange}
            />
          </div>

          <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <h2 className="text-sm font-medium text-gray-700">
                Correction History
              </h2>
              <div className="flex items-center gap-4">
                <span className="text-xs text-gray-500">
                  {totalFiltered.toLocaleString()} result{totalFiltered === 1 ? '' : 's'}
                  {searchQuery.trim() ? ' (filtered)' : ''}
                </span>
                <ExportToolbar entries={filteredEntries} />
              </div>
            </div>

            {pageEntries.length === 0 ? (
              <div className="flex items-center justify-center h-48 text-gray-400">
                {searchQuery.trim()
                  ? 'No corrections match your search.'
                  : 'No corrections found.'}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50">
                      <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Time
                      </th>
                      <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Field
                      </th>
                      <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Source
                      </th>
                      <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Mapping
                      </th>
                      <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Evidence
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageEntries.map((entry, idx) => (
                      <CorrectionRow
                        key={`${entry.timestamp}-${entry.raw_value}-${String(idx)}`}
                        entry={entry}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="px-6 py-4 border-t border-gray-100">
              <Pagination
                page={safePage}
                totalPages={totalPages}
                onPageChange={setPage}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
