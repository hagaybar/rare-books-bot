import { useMemo, useCallback, useRef } from 'react';
import MapGL, { NavigationControl } from 'react-map-gl/maplibre';
import { DeckGL } from '@deck.gl/react';
import { ArcLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import type { MapNode, MapEdge, ColorByMode } from '../../types/network';
import { CONNECTION_TYPE_CONFIG, getAgentColor } from '../../types/network';
import 'maplibre-gl/dist/maplibre-gl.css';

interface Props {
  nodes: MapNode[];
  edges: MapEdge[];
  selectedAgent: string | null;
  onAgentClick: (node: MapNode) => void;
  onBackgroundClick: () => void;
  isLoading: boolean;
  colorBy: ColorByMode;
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
  isLoading,
  colorBy,
}: Props) {
  // Track whether a deck.gl object was picked on this click
  const pickedRef = useRef(false);

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

  const scatterLayer = useMemo(
    () =>
      new ScatterplotLayer<MapNode>({
        id: 'agents',
        data: nodes,
        getPosition: (d) => jitteredPositions.get(d.agent_norm) ?? [d.lon ?? 0, d.lat ?? 0],
        getRadius: (d) => {
          const base = 4 + Math.min(d.connection_count / 10, 10);
          return base;
        },
        getFillColor: (d) => {
          const color = getAgentColor(d, colorBy);
          if (d.agent_norm === selectedAgent) return [...color, 255];
          if (selectedAgent && connectedAgents.has(d.agent_norm)) return [...color, 220];
          if (selectedAgent) return [156, 163, 175, 50];
          return [...color, 200];
        },
        getLineColor: (d) => {
          if (d.agent_norm === selectedAgent) return [255, 255, 255, 255];
          if (selectedAgent && connectedAgents.has(d.agent_norm)) return [255, 255, 255, 180];
          return [0, 0, 0, 0];
        },
        getLineWidth: (d) => {
          if (d.agent_norm === selectedAgent) return 2;
          if (selectedAgent && connectedAgents.has(d.agent_norm)) return 1;
          return 0;
        },
        stroked: true,
        lineWidthUnits: 'pixels',
        radiusUnits: 'pixels',
        pickable: true,
        onClick: (info) => {
          if (info.object) {
            pickedRef.current = true;
            onAgentClick(info.object);
          }
        },
        updateTriggers: {
          getRadius: [selectedAgent],
          getFillColor: [selectedAgent, colorBy],
          getLineColor: [selectedAgent],
          getLineWidth: [selectedAgent],
        },
      }),
    [nodes, selectedAgent, connectedAgents, onAgentClick, colorBy, jitteredPositions]
  );

  const arcLayer = useMemo(
    () =>
      new ArcLayer<MapEdge>({
        id: 'connections',
        data: edges,
        getSourcePosition: (d) => {
          const n = nodeMap.get(d.source);
          return [n?.lon ?? 0, n?.lat ?? 0];
        },
        getTargetPosition: (d) => {
          const n = nodeMap.get(d.target);
          return [n?.lon ?? 0, n?.lat ?? 0];
        },
        getSourceColor: (d) => {
          const config = CONNECTION_TYPE_CONFIG[d.type as keyof typeof CONNECTION_TYPE_CONFIG];
          const baseColor = config?.color ?? [156, 163, 175];
          const isHighlighted =
            selectedAgent &&
            (d.source === selectedAgent || d.target === selectedAgent);
          const opacity = selectedAgent
            ? isHighlighted
              ? Math.round(d.confidence * 255)
              : 25
            : Math.round(d.confidence * 200);
          return [...baseColor, opacity] as [number, number, number, number];
        },
        getTargetColor: (d) => {
          const config = CONNECTION_TYPE_CONFIG[d.type as keyof typeof CONNECTION_TYPE_CONFIG];
          const baseColor = config?.color ?? [156, 163, 175];
          const isHighlighted =
            selectedAgent &&
            (d.source === selectedAgent || d.target === selectedAgent);
          const opacity = selectedAgent
            ? isHighlighted
              ? Math.round(d.confidence * 255)
              : 25
            : Math.round(d.confidence * 200);
          return [...baseColor, opacity] as [number, number, number, number];
        },
        getWidth: (d) => {
          const config = CONNECTION_TYPE_CONFIG[d.type as keyof typeof CONNECTION_TYPE_CONFIG];
          const base = config?.width ?? 1;
          if (
            selectedAgent &&
            (d.source === selectedAgent || d.target === selectedAgent)
          )
            return base * 2;
          return base;
        },
        pickable: false,
        updateTriggers: {
          getSourceColor: selectedAgent,
          getTargetColor: selectedAgent,
          getWidth: selectedAgent,
        },
      }),
    [edges, nodeMap, selectedAgent]
  );

  const labelNodes = useMemo(() => {
    return [...nodes]
      .sort((a, b) => b.connection_count - a.connection_count)
      .slice(0, 15);
  }, [nodes]);

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
        outlineWidth: 3,
        outlineColor: [255, 255, 255, 200],
        billboard: false,
        sizeUnits: 'pixels',
      }),
    [labelNodes, jitteredPositions]
  );

  // Handle background clicks via the MapGL onClick (fires for all map clicks).
  // We use pickedRef to distinguish: if deck.gl picked an object, skip the background handler.
  const handleMapClick = useCallback(() => {
    if (pickedRef.current) {
      pickedRef.current = false;
      return;
    }
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
        layers={[arcLayer, scatterLayer, labelLayer]}
        getTooltip={({ object }: any) => {
          if (!object) return null;
          if ('agent_norm' in object) {
            const n = object as MapNode;
            const years =
              n.birth_year || n.death_year
                ? ` (${n.birth_year ?? '?'}\u2013${n.death_year ?? '?'})`
                : '';
            return {
              text: `${n.display_name}${years}\n${n.place_norm ?? ''}\n${n.connection_count} connections`,
            };
          }
          return null;
        }}
      >
        <MapGL mapStyle={MAP_STYLE} onClick={handleMapClick}>
          <NavigationControl position="top-left" />
        </MapGL>
      </DeckGL>
    </div>
  );
}
