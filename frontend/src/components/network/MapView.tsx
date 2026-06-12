import { useMemo, useCallback, useRef, useState } from 'react';
import MapGL, { NavigationControl } from 'react-map-gl/maplibre';
import { DeckGL } from '@deck.gl/react';
import { ArcLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import type { MapNode, MapEdge, ColorByMode, PlaceMarker, MapLayer } from '../../types/network';
import { CONNECTION_TYPE_CONFIG, getAgentColor, buildCommunityColorMap } from '../../types/network';
import 'maplibre-gl/dist/maplibre-gl.css';

interface Props {
  nodes: MapNode[];
  edges: MapEdge[];
  places?: PlaceMarker[];
  mapLayer?: MapLayer;
  selectedAgent: string | null;
  onAgentClick: (node: MapNode) => void;
  onBackgroundClick: () => void;
  onPlaceSelect?: (placeNorm: string) => void;
  isLoading: boolean;
  colorBy: ColorByMode;
  communities?: string[];
}

const INITIAL_VIEW_STATE = {
  latitude: 40,
  longitude: 15,
  zoom: 4,
  pitch: 0,
  bearing: 0,
};

const MAP_STYLE = 'https://tiles.openfreemap.org/styles/positron';

export default function MapView({
  nodes,
  edges,
  selectedAgent,
  onAgentClick,
  onBackgroundClick,
  onPlaceSelect,
  isLoading,
  colorBy,
  communities,
  places,
  mapLayer = 'people',
}: Props) {
  // Track whether a deck.gl object was picked on this click
  const pickedRef = useRef(false);
  const communityColors = useMemo(
    () => buildCommunityColorMap(communities ?? []),
    [communities]
  );
  // Popover for a clicked stack of co-located agents (issue #23)
  const [stack, setStack] = useState<{ x: number; y: number; nodes: MapNode[] } | null>(null);
  // Rounded zoom drives zoom-aware label density (issue #35) — rounding keeps
  // pans from re-rendering and only re-tiers on a whole zoom-level change.
  const [zoom, setZoom] = useState(Math.round(INITIAL_VIEW_STATE.zoom));

  // Build a lookup for node positions (use JavaScript's built-in Map, not the react-map-gl component)
  const nodeMap = useMemo(() => {
    const m = new globalThis.Map<string, MapNode>();
    for (const n of nodes) m.set(n.agent_norm, n);
    return m;
  }, [nodes]);

  // Determine which agents are connected to the selected agent
  const connectedAgents = useMemo(() => {
    if (!selectedAgent) return new Set<string>();
    const connected = new Set<string>();
    for (const e of edges) {
      if (e.source === selectedAgent) connected.add(e.target);
      if (e.target === selectedAgent) connected.add(e.source);
    }
    return connected;
  }, [edges, selectedAgent]);

  // Deterministic jitter for agents sharing the same city
  const jitteredPositions = useMemo(() => {
    const cityGroups = new globalThis.Map<string, MapNode[]>();
    for (const n of nodes) {
      const key = `${n.lat},${n.lon}`;
      if (!cityGroups.has(key)) cityGroups.set(key, []);
      cityGroups.get(key)!.push(n);
    }
    const positions = new globalThis.Map<string, [number, number]>();
    for (const [, group] of cityGroups) {
      if (group.length === 1) {
        positions.set(group[0].agent_norm, [group[0].lon ?? 0, group[0].lat ?? 0]);
      } else {
        const cx = group[0].lon ?? 0;
        const cy = group[0].lat ?? 0;
        const radius = Math.min(0.03 * Math.sqrt(group.length), 0.3);
        group.forEach((n, i) => {
          const angle = (2 * Math.PI * i) / group.length;
          positions.set(n.agent_norm, [
            cx + radius * Math.cos(angle),
            cy + radius * Math.sin(angle),
          ]);
        });
      }
    }
    return positions;
  }, [nodes]);

  // Co-located agents per coordinate (issue #23)
  const coLocated = useMemo(() => {
    const m = new globalThis.Map<string, MapNode[]>();
    for (const n of nodes) {
      const key = `${n.lat},${n.lon}`;
      if (!m.has(key)) m.set(key, []);
      m.get(key)!.push(n);
    }
    return m;
  }, [nodes]);

  const scatterLayer = useMemo(
    () =>
      new ScatterplotLayer<MapNode>({
        id: 'agents',
        data: nodes,
        getPosition: (d) => jitteredPositions.get(d.agent_norm) ?? [d.lon ?? 0, d.lat ?? 0],
        getRadius: (d) => {
          const base = 4 + Math.min(d.connection_count / 10, 10);
          return d.node_type === 'publisher' ? base + 4 : base;
        },
        getFillColor: (d) => {
          const color = getAgentColor(d, colorBy, communityColors);
          if (d.agent_norm === selectedAgent) return [...color, 255];
          if (selectedAgent && connectedAgents.has(d.agent_norm)) return [...color, 220];
          if (selectedAgent) return [156, 163, 175, 50];
          return [...color, 200];
        },
        getLineColor: (d) => {
          if (d.agent_norm === selectedAgent) return [255, 255, 255, 255];
          if (selectedAgent && connectedAgents.has(d.agent_norm)) return [255, 255, 255, 180];
          if (d.node_type === 'publisher') return [120, 53, 15, 230];
          return [0, 0, 0, 0];
        },
        getLineWidth: (d) => {
          if (d.agent_norm === selectedAgent) return 2;
          if (selectedAgent && connectedAgents.has(d.agent_norm)) return 1;
          return d.node_type === 'publisher' ? 1.5 : 0;
        },
        stroked: true,
        lineWidthUnits: 'pixels',
        radiusUnits: 'pixels',
        pickable: true,
        onClick: (info) => {
          if (info.object) {
            pickedRef.current = true;
            const here = coLocated.get(`${info.object.lat},${info.object.lon}`) ?? [info.object];
            if (here.length > 1) {
              setStack({ x: info.x, y: info.y, nodes: here });
            } else {
              setStack(null);
              onAgentClick(info.object);
            }
          }
        },
        updateTriggers: {
          getRadius: [selectedAgent],
          getFillColor: [selectedAgent, colorBy, communityColors],
          getLineColor: [selectedAgent],
          getLineWidth: [selectedAgent],
        },
      }),
    [nodes, selectedAgent, connectedAgents, onAgentClick, colorBy, jitteredPositions, coLocated, communityColors]
  );

  const arcLayer = useMemo(
    () =>
      new ArcLayer<MapEdge>({
        id: 'connections',
        data: edges,
        getSourcePosition: (d) => {
          return jitteredPositions.get(d.source) ?? (() => {
            const n = nodeMap.get(d.source);
            return [n?.lon ?? 0, n?.lat ?? 0] as [number, number];
          })();
        },
        getTargetPosition: (d) => {
          return jitteredPositions.get(d.target) ?? (() => {
            const n = nodeMap.get(d.target);
            return [n?.lon ?? 0, n?.lat ?? 0] as [number, number];
          })();
        },
        getSourceColor: (d) => {
          const config = CONNECTION_TYPE_CONFIG[d.type as keyof typeof CONNECTION_TYPE_CONFIG];
          const baseColor = config?.color ?? [156, 163, 175];
          const isHighlighted =
            selectedAgent &&
            (d.source === selectedAgent || d.target === selectedAgent);
          let opacity: number;
          if (selectedAgent) {
            opacity = isHighlighted ? Math.round(d.confidence * 255) : 25;
          } else {
            opacity = d.confidence >= 0.8 ? 200 : d.confidence >= 0.6 ? 130 : 60;
          }
          return [...baseColor, opacity] as [number, number, number, number];
        },
        getTargetColor: (d) => {
          const config = CONNECTION_TYPE_CONFIG[d.type as keyof typeof CONNECTION_TYPE_CONFIG];
          const baseColor = config?.color ?? [156, 163, 175];
          const isHighlighted =
            selectedAgent &&
            (d.source === selectedAgent || d.target === selectedAgent);
          let opacity: number;
          if (selectedAgent) {
            opacity = isHighlighted ? Math.round(d.confidence * 255) : 25;
          } else {
            opacity = d.confidence >= 0.8 ? 200 : d.confidence >= 0.6 ? 130 : 60;
          }
          return [...baseColor, opacity] as [number, number, number, number];
        },
        getWidth: (d) => {
          const base = d.confidence >= 0.8 ? 3 : d.confidence >= 0.6 ? 2 : 1;
          if (
            selectedAgent &&
            (d.source === selectedAgent || d.target === selectedAgent)
          )
            return base * 2;
          return base;
        },
        pickable: true,
        updateTriggers: {
          getSourceColor: selectedAgent,
          getTargetColor: selectedAgent,
          getWidth: selectedAgent,
        },
      }),
    [edges, nodeMap, selectedAgent, jitteredPositions]
  );

  // Zoom-aware label density (issue #35): publishers always labelled; people
  // labels grow as you zoom in, so the full node set stays readable without an
  // arbitrary node cap. Always sorted by connection_count so the most important
  // names surface first.
  const peopleLabelCount = zoom <= 4 ? 10 : zoom === 5 ? 24 : zoom === 6 ? 50 : zoom === 7 ? 90 : 150;
  const labelNodes = useMemo(() => {
    const publishers = nodes.filter((n) => n.node_type === 'publisher');
    const people = nodes
      .filter((n) => n.node_type !== 'publisher')
      .sort((a, b) => b.connection_count - a.connection_count)
      .slice(0, peopleLabelCount);
    return [...publishers, ...people];
  }, [nodes, peopleLabelCount]);

  const labelLayer = useMemo(
    () =>
      new TextLayer<MapNode>({
        id: 'labels',
        data: labelNodes,
        getPosition: (d) => jitteredPositions.get(d.agent_norm) ?? [d.lon ?? 0, d.lat ?? 0],
        getText: (d) => d.display_name,
        getSize: 12,
        getColor: [50, 50, 50, 220],
        getAngle: 0,
        getTextAnchor: 'start',
        getAlignmentBaseline: 'center',
        getPixelOffset: [10, 0],
        fontFamily: 'Inter, system-ui, sans-serif',
        fontWeight: 600,
        characterSet: 'auto',
        outlineWidth: 3,
        outlineColor: [255, 255, 255, 200],
        billboard: false,
        sizeUnits: 'pixels',
      }),
    [labelNodes, jitteredPositions]
  );

  // ---- Place-first "cities" layer: one circle per printing city, sized by holdings ----
  const cityData = places ?? [];
  const cityRadius = (p: PlaceMarker) => 5 + Math.sqrt(p.record_count) * 1.9;
  const cityLayer = useMemo(
    () =>
      new ScatterplotLayer<PlaceMarker>({
        id: 'cities',
        data: cityData,
        getPosition: (d) => [d.lon, d.lat],
        getRadius: cityRadius,
        radiusUnits: 'pixels',
        getFillColor: [37, 99, 235, 180],
        getLineColor: [255, 255, 255, 230],
        getLineWidth: 1.5,
        lineWidthUnits: 'pixels',
        stroked: true,
        pickable: true,
        onClick: (info) => {
          if (info.object) {
            pickedRef.current = true;
            onPlaceSelect?.(info.object.place_norm);
          }
        },
      }),
    [cityData, onPlaceSelect]
  );

  // City labels: "City (N)", denser as you zoom in (avoids early clutter).
  const cityLabelData = useMemo(() => {
    const sorted = [...cityData].sort((a, b) => b.record_count - a.record_count);
    const count = zoom <= 3 ? 8 : zoom <= 4 ? 14 : zoom <= 5 ? 30 : zoom <= 6 ? 60 : sorted.length;
    return sorted.slice(0, count);
  }, [cityData, zoom]);
  const cityLabelLayer = useMemo(
    () =>
      new TextLayer<PlaceMarker>({
        id: 'city-labels',
        data: cityLabelData,
        getPosition: (d) => [d.lon, d.lat],
        getText: (d) => {
          const name = d.place_norm; // normalized — place_display is the raw title-page wording
          const cap = name.charAt(0).toUpperCase() + name.slice(1);
          return `${cap} (${d.record_count})`;
        },
        getSize: 12,
        getColor: [30, 41, 59, 235],
        getTextAnchor: 'middle',
        getAlignmentBaseline: 'top',
        getPixelOffset: (d: PlaceMarker) => [0, cityRadius(d) + 2],
        fontFamily: 'Inter, system-ui, sans-serif',
        fontWeight: 600,
        characterSet: 'auto',
        outlineWidth: 3,
        outlineColor: [255, 255, 255, 230],
        billboard: false,
        sizeUnits: 'pixels',
      }),
    [cityLabelData]
  );

  // Handle background clicks via the MapGL onClick (fires for all map clicks).
  // We use pickedRef to distinguish: if deck.gl picked an object, skip the background handler.
  const handleMapClick = useCallback(() => {
    if (pickedRef.current) {
      pickedRef.current = false;
      return;
    }
    setStack(null);
    onBackgroundClick();
  }, [onBackgroundClick]);

  return (
    <div className="w-full h-full relative">
      {isLoading && nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center z-10 bg-white/50">
          <div className="text-gray-500">Loading map data...</div>
        </div>
      )}
      <DeckGL
        initialViewState={INITIAL_VIEW_STATE}
        controller={true}
        onViewStateChange={({ viewState }: any) => {
          const z = Math.round(viewState.zoom);
          setZoom((prev) => (prev === z ? prev : z)); // only re-tier on level change
        }}
        layers={mapLayer === 'cities' ? [cityLayer, cityLabelLayer] : [arcLayer, scatterLayer, labelLayer]}
        getTooltip={({ object }: any) => {
          if (!object) return null;
          if ('record_count' in object && 'place_norm' in object && !('agent_norm' in object)) {
            const p = object as PlaceMarker;
            const span = p.year_min && p.year_max ? `\n${p.year_min}–${p.year_max}` : '';
            return { text: `${p.place_norm.charAt(0).toUpperCase() + p.place_norm.slice(1)}\n${p.record_count} books · ${p.agent_count} people${span}\nClick to see what was printed here` };
          }
          if ('agent_norm' in object) {
            const n = object as MapNode;
            const years =
              n.birth_year || n.death_year
                ? ` (${n.birth_year ?? '?'}\u2013${n.death_year ?? '?'})`
                : '';
            const kind = n.node_type === 'publisher' ? 'Printing house\n' : '';
            return {
              text: `${kind}${n.display_name}${years}\n${n.place_norm ?? ''}\n${n.connection_count} connections\u00B7 ${n.record_count} records`,
            };
          }
          if ('source' in object && 'target' in object) {
            const e = object as MapEdge;
            const cfg = CONNECTION_TYPE_CONFIG[e.type as keyof typeof CONNECTION_TYPE_CONFIG];
            const why = e.relationship || e.evidence || '';
            return {
              text: `${cfg?.label ?? e.type}\u2003confidence ${Math.round(e.confidence * 100)}%${why ? '\n' + why : ''}`,
            };
          }
          return null;
        }}
      >
        <MapGL mapStyle={MAP_STYLE} onClick={handleMapClick}>
          <NavigationControl position="top-left" />
        </MapGL>
      </DeckGL>

      {/* Stacked-agents popover (issue #23) */}
      {stack && (
        <div
          className="absolute z-20 bg-white rounded-lg shadow-xl border border-gray-200 text-sm w-64 max-h-72 overflow-hidden flex flex-col"
          style={{ left: Math.min(stack.x + 8, 600), top: Math.min(stack.y + 8, 400) }}
        >
          <div className="px-3 py-2 border-b flex items-center justify-between bg-gray-50">
            <span className="font-medium text-gray-700 capitalize truncate" dir="auto">
              {stack.nodes[0].place_norm ?? 'This location'} — {stack.nodes.length} agents
            </span>
            <button onClick={() => setStack(null)} className="text-gray-400 hover:text-gray-600 ml-2 leading-none">&times;</button>
          </div>
          {onPlaceSelect && stack.nodes[0].place_norm && (
            <button
              onClick={() => { onPlaceSelect(stack.nodes[0].place_norm!); setStack(null); }}
              className="px-3 py-2 text-left text-blue-600 hover:bg-blue-50 border-b text-xs"
            >
              📚 Books printed in {stack.nodes[0].place_norm} &rarr;
            </button>
          )}
          <ul className="overflow-y-auto">
            {stack.nodes
              .slice()
              .sort((a, b) => b.connection_count - a.connection_count)
              .map((n) => (
                <li key={n.agent_norm}>
                  <button
                    onClick={() => { onAgentClick(n); setStack(null); }}
                    className="w-full text-left px-3 py-1.5 hover:bg-gray-50 flex justify-between items-center gap-2"
                  >
                    <span className="truncate" dir="auto">{n.display_name}</span>
                    <span className="text-xs text-gray-400 shrink-0">{n.connection_count}</span>
                  </button>
                </li>
              ))}
          </ul>
        </div>
      )}
    </div>
  );
}
