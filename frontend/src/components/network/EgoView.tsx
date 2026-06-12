import { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import type { MapNode, MapEdge, ColorByMode, EgoResponse } from '../../types/network';
import {
  getAgentColor, buildCommunityColorMap, CONNECTION_TYPE_CONFIG, PUBLISHER_COLOR,
} from '../../types/network';
import { interpretEgo, type NetworkPortrait } from '../../api/network';
import { useAuthStore } from '../../stores/authStore';
import { getRoleLevel } from '../AuthGuard';

interface Props {
  data: EgoResponse;
  colorBy: ColorByMode;
  communities?: string[];
  connectionTypes: string[];
  onNodeClick: (node: MapNode) => void;
}

/** Deterministic archetype of an ego network — the free tier of interpretation.
 *  The Buchon insight generalized: certain shapes have stable meanings. */
function readEgoShape(data: EgoResponse): { badge: string; line: string } | null {
  const focal = data.nodes.find((n) => n.agent_norm === data.focal);
  if (!focal) return null;
  const neighbours = data.nodes.filter((n) => n.agent_norm !== data.focal);
  if (neighbours.length === 0) return null;
  if (neighbours.length <= 2) {
    return { badge: 'A quiet corner', line: `Only ${neighbours.length} connection${neighbours.length === 1 ? '' : 's'} under the current filters — try enabling more connection types.` };
  }
  const roles = [...new Set(data.edges.map((e) => e.relationship).filter(Boolean))].slice(0, 3);
  const roleNote = roles.length ? ` Roles on shared records: ${roles.join(', ')}.` : '';

  if (focal.node_type === 'publisher') {
    return { badge: 'A printing house at work', line: `${neighbours.length} people orbit this press through the books it printed.${roleNote}` };
  }
  const fb = focal.birth_year;
  const dated = neighbours.filter((n) => n.birth_year != null);
  if (fb != null && dated.length >= 3) {
    const older = dated.filter((n) => fb - (n.birth_year as number) >= 150).length;
    const peers = dated.filter((n) => Math.abs((n.birth_year as number) - fb) <= 60).length;
    if (older / dated.length >= 0.6) {
      return {
        badge: 'A gateway to older texts',
        line: `${older} of ${dated.length} dated connections were born 150+ years earlier — the signature of an editor, translator, or compiler bringing older works back into print.${roleNote}`,
      };
    }
    if (peers / dated.length >= 0.6) {
      return {
        badge: 'A circle of contemporaries',
        line: `${peers} of ${dated.length} dated connections lived within a generation or two — a working milieu of colleagues, collaborators, and rivals.${roleNote}`,
      };
    }
  }
  return {
    badge: 'A mixed web',
    line: `${neighbours.length} connections spanning several eras and link types — explore the strands individually.${roleNote}`,
  };
}

interface GNode { id: string; node: MapNode; x?: number; y?: number; fx?: number; fy?: number }
interface GLink { source: string; target: string; edge: MapEdge }

const rgb = (c: [number, number, number]) => `rgb(${c[0]},${c[1]},${c[2]})`;

/** Force-directed 1-hop ego graph (issue #31). Non-geographic peer of MapView.
 *  Focal node is pinned at the centre; the view auto-fits on load and re-centre. */
export default function EgoView({ data, colorBy, communities, connectionTypes, onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const communityColors = useMemo(() => buildCommunityColorMap(communities ?? []), [communities]);

  // Interpretation: free deterministic shape-reading + optional AI portrait.
  const shape = useMemo(() => readEgoShape(data), [data]);
  const user = useAuthStore((s) => s.user);
  const canInterpret = user ? getRoleLevel(user.role) >= getRoleLevel('limited') : false;
  const [portrait, setPortrait] = useState<NetworkPortrait | null>(null);
  const [portraitLoading, setPortraitLoading] = useState(false);
  const [portraitError, setPortraitError] = useState(false);
  useEffect(() => { setPortrait(null); setPortraitError(false); }, [data.focal]);
  const askAI = async () => {
    setPortraitLoading(true);
    setPortraitError(false);
    try {
      setPortrait(await interpretEgo(data.focal, connectionTypes));
    } catch {
      setPortraitError(true);
    } finally {
      setPortraitLoading(false);
    }
  };
  // The AI names ONE neighbour to explore — make it a click if we can find it.
  const threadNode = useMemo(() => {
    if (!portrait) return null;
    return data.nodes.find(
      (n) => n.agent_norm !== data.focal && portrait.next_thread.includes(n.display_name),
    ) ?? null;
  }, [portrait, data]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setSize({ width: el.clientWidth, height: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const graphData = useMemo(() => {
    const nodes = data.nodes.map((n): GNode => {
      const g: GNode = { id: n.agent_norm, node: n };
      if (n.agent_norm === data.focal) { g.fx = 0; g.fy = 0; } // pin focal at centre
      return g;
    });
    const links = data.edges.map((e): GLink => ({ source: e.source, target: e.target, edge: e }));
    return { nodes, links };
  }, [data]);

  // Spread the ring out a bit and keep it compact + centred on the focal.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.d3Force('charge')?.strength(-220);
    fg.d3Force('link')?.distance(70);
    fg.d3ReheatSimulation?.();
  }, [data]);

  const fit = () => fgRef.current?.zoomToFit(500, 80);

  // Re-fit whenever the focal node or the container size changes.
  useEffect(() => {
    if (size.width === 0) return;
    const t = setTimeout(fit, 280);
    return () => clearTimeout(t);
  }, [data, size]);

  const nodeColor = (gn: GNode): string =>
    gn.node.node_type === 'publisher'
      ? rgb(PUBLISHER_COLOR)
      : rgb(getAgentColor(gn.node, colorBy, communityColors));

  const radius = (gn: GNode) => (gn.id === data.focal ? 9 : 6);
  const onlyFocal = data.nodes.length <= 1;

  return (
    // Absolute-fill (not h-full) so the canvas height never feeds back into the
    // flex row's content height — otherwise min-height:auto lets it grow without
    // bound (issue #31). The parent `.flex-1.relative` is the positioning context.
    <div ref={containerRef} className="absolute inset-0 bg-slate-50">
      {size.width > 0 && (
        <ForceGraph2D
          ref={fgRef}
          width={size.width}
          height={size.height}
          graphData={graphData}
          cooldownTicks={120}
          onEngineStop={fit}
          minZoom={0.4}
          maxZoom={6}
          nodeRelSize={6}
          nodeLabel={() => ''}
          linkColor={(l: object) => {
            const cfg = CONNECTION_TYPE_CONFIG[(l as GLink).edge.type as keyof typeof CONNECTION_TYPE_CONFIG];
            return cfg ? rgb(cfg.color) : 'rgba(148,163,184,0.6)';
          }}
          linkWidth={1.4}
          linkLabel={(l: object) => {
            const e = (l as GLink).edge;
            return e.relationship || e.evidence || e.type;
          }}
          onNodeClick={(n: object) => onNodeClick((n as GNode).node)}
          nodePointerAreaPaint={(n: object, color: string, ctx: CanvasRenderingContext2D) => {
            const gn = n as GNode;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(gn.x ?? 0, gn.y ?? 0, radius(gn) + 3, 0, 2 * Math.PI);
            ctx.fill();
          }}
          nodeCanvasObjectMode={() => 'replace'}
          nodeCanvasObject={(n: object, ctx: CanvasRenderingContext2D, scale: number) => {
            const gn = n as GNode;
            const isFocal = gn.id === data.focal;
            const r = radius(gn);
            const x = gn.x ?? 0;
            const y = gn.y ?? 0;
            // node
            ctx.beginPath();
            ctx.arc(x, y, r, 0, 2 * Math.PI);
            ctx.fillStyle = nodeColor(gn);
            ctx.fill();
            ctx.lineWidth = (isFocal ? 2.5 : 1) / scale;
            ctx.strokeStyle = isFocal ? '#111827' : '#ffffff';
            ctx.stroke();
            // label with a white halo for legibility
            const label = gn.node.display_name;
            const fontSize = Math.max((isFocal ? 13 : 11) / scale, 3);
            ctx.font = `${isFocal ? 600 : 400} ${fontSize}px sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            ctx.lineWidth = 3 / scale;
            ctx.strokeStyle = 'rgba(255,255,255,0.9)';
            ctx.strokeText(label, x, y + r + 1.5 / scale);
            ctx.fillStyle = '#1f2937';
            ctx.fillText(label, x, y + r + 1.5 / scale);
          }}
        />
      )}

      {/* Recenter / fit button — always a way back to the framed view */}
      <button
        onClick={fit}
        className="absolute top-3 right-3 z-10 bg-white/90 hover:bg-white border border-gray-300 rounded-lg shadow-sm px-2.5 py-1.5 text-xs font-medium text-gray-700 flex items-center gap-1"
        title="Fit graph to view"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M20.25 3.75v4.5m0-4.5h-4.5m4.5 0L15 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15m11.25 5.25v-4.5m0 4.5h-4.5m4.5 0L15 15" />
        </svg>
        Recenter
      </button>

      {/* Reading card: archetype badge (free) + optional AI portrait */}
      {shape && !onlyFocal && (
        <div className="absolute top-3 left-3 z-10 max-w-sm bg-white/95 backdrop-blur-sm border border-gray-200 rounded-xl shadow-md px-4 py-3">
          {!portrait ? (
            <>
              <div className="text-xs font-semibold text-indigo-600 uppercase tracking-wider">{shape.badge}</div>
              <p className="mt-1 text-sm text-gray-700 leading-snug">{shape.line}</p>
              {canInterpret && (
                <button
                  onClick={askAI}
                  disabled={portraitLoading}
                  className="mt-2 text-xs font-medium text-indigo-600 hover:text-indigo-800 disabled:opacity-50"
                >
                  {portraitLoading ? 'Reading the network…' : '✦ Interpret with AI'}
                </button>
              )}
              {portraitError && (
                <p className="mt-1 text-xs text-red-500">Interpretation failed — try again.</p>
              )}
            </>
          ) : (
            <>
              <div className="text-sm font-semibold text-gray-900">
                <bdi dir="auto">{portrait.epithet}</bdi>
              </div>
              <p className="mt-1 text-sm text-gray-700 leading-snug">
                <bdi dir="auto">{portrait.reading}</bdi>
              </p>
              <p className="mt-1.5 text-xs text-gray-500 leading-snug">
                {threadNode ? (
                  <button
                    onClick={() => onNodeClick(threadNode)}
                    className="text-indigo-600 hover:text-indigo-800 text-start"
                  >
                    → <bdi dir="auto">{portrait.next_thread}</bdi>
                  </button>
                ) : (
                  <>→ <bdi dir="auto">{portrait.next_thread}</bdi></>
                )}
              </p>
            </>
          )}
        </div>
      )}

      {onlyFocal && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <p className="text-sm text-gray-500 bg-white/85 px-4 py-2 rounded shadow text-center max-w-xs">
            No connections for this node under the current filters. Try enabling more
            connection types or lowering the confidence threshold.
          </p>
        </div>
      )}

      {data.meta.truncated && (
        <div className="absolute bottom-3 right-3 text-xs text-gray-600 bg-white/85 px-2 py-1 rounded shadow">
          Showing {data.meta.showing - 1} of {data.meta.total_neighbors} connections
        </div>
      )}
    </div>
  );
}
