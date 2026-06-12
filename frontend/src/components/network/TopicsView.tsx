import { useEffect, useMemo, useRef, useState } from 'react';
import { hierarchy, pack } from 'd3-hierarchy';
import type { TopicMarker } from '../../api/network';
import { CENTURY_COLORS, getCenturyLabel } from '../../types/network';

interface Props {
  topics: TopicMarker[];
  onSelect: (subject: string) => void;
}

interface Leaf {
  subject: string;
  label: string;
  count: number;
  peak_decade: number | null;
  value_he: string | null;
  kind: 'topic' | 'form';
}

const rgb = (c: [number, number, number]) => `rgb(${c[0]},${c[1]},${c[2]})`;

const cleanHe = (v: string | null) => (v && !v.includes('\uFFFD') ? v : null);

function eraColor(peak: number | null): string {
  const c = CENTURY_COLORS[getCenturyLabel(peak)] ?? CENTURY_COLORS['Unknown'];
  return rgb(c);
}

/** The topic constellation: packed subject bubbles grouped by LCSH root,
 *  sized by holdings, colored by the era of peak printing (place redesign —
 *  the non-map "what is this collection about" entrance). */
export default function TopicsView({ topics, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [filter, setFilter] = useState('');

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Two-level hierarchy: roots → headings. Sub-headings drop the root prefix
  // for legible in-bubble labels ('Grammar — Early works to 1800').
  const layout = useMemo(() => {
    if (size.w < 50 || size.h < 50 || topics.length === 0) return null;
    const byRoot = new Map<string, Leaf[]>();
    for (const t of topics) {
      const label = t.subject === t.root ? t.subject
        : t.subject.startsWith(t.root) ? t.subject.slice(t.root.length).replace(/^[. ]*— /, '') : t.subject;
      const leaf: Leaf = { subject: t.subject, label, count: t.count, peak_decade: t.peak_decade, value_he: t.value_he, kind: t.kind };
      if (!byRoot.has(t.root)) byRoot.set(t.root, []);
      byRoot.get(t.root)!.push(leaf);
    }
    const data = {
      children: [...byRoot.entries()].map(([root, items]) => ({ root, children: items })),
    };
    const h = hierarchy<unknown>(data as unknown)
      .sum((d) => (d as Leaf).count ?? 0)
      .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
    pack<unknown>().size([size.w, size.h - 8]).padding(3)(h);
    return h;
  }, [topics, size]);

  const q = filter.trim().toLowerCase();
  const matches = (l: Leaf) =>
    !q || l.subject.toLowerCase().includes(q) || (cleanHe(l.value_he) ?? '').includes(filter.trim());

  return (
    <div className="absolute inset-0 bg-white flex flex-col">
      {/* Slim toolbar: filter + era legend */}
      <div className="flex items-center gap-4 px-4 py-2 border-b text-sm shrink-0 flex-wrap">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter subjects…"
          className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 w-56 focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
        <div className="flex items-center gap-2.5 text-xs text-gray-500 flex-wrap">
          <span className="text-gray-400">Color = era of peak printing:</span>
          {Object.entries(CENTURY_COLORS).map(([label, c]) => (
            <span key={label} className="inline-flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ backgroundColor: rgb(c) }} />
              {label}
            </span>
          ))}
          <span className="inline-flex items-center gap-1 ml-2">
            <span className="w-2.5 h-2.5 rounded-full inline-block border-2 border-dashed border-gray-400" />
            form/genre (what the books are)
          </span>
        </div>
      </div>

      <div ref={containerRef} className="flex-1 min-h-0 relative">
        {layout && (
          <svg width={size.w} height={size.h - 8} className="block">
            {/* Root rings + labels */}
            {layout.children?.map((g) => {
              const node = g as unknown as { x: number; y: number; r: number; data: { root: string } };
              if (node.r < 14) return null;
              return (
                <g key={node.data.root}>
                  <circle cx={node.x} cy={node.y} r={node.r} fill="none" stroke="#e2e8f0" strokeWidth={1.2} />
                  {node.r > 42 && (
                    <text x={node.x} y={node.y - node.r + 13} textAnchor="middle"
                          className="fill-slate-400" fontSize={11} fontWeight={600}>
                      {node.data.root.length > 28 ? node.data.root.slice(0, 27) + '…' : node.data.root}
                    </text>
                  )}
                </g>
              );
            })}
            {/* Subject bubbles */}
            {layout.leaves().map((lf) => {
              const node = lf as unknown as { x: number; y: number; r: number; data: Leaf };
              const d = node.data;
              const dim = !matches(d);
              return (
                <g key={d.subject}
                   className="cursor-pointer"
                   opacity={dim ? 0.12 : 1}
                   onClick={() => !dim && onSelect(d.subject)}>
                  <circle
                    cx={node.x} cy={node.y} r={Math.max(node.r, 2)}
                    fill={eraColor(d.peak_decade)} fillOpacity={0.82}
                    stroke={d.kind === 'form' ? '#475569' : '#ffffff'}
                    strokeWidth={d.kind === 'form' ? 1.6 : 1}
                    strokeDasharray={d.kind === 'form' ? '4 3' : undefined}
                  >
                    <title>{`${d.subject}${cleanHe(d.value_he) ? `\n${cleanHe(d.value_he)}` : ''}\n${d.count} books`}</title>
                  </circle>
                  {node.r > 26 && (
                    <text x={node.x} y={node.y} textAnchor="middle" dominantBaseline="middle"
                          fontSize={Math.min(13, node.r / 3.2)} fontWeight={600} fill="#1e293b"
                          style={{ pointerEvents: 'none' }}>
                      {d.label.length > Math.floor(node.r / 3.4) ? d.label.slice(0, Math.floor(node.r / 3.4) - 1) + '…' : d.label}
                    </text>
                  )}
                  {node.r > 26 && (
                    <text x={node.x} y={node.y + Math.min(13, node.r / 3.2) + 2} textAnchor="middle" dominantBaseline="middle"
                          fontSize={10} fill="#475569" style={{ pointerEvents: 'none' }}>
                      {d.count}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        )}
      </div>
    </div>
  );
}
