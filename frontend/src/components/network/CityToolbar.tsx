import { useMemo, useRef, useState } from 'react';
import type { PlaceMarker } from '../../types/network';

interface Props {
  places: PlaceMarker[];
  onSelect: (placeNorm: string) => void;
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Slim toolbar for the cities layer: a ranked, searchable city list — the
 *  navigational device for overlapping circles (you never have to click a tiny
 *  dot; pick the city from the list instead). */
export default function CityToolbar({ places, onSelect }: Props) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const blurTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const ranked = useMemo(
    () => [...places].sort((a, b) => b.record_count - a.record_count),
    [places],
  );
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const pool = q
      ? ranked.filter((p) => p.place_norm.toLowerCase().includes(q))
      : ranked;
    return pool.slice(0, 12);
  }, [ranked, query]);

  const pick = (p: PlaceMarker) => {
    setQuery('');
    setOpen(false);
    onSelect(p.place_norm);
  };

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-white border-b text-sm">
      <span className="text-gray-500 hidden sm:inline">
        <span className="font-medium text-gray-800">{places.length}</span> printing cities — click a circle, or
      </span>
      <div className="relative" data-tour="city-finder">
        <input
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => { blurTimer.current = setTimeout(() => setOpen(false), 150); }}
          placeholder="Find a city…"
          className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 w-56 focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
        {open && shown.length > 0 && (
          <ul
            className="absolute top-full left-0 mt-1 w-72 bg-white border border-gray-200 rounded-lg shadow-lg z-50 max-h-72 overflow-y-auto"
            // preventDefault keeps the input focused while pressing a list item —
            // otherwise blur's close-timer unmounts the list mid-click and the
            // click lands on nothing (only reproducible at human click speed).
            onMouseDown={(e) => e.preventDefault()}
          >
            {!query.trim() && (
              <li className="px-3 pt-2 pb-1 text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
                Top printing cities
              </li>
            )}
            {shown.map((p) => (
              <li key={p.place_norm}>
                <button
                  onClick={() => pick(p)}
                  className="w-full text-start px-3 py-1.5 hover:bg-gray-50 flex justify-between items-baseline gap-2"
                >
                  <span className="text-gray-800 truncate">{cap(p.place_norm)}</span>
                  <span className="text-xs text-gray-400 tabular-nums shrink-0">{p.record_count} books</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
