interface Props {
  min: number;
  max: number;
  windowStart: number;
  windowWidth: number;
  playing: boolean;
  activeCount: number;
  onStartChange: (year: number) => void;
  onWidthChange: (width: number) => void;
  onTogglePlay: () => void;
  onClose: () => void;
}

const WIDTHS = [50, 100, 200];

/** Sliding time window over imprint dates (issue #32). Drag or play to watch
 *  printing activity migrate across the centuries. */
export default function TimeSlider({
  min, max, windowStart, windowWidth, playing, activeCount,
  onStartChange, onWidthChange, onTogglePlay, onClose,
}: Props) {
  const windowEnd = windowStart + windowWidth;
  const sliderMax = Math.max(min, max - windowWidth);

  return (
    <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-20 w-[min(92%,640px)] bg-white/95 backdrop-blur-sm rounded-xl shadow-lg border border-gray-200 px-4 py-2.5">
      <div className="flex items-center gap-3">
        <button
          onClick={onTogglePlay}
          className="shrink-0 w-9 h-9 rounded-full bg-blue-600 hover:bg-blue-700 text-white flex items-center justify-center"
          title={playing ? 'Pause' : 'Play through time'}
          aria-label={playing ? 'Pause' : 'Play'}
        >
          {playing ? (
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 5h4v14H6zM14 5h4v14h-4z" /></svg>
          ) : (
            <svg className="w-4 h-4 ml-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
          )}
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex items-baseline justify-between mb-0.5">
            <span className="text-sm font-semibold text-gray-900 tabular-nums">{windowStart} – {windowEnd}</span>
            <span className="text-xs text-gray-500">{activeCount} active</span>
          </div>
          <input
            type="range"
            min={min}
            max={sliderMax}
            step={5}
            value={Math.min(windowStart, sliderMax)}
            onChange={(e) => onStartChange(Number(e.target.value))}
            className="w-full"
            aria-label="Window start year"
          />
        </div>

        <div className="shrink-0 flex items-center gap-1">
          <span className="text-xs text-gray-400 mr-1 hidden sm:inline">width</span>
          {WIDTHS.map((w) => (
            <button
              key={w}
              onClick={() => onWidthChange(w)}
              className={`text-xs px-1.5 py-0.5 rounded ${w === windowWidth ? 'bg-blue-100 text-blue-700 font-semibold' : 'text-gray-500 hover:bg-gray-100'}`}
            >
              {w}y
            </button>
          ))}
        </div>

        <button
          onClick={onClose}
          className="shrink-0 text-gray-400 hover:text-gray-600 p-1"
          title="Exit timeline"
          aria-label="Exit timeline"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  );
}
