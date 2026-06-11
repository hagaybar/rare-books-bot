import { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import type { MapNode, MapEdge, ColorByMode, EgoResponse } from '../../types/network';
import {
  getAgentColor, buildCommunityColorMap, CONNECTION_TYPE_CONFIG, PUBLISHER_COLOR,
} from '../../types/network';

interface Props {
  data: EgoResponse;
  colorBy: ColorByMode;
  communities?: string[];
  onNodeClick: (node: MapNode) => void;
}

interface GNode { id: string; node: MapNode; x?: number; y?: number }
interface GLink { source: string; target: string; edge: MapEdge }

const rgb = (c: [number, number, number]) => `rgb(${c[0]},${c[1]},${c[2]})`;

/** Force-directed 1-hop ego graph (issue #31). Non-geographic peer of MapView. */
export default function EgoView({ data, colorBy, communities, onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const communityColors = useMemo(() => buildCommunityColorMap(communities ?? []), [communities]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setSize({ width: el.clientWidth, height: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const graphData = useMemo(() => ({
    nodes: data.nodes.map((n): GNode => ({ id: n.agent_norm, node: n })),
    links: data.edges.map((e): GLink => ({ source: e.source, target: e.target, edge: e })),
  }), [data]);

  const nodeColor = (gn: GNode): string =>
    gn.node.node_type === 'publisher'
      ? rgb(PUBLISHER_COLOR)
      : rgb(getAgentColor(gn.node, colorBy, communityColors));

  const radius = (gn: GNode) => (gn.id === data.focal ? 7 : 4);

  const onlyFocal = data.nodes.length <= 1;

  return (
    <div ref={containerRef} className="w-full h-full bg-slate-50 relative">
      {size.width > 0 && (
        <ForceGraph2D
          ref={fgRef}
          width={size.width}
          height={size.height}
          graphData={graphData}
          cooldownTicks={100}
          onEngineStop={() => fgRef.current?.zoomToFit(400, 70)}
          nodeRelSize={4}
          nodeLabel={(n: object) => (n as GNode).node.display_name}
          linkColor={(l: object) => {
            const cfg = CONNECTION_TYPE_CONFIG[(l as GLink).edge.type as keyof typeof CONNECTION_TYPE_CONFIG];
            return cfg ? rgb(cfg.color) : 'rgba(148,163,184,0.6)';
          }}
          linkWidth={1.2}
          linkLabel={(l: object) => {
            const e = (l as GLink).edge;
            return e.relationship || e.evidence || e.type;
          }}
          onNodeClick={(n: object) => onNodeClick((n as GNode).node)}
          nodePointerAreaPaint={(n: object, color: string, ctx: CanvasRenderingContext2D) => {
            const gn = n as GNode;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(gn.x ?? 0, gn.y ?? 0, radius(gn) + 2, 0, 2 * Math.PI);
            ctx.fill();
          }}
          nodeCanvasObjectMode={() => 'replace'}
          nodeCanvasObject={(n: object, ctx: CanvasRenderingContext2D, scale: number) => {
            const gn = n as GNode;
            const isFocal = gn.id === data.focal;
            const r = radius(gn);
            ctx.beginPath();
            ctx.arc(gn.x ?? 0, gn.y ?? 0, r, 0, 2 * Math.PI);
            ctx.fillStyle = nodeColor(gn);
            ctx.fill();
            if (isFocal) {
              ctx.lineWidth = 2 / scale;
              ctx.strokeStyle = '#111827';
              ctx.stroke();
            }
            // Label: always for focal, otherwise once zoomed in (keeps it legible)
            if (isFocal || scale > 1.3) {
              const fontSize = Math.max(11 / scale, 2);
              ctx.font = `${isFocal ? 600 : 400} ${fontSize}px sans-serif`;
              ctx.textAlign = 'center';
              ctx.textBaseline = 'top';
              ctx.fillStyle = '#374151';
              ctx.fillText(gn.node.display_name, gn.x ?? 0, (gn.y ?? 0) + r + 1);
            }
          }}
        />
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
