import { useMemo, useCallback, useRef } from 'react';
import MapGL, { NavigationControl } from 'react-map-gl/maplibre';
import { DeckGL } from '@deck.gl/react';
import { ArcLayer, ScatterplotLayer } from '@deck.gl/layers';
import type { MapNode, MapEdge } from '../../types/network';
import { CONNECTION_TYPE_CONFIG } from '../../types/network';
import 'maplibre-gl/dist/maplibre-gl.css';

interface Props {
  nodes: MapNode[];
  edges: MapEdge[];
  selectedAgent: string | null;
  onAgentClick: (node: MapNode) => void;
  onBackgroundClick: () => void;
  isLoading: boolean;
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

  const scatterLayer = useMemo(
    () =>
      new ScatterplotLayer<MapNode>({
        id: 'agents',
        data: nodes,
        getPosition: (d) => [d.lon ?? 0, d.lat ?? 0],
        getRadius: (d) => {
          if (d.agent_norm === selectedAgent) return 12;
          if (selectedAgent && connectedAgents.has(d.agent_norm)) return 8;
          return 6;
        },
        getFillColor: (d) => {
          if (d.agent_norm === selectedAgent) return [59, 130, 246, 255];
          if (selectedAgent && connectedAgents.has(d.agent_norm))
            return [59, 130, 246, 200];
          if (selectedAgent) return [156, 163, 175, 60];
          return [59, 130, 246, 180];
        },
        radiusUnits: 'pixels',
        pickable: true,
        onClick: (info) => {
          if (info.object) {
            pickedRef.current = true;
            onAgentClick(info.object);
          }
        },
        updateTriggers: {
          getRadius: selectedAgent,
          getFillColor: selectedAgent,
        },
      }),
    [nodes, selectedAgent, connectedAgents, onAgentClick]
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
        layers={[arcLayer, scatterLayer]}
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
