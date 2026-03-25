/**
 * Row of clickable pill buttons for follow-up query suggestions.
 */

interface FollowUpChipsProps {
  suggestions: string[];
  onSelect: (text: string) => void;
  disabled?: boolean;
}

export default function FollowUpChips({
  suggestions,
  onSelect,
  disabled = false,
}: FollowUpChipsProps) {
  if (suggestions.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {suggestions.map((text) => (
        <button
          key={text}
          type="button"
          onClick={() => onSelect(text)}
          disabled={disabled}
          className="px-3 py-1.5 rounded-full text-xs font-medium
            bg-blue-50 text-blue-700 border border-blue-200
            hover:bg-blue-100 hover:border-blue-300
            disabled:opacity-50 disabled:cursor-not-allowed
            transition-colors cursor-pointer"
        >
          {text}
        </button>
      ))}
    </div>
  );
}
