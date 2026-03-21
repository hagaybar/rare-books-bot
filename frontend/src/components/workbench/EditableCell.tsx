import { useState, useCallback, useRef, useEffect } from 'react';

interface EditableCellProps {
  value: string | null;
  onSave: (newValue: string) => void;
  isSaving: boolean;
}

export default function EditableCell({ value, onSave, isSaving }: EditableCellProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? '');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const handleDoubleClick = useCallback(() => {
    if (!isSaving) {
      setDraft(value ?? '');
      setEditing(true);
    }
  }, [value, isSaving]);

  const handleCancel = useCallback(() => {
    setEditing(false);
    setDraft(value ?? '');
  }, [value]);

  const handleSave = useCallback(() => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== (value ?? '')) {
      onSave(trimmed);
    }
    setEditing(false);
  }, [draft, value, onSave]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        handleSave();
      } else if (e.key === 'Escape') {
        handleCancel();
      }
    },
    [handleSave, handleCancel]
  );

  if (editing) {
    return (
      <div className="flex items-center gap-1">
        <input
          ref={inputRef}
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          className="w-full border border-indigo-300 rounded px-1.5 py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
          disabled={isSaving}
        />
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="text-green-600 hover:text-green-800 disabled:opacity-50 p-0.5"
          title="Save"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        </button>
        <button
          onClick={handleCancel}
          disabled={isSaving}
          className="text-gray-400 hover:text-gray-600 disabled:opacity-50 p-0.5"
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
    <span
      onDoubleClick={handleDoubleClick}
      className="cursor-pointer hover:bg-indigo-50 rounded px-1 py-0.5 -mx-1 transition-colors"
      title="Double-click to edit"
    >
      {value ?? <span className="text-gray-400 italic">null</span>}
    </span>
  );
}
