import { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { fetchMapData, fetchAgentDetail, fetchPlaceDetail, fetchEgo, fetchPath } from '../api/network';
import { useNetworkStore } from '../stores/networkStore';
import MapView from '../components/network/MapView';
import EgoView from '../components/network/EgoView';
import Breadcrumbs from '../components/network/Breadcrumbs';
import PathFinder from '../components/network/PathFinder';
import ControlBar from '../components/network/ControlBar';
import AgentPanel from '../components/network/AgentPanel';
import PlacePanel from '../components/network/PlacePanel';
import Legend from '../components/network/Legend';
import type { MapNode } from '../types/network';

export default function Network() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [selectedPlace, setSelectedPlace] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const { connectionTypes, minConfidence, century, place, role, agentLimit, colorBy } =
    useNetworkStore();
  const [searchParams, setSearchParams] = useSearchParams();

  // Hydrate filters + selected agent from the URL once on mount (issue #24).
  useEffect(() => {
    const s = useNetworkStore.getState();
    const types = searchParams.get('types');
    if (types !== null) s.setConnectionTypes(types ? (types.split(',') as typeof connectionTypes) : []);
    const c = searchParams.get('century');
    if (c) s.setCentury(Number(c));
    const r = searchParams.get('role');
    if (r) s.setRole(r);
    const mc = searchParams.get('conf');
    if (mc) s.setMinConfidence(Number(mc));
    const lim = searchParams.get('limit');
    if (lim) s.setAgentLimit(Number(lim));
    const cb = searchParams.get('color');
    if (cb) s.setColorBy(cb as typeof colorBy);
    const agent = searchParams.get('agent');
    if (agent) setSelectedAgent(agent);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reflect filter + selection state back into the URL (shareable views).
  useEffect(() => {
    const next: Record<string, string> = {};
    if (connectionTypes.length) next.types = connectionTypes.join(',');
    if (century) next.century = String(century);
    if (role) next.role = role;
    if (minConfidence !== 0.5) next.conf = String(minConfidence);
    if (agentLimit !== 500) next.limit = String(agentLimit);
    if (colorBy !== 'century') next.color = colorBy;
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionTypes, century, role, minConfidence, agentLimit, colorBy]);

  const {
    data: mapData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['network-map', connectionTypes, minConfidence, century, place, role, agentLimit],
    queryFn: () =>
      fetchMapData({
        connectionTypes,
        minConfidence,
        century,
        place,
        role,
        limit: agentLimit,
      }),
    placeholderData: (prev) => prev, // keep previous data while loading (avoids flash)
  });

  const { data: agentDetail } = useQuery({
    queryKey: ['network-agent', selectedAgent],
    queryFn: () => fetchAgentDetail(selectedAgent!),
    enabled: !!selectedAgent,
  });

  const { data: placeDetail } = useQuery({
    queryKey: ['network-place', selectedPlace],
    queryFn: () => fetchPlaceDetail(selectedPlace!),
    enabled: !!selectedPlace,
  });

  // Selecting an agent and a place are mutually exclusive in the side panel.
  const selectAgent = (norm: string) => { setSelectedPlace(null); setSelectedAgent(norm); };
  const selectPlace = (norm: string) => { setSelectedAgent(null); setSelectedPlace(norm); };

  // Ego-network mode (issue #31)
  const viewMode = useNetworkStore((s) => s.viewMode);
  const focusAgent = useNetworkStore((s) => s.focusAgent);
  const enterEgo = useNetworkStore((s) => s.enterEgo);
  const pushEgo = useNetworkStore((s) => s.pushEgo);
  const setViewMode = useNetworkStore((s) => s.setViewMode);

  // Default focal node when entering Network mode with nothing selected:
  // the most-connected node currently on the map (decision A).
  const topNode = useMemo(() => {
    const ns = mapData?.nodes ?? [];
    return ns.length ? ns.reduce((a, b) => (b.connection_count > a.connection_count ? b : a)) : null;
  }, [mapData]);

  const { data: egoData, isLoading: egoLoading } = useQuery({
    queryKey: ['network-ego', focusAgent, connectionTypes, minConfidence],
    // Cap the ring at a legible size by default; the panel shows "X of N".
    queryFn: () => fetchEgo(focusAgent!, { connectionTypes, minConfidence, limit: 24 }),
    enabled: viewMode === 'ego' && !!focusAgent,
    placeholderData: (prev) => prev,
  });

  const nameFor = (norm: string) =>
    mapData?.nodes.find((x) => x.agent_norm === norm)?.display_name
    ?? (agentDetail?.agent_norm === norm ? agentDetail.display_name : undefined)
    ?? norm;

  const goNetwork = () => {
    const start = selectedAgent
      ? { agent_norm: selectedAgent, display_name: nameFor(selectedAgent) }
      : focusAgent
      ? { agent_norm: focusAgent, display_name: nameFor(focusAgent) }
      : topNode
      ? { agent_norm: topNode.agent_norm, display_name: topNode.display_name }
      : null;
    if (start) enterEgo(start);
    else setViewMode('ego');
  };

  const goMap = () => setViewMode('map');

  const handleEgoNodeClick = (node: MapNode) => {
    selectAgent(node.agent_norm);
    pushEgo({ agent_norm: node.agent_norm, display_name: node.display_name });
  };

  const handleExplore = (norm: string, displayName: string) =>
    enterEgo({ agent_norm: norm, display_name: displayName });

  // Pathfinding (issue #33): from the current ego focal to a chosen target.
  const [pathTarget, setPathTarget] = useState<string | null>(null);
  useEffect(() => { setPathTarget(null); }, [focusAgent]); // stale path on re-center
  const { data: pathData, isFetching: pathLoading } = useQuery({
    queryKey: ['network-path', focusAgent, pathTarget, connectionTypes, minConfidence],
    queryFn: () => fetchPath(focusAgent!, pathTarget!, { connectionTypes, minConfidence }),
    enabled: viewMode === 'ego' && !!focusAgent && !!pathTarget,
  });

  // Show toast on API error (map retains last successful data via placeholderData)
  useEffect(() => {
    if (error) toast.error(`Map data error: ${String(error)}`);
  }, [error]);

  // Keep ?agent= in sync with the selection.
  useEffect(() => {
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev);
      if (selectedAgent) p.set('agent', selectedAgent);
      else p.delete('agent');
      return p;
    }, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAgent]);

  const handleAgentClick = (node: MapNode) => {
    selectAgent(node.agent_norm);
  };

  const handleClosePanel = () => {
    setSelectedAgent(null);
    setSelectedPlace(null);
  };

  // Count active filters for the badge
  const activeFilterCount =
    (century ? 1 : 0) +
    (role ? 1 : 0) +
    connectionTypes.length;

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Page header — compact on mobile */}
      <div className="px-4 pt-3 pb-1 flex items-center justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-gray-900 md:text-xl text-base truncate">
            Scholarly Network Map
          </h1>
          <p className="text-sm text-gray-500 hidden md:block">
            Explore connections between {mapData?.meta.total_agents?.toLocaleString() ?? '...'} historical figures across Europe and the Middle East
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0 ml-2">
        {/* Map / Network view toggle (issue #31) */}
        <div className="inline-flex rounded-lg border border-gray-300 overflow-hidden text-sm" role="group" aria-label="View mode">
          <button
            onClick={goMap}
            aria-pressed={viewMode === 'map'}
            className={`px-3 py-1.5 ${viewMode === 'map' ? 'bg-blue-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'}`}
          >
            Map
          </button>
          <button
            onClick={goNetwork}
            aria-pressed={viewMode === 'ego'}
            className={`px-3 py-1.5 border-l border-gray-300 ${viewMode === 'ego' ? 'bg-blue-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'}`}
          >
            Network
          </button>
        </div>

        {/* Mobile filter toggle button */}
        <button
          onClick={() => setFiltersOpen(!filtersOpen)}
          className="md:hidden flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg border border-gray-300 bg-white text-gray-700 active:bg-gray-100 shrink-0"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75" />
          </svg>
          Filters
          {activeFilterCount > 0 && (
            <span className="bg-blue-600 text-white text-[10px] font-bold rounded-full w-5 h-5 flex items-center justify-center">
              {activeFilterCount}
            </span>
          )}
        </button>
        </div>
      </div>

      {/* Desktop: always visible. Mobile: collapsible bottom sheet */}
      <div className="hidden md:block">
        <ControlBar onAgentSelect={setSelectedAgent} />
      </div>

      {/* Mobile filter bottom sheet */}
      {filtersOpen && (
        <div className="md:hidden fixed inset-0 z-30" onClick={() => setFiltersOpen(false)}>
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/30" />
          {/* Sheet */}
          <div
            className="absolute bottom-14 left-0 right-0 bg-white rounded-t-2xl shadow-xl max-h-[70vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 pt-3 pb-2 border-b border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900">Filters</h3>
              <button
                onClick={() => setFiltersOpen(false)}
                className="text-gray-400 hover:text-gray-600 p-1"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-4">
              <ControlBar mobile onAgentSelect={(norm) => { setSelectedAgent(norm); setFiltersOpen(false); }} />
            </div>
          </div>
        </div>
      )}

      {/* Active filter chips on mobile (shown when filters panel is closed) */}
      {!filtersOpen && activeFilterCount > 0 && (
        <div className="md:hidden flex gap-2 px-4 py-1.5 overflow-x-auto no-scrollbar">
          {century && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded-full whitespace-nowrap">
              {century}th c.
              <button onClick={() => useNetworkStore.getState().setCentury(null)} className="hover:text-blue-900">&times;</button>
            </span>
          )}
          {role && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded-full whitespace-nowrap capitalize">
              {role}
              <button onClick={() => useNetworkStore.getState().setRole(null)} className="hover:text-blue-900">&times;</button>
            </span>
          )}
          {connectionTypes.map((ct) => (
            <span key={ct} className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-50 text-purple-700 text-xs rounded-full whitespace-nowrap">
              {ct.replace(/_/g, ' ')}
              <button onClick={() => useNetworkStore.getState().toggleConnectionType(ct)} className="hover:text-purple-900">&times;</button>
            </span>
          ))}
        </div>
      )}

      {viewMode === 'ego' && <Breadcrumbs />}
      {viewMode === 'ego' && focusAgent && (
        <PathFinder
          sourceName={nameFor(focusAgent)}
          path={pathTarget ? pathData ?? null : null}
          loading={pathLoading}
          onSelectTarget={setPathTarget}
          onClear={() => setPathTarget(null)}
          onNodeClick={(norm, displayName) => { selectAgent(norm); pushEgo({ agent_norm: norm, display_name: displayName }); }}
        />
      )}

      <div className="flex flex-1 relative overflow-hidden min-h-0">
        <div className="flex-1 relative min-h-0">
          {viewMode === 'ego' ? (
            egoData ? (
              <EgoView
                data={egoData}
                colorBy={colorBy}
                communities={mapData?.meta.communities}
                onNodeClick={handleEgoNodeClick}
              />
            ) : (
              <div className="absolute inset-0 flex items-center justify-center text-gray-500 text-sm">
                {egoLoading ? 'Loading network…' : 'Search or pick a node to explore its connections.'}
              </div>
            )
          ) : (
            <MapView
              nodes={mapData?.nodes ?? []}
              edges={mapData?.edges ?? []}
              selectedAgent={selectedAgent}
              onAgentClick={handleAgentClick}
              onBackgroundClick={handleClosePanel}
              onPlaceSelect={selectPlace}
              isLoading={isLoading}
              colorBy={colorBy}
              communities={mapData?.meta.communities}
            />
          )}
          <Legend colorBy={colorBy} activeTypes={connectionTypes} communities={mapData?.meta.communities} />
          {/* Empty results overlay (map mode only) */}
          {viewMode === 'map' && !isLoading && mapData && mapData.nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none">
              <p className="text-gray-500 bg-white/80 px-4 py-2 rounded shadow">
                No agents match these filters. Try broadening your search.
              </p>
            </div>
          )}
        </div>

        {/* Desktop agent panel — sidebar */}
        {selectedAgent && agentDetail && (
          <div className="hidden md:block">
            <AgentPanel agent={agentDetail} onClose={handleClosePanel} onAgentClick={selectAgent} onPlaceSelect={selectPlace} onExplore={handleExplore} />
          </div>
        )}
        {/* Desktop place panel — sidebar */}
        {selectedPlace && placeDetail && (
          <div className="hidden md:block">
            <PlacePanel place={placeDetail} onClose={handleClosePanel} />
          </div>
        )}
      </div>

      {/* Mobile place panel — bottom sheet */}
      {selectedPlace && placeDetail && (
        <div className="md:hidden fixed inset-0 z-30" onClick={handleClosePanel}>
          <div className="absolute inset-0 bg-black/30" />
          <div className="absolute bottom-14 left-0 right-0 bg-white rounded-t-2xl shadow-xl max-h-[75vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-center pt-2 pb-1"><div className="w-10 h-1 bg-gray-300 rounded-full" /></div>
            <PlacePanel place={placeDetail} onClose={handleClosePanel} mobile />
          </div>
        </div>
      )}

      {/* Mobile agent panel — bottom sheet */}
      {selectedAgent && agentDetail && (
        <div className="md:hidden fixed inset-0 z-30" onClick={handleClosePanel}>
          <div className="absolute inset-0 bg-black/30" />
          <div
            className="absolute bottom-14 left-0 right-0 bg-white rounded-t-2xl shadow-xl max-h-[75vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Drag handle */}
            <div className="flex justify-center pt-2 pb-1">
              <div className="w-10 h-1 bg-gray-300 rounded-full" />
            </div>
            <AgentPanel agent={agentDetail} onClose={handleClosePanel} onAgentClick={selectAgent} onPlaceSelect={selectPlace} onExplore={(n, d) => { handleExplore(n, d); handleClosePanel(); }} mobile />
          </div>
        </div>
      )}

      {/* Footer — compact on mobile */}
      <div className="px-4 py-2 bg-gray-50 border-t text-xs md:text-sm text-gray-500 flex justify-between">
        <span className="truncate">
          {mapData
            ? connectionTypes.length === 0
              ? `${mapData.meta.showing}/${mapData.meta.total_agents} agents`
              : `${mapData.meta.showing}/${mapData.meta.total_agents} agents \u00B7 ${mapData.meta.total_edges} connections`
            : 'Loading...'}
        </span>
        {isLoading && <span className="text-blue-500 shrink-0 ml-2">Updating...</span>}
      </div>
    </div>
  );
}
