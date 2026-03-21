import { useState, useCallback } from 'react';
import type { IssueRecord } from '../../types/metadata';

interface BatchToolbarProps {
  selectedRows: IssueRecord[];
  field: string;
  onApplyCorrection: (canonicalValue: string, rows: IssueRecord[]) => void;
  isApplying: boolean;
}

export default function BatchToolbar({
  selectedRows,
  field,
  onApplyCorrection,
  isApplying,
}: BatchToolbarProps) {
  const [showModal, setShowModal] = useState(false);
  const [canonicalValue, setCanonicalValue] = useState('');

  const handleExportCsv = useCallback(() => {
    const headers = ['mms_id', 'raw_value', 'norm_value', 'confidence', 'method'];
    const rows = selectedRows.map((r) => [
      r.mms_id,
      `"${(r.raw_value ?? '').replace(/"/g, '""')}"`,
      `"${(r.norm_value ?? '').replace(/"/g, '""')}"`,
      String(r.confidence),
      r.method,
    ]);
    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${field}_issues_export.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [selectedRows, field]);

  const handleApply = useCallback(() => {
    if (canonicalValue.trim()) {
      onApplyCorrection(canonicalValue.trim(), selectedRows);
      setShowModal(false);
      setCanonicalValue('');
    }
  }, [canonicalValue, onApplyCorrection, selectedRows]);

  if (selectedRows.length === 0) return null;

  return (
    <>
      <div className="flex items-center gap-3 bg-indigo-50 border border-indigo-200 rounded-lg px-4 py-2.5">
        <span className="text-sm font-medium text-indigo-700">
          {selectedRows.length} row{selectedRows.length !== 1 ? 's' : ''} selected
        </span>
        <div className="h-4 w-px bg-indigo-200" />
        <button
          onClick={() => {
            setCanonicalValue('');
            setShowModal(true);
          }}
          disabled={isApplying}
          className="text-sm font-medium text-indigo-600 hover:text-indigo-800 disabled:opacity-50"
        >
          Apply correction to {selectedRows.length} selected
        </button>
        <button
          onClick={handleExportCsv}
          className="text-sm font-medium text-indigo-600 hover:text-indigo-800"
        >
          Export CSV
        </button>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Batch Correction
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Apply a canonical value to {selectedRows.length} selected record{selectedRows.length !== 1 ? 's' : ''} in the <span className="font-medium">{field}</span> field.
            </p>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Canonical Value
            </label>
            <input
              type="text"
              value={canonicalValue}
              onChange={(e) => setCanonicalValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleApply();
                if (e.key === 'Escape') setShowModal(false);
              }}
              placeholder="Enter the correct normalized value..."
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent mb-4"
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
              >
                Cancel
              </button>
              <button
                onClick={handleApply}
                disabled={!canonicalValue.trim() || isApplying}
                className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isApplying ? 'Applying...' : 'Apply'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
