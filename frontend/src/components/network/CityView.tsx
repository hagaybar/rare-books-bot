import type { PlaceDetail } from '../../api/network';

interface Props {
  city: PlaceDetail;
  onBack: () => void;
  onPersonClick: (agentNorm: string, displayName: string) => void;
}

function tidySubject(s: string): string {
  return s.replace(/ -- /g, ' — ').replace(/\.$/, '');
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Full-area city drill-down: what this collection holds from one printing city
 *  (place redesign). Replaces the map canvas; not a map itself. */
export default function CityView({ city, onBack, onPersonClick }: Props) {
  const name = capitalize(city.place_norm); // place_norm is normalized; place_display is raw transcription
  const span = city.year_min && city.year_max
    ? (city.year_min === city.year_max ? `${city.year_min}` : `${city.year_min}–${city.year_max}`)
    : null;

  // Continuous decade range so gaps read as gaps, not missing bars
  const decades = city.decades;
  const maxCount = Math.max(1, ...decades.map((d) => d.count));
  let bars: { decade: number; count: number }[] = [];
  if (decades.length > 0) {
    const first = decades[0].decade;
    const last = decades[decades.length - 1].decade;
    const byDecade = new Map(decades.map((d) => [d.decade, d.count]));
    for (let d = first; d <= last; d += 10) bars.push({ decade: d, count: byDecade.get(d) ?? 0 });
  }
  // Keep the chart readable for very long spans
  if (bars.length > 60) bars = bars.filter((b, i) => b.count > 0 || i % 2 === 0);

  return (
    <div className="absolute inset-0 bg-white overflow-y-auto">
      <div className="max-w-5xl mx-auto px-6 py-5">
        <button onClick={onBack} className="text-sm text-blue-600 hover:text-blue-800 mb-3 flex items-center gap-1">
          <span aria-hidden>←</span> Back to map
        </button>

        <div className="flex items-baseline justify-between flex-wrap gap-2">
          <h2 className="text-3xl font-semibold text-gray-900">{name}</h2>
          <p className="text-sm text-gray-500">
            <span className="font-medium text-gray-700">{city.total}</span> books
            {' · '}<span className="font-medium text-gray-700">{city.agent_count}</span> people
            {span && <>{' · '}<span className="font-medium text-gray-700">{span}</span></>}
          </p>
        </div>

        {/* When: printing activity by decade */}
        {bars.length > 1 && (
          <div className="mt-5">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              Printing activity over time
            </h3>
            <div className="flex items-end gap-px h-24">
              {bars.map((b) => (
                <div
                  key={b.decade}
                  className="flex-1 min-w-[3px] bg-blue-500/80 hover:bg-blue-600 rounded-t"
                  style={{ height: `${Math.max(b.count > 0 ? 6 : 0, (b.count / maxCount) * 100)}%` }}
                  title={`${b.decade}s — ${b.count} book${b.count === 1 ? '' : 's'}`}
                />
              ))}
            </div>
            <div className="flex justify-between text-[11px] text-gray-400 mt-1 tabular-nums">
              <span>{bars[0].decade}</span>
              <span>{bars[bars.length - 1].decade + 9}</span>
            </div>
          </div>
        )}

        {/* Who + what */}
        <div className="mt-6 grid md:grid-cols-3 gap-6">
          {city.top_publishers.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Printers & publishers</h3>
              <ul className="space-y-1">
                {city.top_publishers.map((p) => (
                  <li key={p.name} className="flex justify-between gap-2 text-sm">
                    <span className="text-gray-800 truncate" title={p.name}><bdi dir="auto">{p.name}</bdi></span>
                    <span className="text-gray-400 tabular-nums shrink-0">{p.count}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {city.top_agents.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Notable people</h3>
              <ul className="space-y-1">
                {city.top_agents.map((a) => (
                  <li key={a.agent_norm} className="flex justify-between gap-2 text-sm">
                    <button
                      onClick={() => onPersonClick(a.agent_norm, a.display_name)}
                      className="text-blue-600 hover:text-blue-800 hover:underline truncate text-start"
                      title={`Explore ${a.display_name}'s connections`}
                    >
                      <bdi dir="auto">{a.display_name}</bdi>
                    </button>
                    <span className="text-gray-400 tabular-nums shrink-0">{a.count}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {city.top_subjects.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">What was printed here</h3>
              <div className="flex flex-wrap gap-1.5">
                {city.top_subjects.map((s) => (
                  <span key={s.subject} className="inline-flex items-center gap-1 px-2 py-0.5 bg-slate-100 text-slate-700 text-xs rounded-full">
                    <bdi dir="auto" className="max-w-[180px] truncate" title={tidySubject(s.subject)}>{tidySubject(s.subject)}</bdi>
                    <span className="text-slate-400 tabular-nums">{s.count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* The books themselves */}
        <div className="mt-7">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Books printed in {name}{city.total > city.works.length ? ` (showing ${city.works.length} of ${city.total})` : ` (${city.total})`}
          </h3>
          <ul className="divide-y divide-gray-100">
            {city.works.map((w) => (
              <li key={w.mms_id} className="py-2 text-sm flex items-baseline justify-between gap-3">
                <span className="min-w-0">
                  {w.primo_url ? (
                    <a href={w.primo_url} target="_blank" rel="noopener noreferrer" dir="auto"
                       className="text-blue-700 hover:text-blue-900 font-medium">
                      {w.title ?? w.mms_id}
                    </a>
                  ) : (
                    <span dir="auto" className="font-medium text-gray-800">{w.title ?? w.mms_id}</span>
                  )}
                  {w.publisher_display && (
                    <span className="text-gray-500"> · <bdi dir="auto">{w.publisher_display}</bdi></span>
                  )}
                </span>
                <span className="text-gray-400 tabular-nums shrink-0">{w.date_label ?? ''}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
