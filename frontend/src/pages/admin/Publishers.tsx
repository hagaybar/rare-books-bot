import { useState, useMemo, Fragment, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  getExpandedRowModel,
  createColumnHelper,
  flexRender,
  type SortingState,
  type ExpandedState,
} from '@tanstack/react-table';
import {
  fetchPublishers,
  createPublisher,
  updatePublisher,
  deletePublisher,
  addVariant,
  deleteVariant,
} from '../../api/publishers';
import type { PublisherAuthority } from '../../types/publishers';
import ConfidenceBadge from '../../components/shared/ConfidenceBadge';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PUBLISHER_TYPES = [
  { value: '', label: 'All Types' },
  { value: 'printing_house', label: 'Printing House' },
  { value: 'unresearched', label: 'Unresearched' },
  { value: 'bibliophile_society', label: 'Bibliophile Society' },
  { value: 'modern_publisher', label: 'Modern Publisher' },
  { value: 'private_press', label: 'Private Press' },
  { value: 'unknown_marker', label: 'Unknown Marker' },
] as const;

const PUBLISHER_TYPE_OPTIONS = PUBLISHER_TYPES.filter((t) => t.value !== '');

const PAGE_SIZE = 25;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function typeBadge(type: string, isMissingMarker: boolean) {
  if (isMissingMarker) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-200 text-gray-600">
        placeholder
      </span>
    );
  }

  const styles: Record<string, string> = {
    printing_house: 'bg-blue-100 text-blue-800',
    bibliophile_society: 'bg-purple-100 text-purple-800',
    modern_publisher: 'bg-teal-100 text-teal-800',
    private_press: 'bg-emerald-100 text-emerald-800',
    unknown_marker: 'bg-gray-200 text-gray-600',
    unresearched: 'bg-amber-100 text-amber-800',
  };

  const label: Record<string, string> = {
    printing_house: 'Printing House',
    bibliophile_society: 'Bibliophile Society',
    modern_publisher: 'Modern Publisher',
    private_press: 'Private Press',
    unknown_marker: 'Unknown',
    unresearched: 'Unresearched',
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${styles[type] ?? 'bg-gray-100 text-gray-700'}`}
    >
      {label[type] ?? type}
    </span>
  );
}

// ---------------------------------------------------------------------------
// New Authority Form
// ---------------------------------------------------------------------------

function NewAuthorityForm({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('');
  const [type, setType] = useState('unresearched');
  const [confidence, setConfidence] = useState(0.5);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createPublisher({ canonical_name: name.trim(), type, confidence });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-indigo-50 border border-indigo-200 rounded-lg p-4 mb-4">
      <h3 className="text-sm font-semibold text-indigo-800 mb-3">New Publisher Authority</h3>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[200px]">
          <label className="block text-xs font-medium text-gray-600 mb-1">Canonical Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm"
            placeholder="e.g. Elsevier"
            required
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Type</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="border border-gray-300 rounded-md px-3 py-1.5 text-sm"
          >
            {PUBLISHER_TYPE_OPTIONS.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <div className="w-24">
          <label className="block text-xs font-medium text-gray-600 mb-1">Confidence</label>
          <input
            type="number"
            step="0.05"
            min="0"
            max="1"
            value={confidence}
            onChange={(e) => setConfidence(parseFloat(e.target.value))}
            className="w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm"
          />
        </div>
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={saving || !name.trim()}
            className="px-4 py-1.5 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Creating...' : 'Create'}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 border border-gray-300 text-sm font-medium rounded-md text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
      {error && <p className="text-sm text-red-600 mt-2">{error}</p>}
    </form>
  );
}

// ---------------------------------------------------------------------------
// Confirm Dialog
// ---------------------------------------------------------------------------

function ConfirmDialog({
  title,
  message,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm w-full mx-4">
        <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
        <p className="text-sm text-gray-600 mb-4">{message}</p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="px-4 py-2 bg-red-600 text-white rounded-md text-sm font-medium hover:bg-red-700"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function Publishers() {
  // --- Filter state ---
  const [typeFilter, setTypeFilter] = useState('');
  const [showNewForm, setShowNewForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editData, setEditData] = useState<{ canonical_name: string; type: string; confidence: number }>({
    canonical_name: '',
    type: '',
    confidence: 0.5,
  });
  const [deleteTarget, setDeleteTarget] = useState<PublisherAuthority | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  const queryClient = useQueryClient();

  const showToast = useCallback((message: string, type: 'success' | 'error') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  // --- Data fetching ---
  const {
    data,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['publishers', typeFilter],
    queryFn: () => fetchPublishers(typeFilter || undefined),
    staleTime: 60_000,
  });

  const items = data?.items ?? [];

  // --- Computed stats (always from unfiltered data for summary cards) ---
  const {
    data: allData,
  } = useQuery({
    queryKey: ['publishers', ''],
    queryFn: () => fetchPublishers(),
    staleTime: 60_000,
  });

  const stats = useMemo(() => {
    const all = allData?.items ?? [];
    const total = all.length;
    const researched = all.filter(
      (a) => a.type !== 'unresearched'
    ).length;
    const unresearched = all.filter(
      (a) => a.type === 'unresearched'
    ).length;
    const totalVariants = all.reduce((sum, a) => sum + a.variant_count, 0);
    return { total, researched, unresearched, totalVariants };
  }, [allData]);

  // --- Mutations ---
  const updateMutation = useMutation({
    mutationFn: ({ id, data: d }: { id: number; data: Parameters<typeof updatePublisher>[1] }) =>
      updatePublisher(id, d),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['publishers'] });
      setEditingId(null);
      showToast('Publisher updated', 'success');
    },
    onError: (err: Error) => showToast(err.message, 'error'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deletePublisher(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['publishers'] });
      setDeleteTarget(null);
      showToast('Publisher deleted', 'success');
    },
    onError: (err: Error) => showToast(err.message, 'error'),
  });

  const addVariantMutation = useMutation({
    mutationFn: ({ pubId, data: d }: { pubId: number; data: Parameters<typeof addVariant>[1] }) =>
      addVariant(pubId, d),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['publishers'] });
      showToast('Variant added', 'success');
    },
    onError: (err: Error) => showToast(err.message, 'error'),
  });

  const deleteVariantMutation = useMutation({
    mutationFn: ({ pubId, varId }: { pubId: number; varId: number }) => deleteVariant(pubId, varId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['publishers'] });
      showToast('Variant removed', 'success');
    },
    onError: (err: Error) => showToast(err.message, 'error'),
  });

  // --- Inline edit handlers ---
  const startEdit = (row: PublisherAuthority) => {
    setEditingId(row.id);
    setEditData({
      canonical_name: row.canonical_name,
      type: row.type,
      confidence: row.confidence,
    });
  };

  const saveEdit = () => {
    if (editingId === null) return;
    updateMutation.mutate({ id: editingId, data: editData });
  };

  const cancelEdit = () => {
    setEditingId(null);
  };

  // --- Table state ---
  const [sorting, setSorting] = useState<SortingState>([]);
  const [expanded, setExpanded] = useState<ExpandedState>({});

  // --- Column definitions ---
  const columnHelper = createColumnHelper<PublisherAuthority>();

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: 'expander',
        header: () => null,
        cell: ({ row }) =>
          row.original.variant_count > 0 ? (
            <button
              type="button"
              onClick={row.getToggleExpandedHandler()}
              className="p-1 rounded hover:bg-gray-100 transition-colors"
              title={row.getIsExpanded() ? 'Collapse variants' : 'Expand variants'}
            >
              <svg
                className={`w-4 h-4 text-gray-500 transition-transform ${row.getIsExpanded() ? 'rotate-90' : ''}`}
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </button>
          ) : null,
        size: 40,
      }),
      columnHelper.accessor('canonical_name', {
        header: 'Name',
        cell: (info) => {
          const row = info.row.original;
          if (editingId === row.id) {
            return (
              <input
                type="text"
                value={editData.canonical_name}
                onChange={(e) => setEditData((d) => ({ ...d, canonical_name: e.target.value }))}
                className="border border-indigo-300 rounded px-2 py-1 text-sm w-full"
              />
            );
          }
          return (
            <div className="flex items-center gap-2">
              <span className={`text-sm font-medium ${row.type === 'unresearched' ? 'text-amber-900' : 'text-gray-900'}`}>
                {info.getValue()}
              </span>
            </div>
          );
        },
      }),
      columnHelper.accessor('type', {
        header: 'Type',
        cell: (info) => {
          const row = info.row.original;
          if (editingId === row.id) {
            return (
              <select
                value={editData.type}
                onChange={(e) => setEditData((d) => ({ ...d, type: e.target.value }))}
                className="border border-indigo-300 rounded px-2 py-1 text-xs"
              >
                {PUBLISHER_TYPE_OPTIONS.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            );
          }
          return typeBadge(info.getValue(), row.is_missing_marker);
        },
        size: 160,
      }),
      columnHelper.accessor('confidence', {
        header: 'Confidence',
        cell: (info) => {
          const row = info.row.original;
          if (editingId === row.id) {
            return (
              <input
                type="number"
                step="0.05"
                min="0"
                max="1"
                value={editData.confidence}
                onChange={(e) => setEditData((d) => ({ ...d, confidence: parseFloat(e.target.value) }))}
                className="border border-indigo-300 rounded px-2 py-1 text-sm w-20"
              />
            );
          }
          return <ConfidenceBadge confidence={info.getValue()} showLabel />;
        },
        size: 110,
      }),
      columnHelper.accessor('variant_count', {
        header: 'Variants',
        cell: (info) => (
          <span className="text-sm text-gray-700 tabular-nums">{info.getValue()}</span>
        ),
        size: 90,
      }),
      columnHelper.accessor('imprint_count', {
        header: 'Imprints',
        cell: (info) => (
          <span className="text-sm text-gray-700 tabular-nums">{info.getValue()}</span>
        ),
        size: 90,
      }),
      columnHelper.accessor('location', {
        header: 'Location',
        cell: (info) => {
          const val = info.getValue();
          return val ? (
            <span className="text-sm text-gray-600">{val}</span>
          ) : (
            <span className="text-sm text-gray-300">--</span>
          );
        },
        size: 120,
      }),
      columnHelper.display({
        id: 'actions',
        header: () => null,
        cell: ({ row }) => {
          const r = row.original;
          if (editingId === r.id) {
            return (
              <div className="flex gap-1">
                <button
                  type="button"
                  onClick={saveEdit}
                  disabled={updateMutation.isPending}
                  className="p-1 rounded text-green-600 hover:bg-green-50 transition-colors"
                  title="Save"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                </button>
                <button
                  type="button"
                  onClick={cancelEdit}
                  className="p-1 rounded text-gray-400 hover:bg-gray-100 transition-colors"
                  title="Cancel"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            );
          }
          return (
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => startEdit(r)}
                className="p-1 rounded text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                title="Edit"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
                </svg>
              </button>
              <button
                type="button"
                onClick={() => setDeleteTarget(r)}
                className="p-1 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                title="Delete"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                </svg>
              </button>
            </div>
          );
        },
        size: 80,
      }),
    ],
    [columnHelper, editingId, editData, updateMutation.isPending]
  );

  // --- Table instance ---
  const table = useReactTable({
    data: items,
    columns,
    state: { sorting, expanded },
    onSortingChange: setSorting,
    onExpandedChange: setExpanded,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getRowCanExpand: (row) => row.original.variant_count > 0,
    initialState: {
      pagination: { pageSize: PAGE_SIZE },
    },
  });

  const pageIndex = table.getState().pagination.pageIndex;
  const pageCount = table.getPageCount();

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-900 mb-2">
        Publisher Authorities
      </h1>
      <p className="text-gray-500 mb-6">
        Manage publisher authority records and their variant name forms.
      </p>

      {/* Toast */}
      {toast && (
        <div
          className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium ${
            toast.type === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
          }`}
        >
          {toast.message}
        </div>
      )}

      {/* Delete confirmation dialog */}
      {deleteTarget && (
        <ConfirmDialog
          title="Delete Publisher Authority"
          message={`Are you sure you want to delete "${deleteTarget.canonical_name}"? This will also remove all its variant forms.`}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {/* --- Stats Cards --- */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Total Authorities" value={stats.total} />
        <StatCard label="Researched" value={stats.researched} color="green" />
        <StatCard label="Unresearched" value={stats.unresearched} color="amber" />
        <StatCard label="Total Variants" value={stats.totalVariants} color="blue" />
      </div>

      {/* --- New Authority / Filter --- */}
      {showNewForm && (
        <NewAuthorityForm
          onClose={() => setShowNewForm(false)}
          onCreated={() => queryClient.invalidateQueries({ queryKey: ['publishers'] })}
        />
      )}

      <div className="flex items-center gap-4 bg-white rounded-lg border border-gray-200 shadow-sm px-4 py-3 mb-4">
        <button
          type="button"
          onClick={() => setShowNewForm(!showNewForm)}
          className="px-3 py-1.5 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700 transition-colors"
        >
          + New Authority
        </button>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-600 whitespace-nowrap">
            Publisher Type
          </label>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="text-sm border border-gray-300 rounded-md px-3 py-1.5 text-gray-700 bg-white"
          >
            {PUBLISHER_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div className="ml-auto text-sm text-gray-500">
          Showing {items.length} {items.length === 1 ? 'authority' : 'authorities'}
        </div>
      </div>

      {/* --- Loading --- */}
      {isLoading && (
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
          <div className="flex items-center justify-center h-64 text-gray-400">
            <svg
              className="animate-spin -ml-1 mr-3 h-5 w-5 text-indigo-500"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            Loading publisher authorities...
          </div>
        </div>
      )}

      {/* --- Error --- */}
      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-red-700">
          <h2 className="font-semibold mb-1">Failed to load publisher authorities</h2>
          <p className="text-sm">
            {error instanceof Error ? error.message : 'Unknown error'}
          </p>
        </div>
      )}

      {/* --- Data Table --- */}
      {!isLoading && !isError && (
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                {table.getHeaderGroups().map((headerGroup) => (
                  <tr
                    key={headerGroup.id}
                    className="border-b border-gray-200 bg-gray-50"
                  >
                    {headerGroup.headers.map((header) => (
                      <th
                        key={header.id}
                        className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none hover:bg-gray-100 transition-colors"
                        style={{
                          width:
                            header.getSize() !== 150
                              ? header.getSize()
                              : undefined,
                        }}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        <div className="flex items-center gap-1">
                          {header.isPlaceholder
                            ? null
                            : flexRender(
                                header.column.columnDef.header,
                                header.getContext()
                              )}
                          {header.column.getIsSorted() === 'asc' && (
                            <svg
                              className="w-3 h-3"
                              fill="currentColor"
                              viewBox="0 0 20 20"
                            >
                              <path d="M5 13l5-5 5 5H5z" />
                            </svg>
                          )}
                          {header.column.getIsSorted() === 'desc' && (
                            <svg
                              className="w-3 h-3"
                              fill="currentColor"
                              viewBox="0 0 20 20"
                            >
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
                {table.getRowModel().rows.map((row) => (
                  <Fragment key={row.id}>
                    <tr
                      className={`transition-colors ${
                        row.original.type === 'unresearched'
                          ? 'bg-amber-50/50 hover:bg-amber-50'
                          : row.original.is_missing_marker
                            ? 'bg-gray-50/50 hover:bg-gray-100/50'
                            : 'hover:bg-gray-50'
                      }`}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="px-4 py-3">
                          {flexRender(
                            cell.column.columnDef.cell,
                            cell.getContext()
                          )}
                        </td>
                      ))}
                    </tr>

                    {/* --- Expanded Variant Details --- */}
                    {row.getIsExpanded() && (
                      <tr>
                        <td
                          colSpan={columns.length}
                          className="px-4 py-0 bg-slate-50"
                        >
                          <VariantPanel
                            authority={row.original}
                            onAddVariant={(d) =>
                              addVariantMutation.mutate({ pubId: row.original.id, data: d })
                            }
                            onDeleteVariant={(varId) =>
                              deleteVariantMutation.mutate({ pubId: row.original.id, varId })
                            }
                            isAdding={addVariantMutation.isPending}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {/* --- Pagination --- */}
          {pageCount > 1 && (
            <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-600">
              <span>
                Page {pageIndex + 1} of {pageCount} ({data?.total ?? 0} total)
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => table.previousPage()}
                  disabled={!table.getCanPreviousPage()}
                  className="px-3 py-1.5 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Previous
                </button>
                <button
                  type="button"
                  onClick={() => table.nextPage()}
                  disabled={!table.getCanNextPage()}
                  className="px-3 py-1.5 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Next
                </button>
              </div>
            </div>
          )}

          {/* --- Empty state --- */}
          {items.length === 0 && (
            <div className="flex items-center justify-center h-32 text-gray-400 text-sm">
              No publisher authorities found
              {typeFilter ? ` for type "${typeFilter}"` : ''}.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// VariantPanel sub-component (expanded row content)
// ---------------------------------------------------------------------------

function VariantPanel({
  authority,
  onAddVariant,
  onDeleteVariant,
  isAdding,
}: {
  authority: PublisherAuthority;
  onAddVariant: (data: { variant_form: string; script: string; language?: string }) => void;
  onDeleteVariant: (variantId: number) => void;
  isAdding: boolean;
}) {
  const [showAdd, setShowAdd] = useState(false);
  const [newVariant, setNewVariant] = useState('');
  const [newScript, setNewScript] = useState('latin');
  const [newLang, setNewLang] = useState('');

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newVariant.trim()) return;
    onAddVariant({
      variant_form: newVariant.trim(),
      script: newScript,
      language: newLang.trim() || undefined,
    });
    setNewVariant('');
    setNewLang('');
    setShowAdd(false);
  };

  return (
    <div className="py-3 pl-10">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
          Variant Forms ({authority.variants.length})
        </h4>
        <button
          type="button"
          onClick={() => setShowAdd(!showAdd)}
          className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
        >
          {showAdd ? 'Cancel' : '+ Add Variant'}
        </button>
      </div>

      {showAdd && (
        <form onSubmit={handleAdd} className="flex items-end gap-2 mb-3 bg-white rounded border border-indigo-200 p-2">
          <div className="flex-1">
            <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Variant Form</label>
            <input
              type="text"
              value={newVariant}
              onChange={(e) => setNewVariant(e.target.value)}
              className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
              placeholder="e.g. ex officina elzeviriana"
              required
            />
          </div>
          <div>
            <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Script</label>
            <select
              value={newScript}
              onChange={(e) => setNewScript(e.target.value)}
              className="border border-gray-300 rounded px-2 py-1 text-xs"
            >
              <option value="latin">Latin</option>
              <option value="hebrew">Hebrew</option>
              <option value="arabic">Arabic</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div>
            <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Language</label>
            <input
              type="text"
              value={newLang}
              onChange={(e) => setNewLang(e.target.value)}
              className="w-20 border border-gray-300 rounded px-2 py-1 text-xs"
              placeholder="e.g. lat"
            />
          </div>
          <button
            type="submit"
            disabled={isAdding || !newVariant.trim()}
            className="px-3 py-1 bg-indigo-600 text-white text-xs font-medium rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            Add
          </button>
        </form>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs text-gray-400 uppercase">
              <th className="pb-1 pr-6 font-medium">Variant Form</th>
              <th className="pb-1 pr-6 font-medium">Script</th>
              <th className="pb-1 pr-6 font-medium">Language</th>
              <th className="pb-1 pr-6 font-medium">Primary</th>
              <th className="pb-1 font-medium w-10"></th>
            </tr>
          </thead>
          <tbody>
            {authority.variants.map((v, idx) => (
              <tr key={v.id ?? idx} className="border-t border-gray-100">
                <td className="py-1.5 pr-6 text-gray-800 font-mono text-xs">
                  {v.variant_form}
                </td>
                <td className="py-1.5 pr-6 text-gray-600">{v.script ?? '--'}</td>
                <td className="py-1.5 pr-6 text-gray-600">{v.language ?? '--'}</td>
                <td className="py-1.5 pr-6">
                  {v.is_primary ? (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-800">
                      Primary
                    </span>
                  ) : (
                    <span className="text-gray-300 text-xs">--</span>
                  )}
                </td>
                <td className="py-1.5">
                  {v.id != null && (
                    <button
                      type="button"
                      onClick={() => onDeleteVariant(v.id!)}
                      className="p-0.5 rounded text-gray-300 hover:text-red-500 transition-colors"
                      title="Remove variant"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* External IDs if any */}
      {(authority.viaf_id || authority.wikidata_id || authority.cerl_id) && (
        <div className="mt-3 flex items-center gap-4 text-xs text-gray-500">
          {authority.viaf_id && (
            <span>
              VIAF:{' '}
              <a
                href={`https://viaf.org/viaf/${authority.viaf_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-indigo-600 hover:underline"
              >
                {authority.viaf_id}
              </a>
            </span>
          )}
          {authority.wikidata_id && (
            <span>
              Wikidata:{' '}
              <a
                href={`https://www.wikidata.org/wiki/${authority.wikidata_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-indigo-600 hover:underline"
              >
                {authority.wikidata_id}
              </a>
            </span>
          )}
          {authority.cerl_id && (
            <span>
              CERL:{' '}
              <a
                href={`https://data.cerl.org/thesaurus/${authority.cerl_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-indigo-600 hover:underline"
              >
                {authority.cerl_id}
              </a>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// StatCard sub-component
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color?: 'green' | 'amber' | 'blue';
}) {
  const colorMap = {
    green: 'text-green-700',
    amber: 'text-amber-700',
    blue: 'text-blue-700',
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <p
        className={`text-2xl font-semibold tabular-nums ${color ? colorMap[color] : 'text-gray-900'}`}
      >
        {value}
      </p>
    </div>
  );
}
