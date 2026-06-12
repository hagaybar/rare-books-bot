import type { TopicDetail } from '../../api/network';

interface Props {
  topic: TopicDetail;
  onBack: () => void;
  onPersonClick: (agentNorm: string, displayName: string) => void;
  onPlaceClick: (placeNorm: string) => void;
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Topic profile: the subject-axis sibling of CityView. Every mention is a
 *  door — places open city profiles, people open their networks. */
// 117 stored Hebrew translations carry U+FFFD mojibake (fix_19 encoding wart)
// — suppress them rather than display corruption; the data fix is a separate,
// approval-gated pass.
const cleanHe = (v: string | null) => (v && !v.includes('\uFFFD') ? v : null);

export default function TopicView({ topic, onBack, onPersonClick, onPlaceClick }: Props) {
  const valueHe = cleanHe(topic.value_he);
  const decades = topic.decades;
  const maxCount = Math.max(1, ...decades.map((d) => d.count));
  let bars: { decade: number; count: number }[] = [];
  if (decades.length > 0) {
    const byDecade = new Map(decades.map((d) => [d.decade, d.count]));
    for (let d = decades[0].decade; d <= decades[decades.length - 1].decade; d += 10)
      bars.push({ decade: d, count: byDecade.get(d) ?? 0 });
  }
  if (bars.length > 60) bars = bars.filter((b, i) => b.count > 0 || i % 2 === 0);

  const chatQuery = `Tell me about the books on "${topic.subject}" in this collection — what do we hold, from when and where, and by whom?`;

  return (
    <div className="absolute inset-0 bg-white overflow-y-auto z-10">
      <div className="max-w-5xl mx-auto px-6 py-5">
        <button onClick={onBack} className="text-sm text-blue-600 hover:text-blue-800 mb-3 flex items-center gap-1">
          <span aria-hidden>←</span> Back to topics
        </button>

        <div className="flex items-baseline justify-between flex-wrap gap-2">
          <div className="min-w-0">
            <h2 className="text-3xl font-semibold text-gray-900"><bdi dir="auto">{topic.subject}</bdi></h2>
            {valueHe && (
              <p className="text-lg text-gray-500"><bdi dir="auto">{valueHe}</bdi></p>
            )}
          </div>
          <p className="text-sm text-gray-500 shrink-0">
            <span className="font-medium text-gray-700">{topic.total}</span> books
          </p>
        </div>

        {bars.length > 1 && (
          <div className="mt-5">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              When this subject was printed
            </h3>
            <div className="flex items-end gap-px h-24">
              {bars.map((b) => (
                <div key={b.decade}
                     className="flex-1 min-w-[3px] bg-blue-500/80 hover:bg-blue-600 rounded-t"
                     style={{ height: `${Math.max(b.count > 0 ? 6 : 0, (b.count / maxCount) * 100)}%` }}
                     title={`${b.decade}s — ${b.count} book${b.count === 1 ? '' : 's'}`} />
              ))}
            </div>
            <div className="flex justify-between text-[11px] text-gray-400 mt-1 tabular-nums">
              <span>{bars[0].decade}</span>
              <span>{bars[bars.length - 1].decade + 9}</span>
            </div>
          </div>
        )}

        <div className="mt-6 grid md:grid-cols-2 gap-6">
          {topic.top_places.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Where it was printed</h3>
              <ul className="space-y-1">
                {topic.top_places.map((p) => (
                  <li key={p.name} className="flex justify-between gap-2 text-sm">
                    <button onClick={() => onPlaceClick(p.name)}
                            className="text-blue-600 hover:text-blue-800 hover:underline truncate text-start"
                            title={`Open the ${cap(p.name)} city profile`}>
                      {cap(p.name)}
                    </button>
                    <span className="text-gray-400 tabular-nums shrink-0">{p.count}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {topic.top_agents.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Who wrote &amp; printed it</h3>
              <ul className="space-y-1">
                {topic.top_agents.map((a) => (
                  <li key={a.agent_norm} className="flex justify-between gap-2 text-sm">
                    <button onClick={() => onPersonClick(a.agent_norm, a.display_name)}
                            className="text-blue-600 hover:text-blue-800 hover:underline truncate text-start"
                            title={`Explore ${a.display_name}'s network`}>
                      <bdi dir="auto">{a.display_name}</bdi>
                    </button>
                    <span className="text-gray-400 tabular-nums shrink-0">{a.count}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <a href={`/chat?q=${encodeURIComponent(chatQuery)}`}
           className="inline-block mt-5 text-sm text-blue-500 hover:text-blue-700">
          Ask about this subject in Chat →
        </a>

        <div className="mt-6">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Books{topic.total > topic.works.length ? ` (showing ${topic.works.length} of ${topic.total})` : ` (${topic.total})`}
          </h3>
          <ul className="divide-y divide-gray-100">
            {topic.works.map((w) => (
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
                  {w.place_display && (
                    <span className="text-gray-500"> · <bdi dir="auto">{w.place_display}</bdi></span>
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
