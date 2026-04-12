import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { fetchMapData, fetchAgentDetail } from '../api/network';
import { useNetworkStore } from '../stores/networkStore';
import MapView from '../components/network/MapView';
import ControlBar from '../components/network/ControlBar';
import AgentPanel from '../components/network/AgentPanel';
import Legend from '../components/network/Legend';
import type { MapNode } from '../types/network';

export default function Network() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const { connectionTypes, minConfidence, century, place, role, agentLimit, colorBy } =
    useNetworkStore();

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

  // Show toast on API error (map retains last successful data via placeholderData)
  useEffect(() => {
    if (error) toast.error(`Map data error: ${String(error)}`);
  }, [error]);

  const handleAgentClick = (node: MapNode) => {
    setSelectedAgent(node.agent_norm);
  };

  const handleClosePanel = () => {
    setSelectedAgent(null);
  };

  // Count active filters for the badge
  const activeFilterCount =
    (century ? 1 : 0) +
    (role ? 1 : 0) +
    connectionTypes.length;

  return (
    <div className="flex flex-col h-full">
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

        {/* Mobile filter toggle button */}
        <button
          onClick={() => setFiltersOpen(!filtersOpen)}
          className="md:hidden flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg border border-gray-300 bg-white text-gray-700 active:bg-gray-100 shrink-0 ml-2"
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

      <div className="flex flex-1 relative overflow-hidden">
        <div className="flex-1 relative">
          <MapView
            nodes={mapData?.nodes ?? []}
            edges={mapData?.edges ?? []}
            selectedAgent={selectedAgent}
            onAgentClick={handleAgentClick}
            onBackgroundClick={handleClosePanel}
            isLoading={isLoading}
            colorBy={colorBy}
          />
          <Legend colorBy={colorBy} />
          {/* Empty results overlay */}
          {!isLoading && mapData && mapData.nodes.length === 0 && (
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
            <AgentPanel agent={agentDetail} onClose={handleClosePanel} onAgentClick={(norm) => setSelectedAgent(norm)} />
          </div>
        )}
      </div>

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
            <AgentPanel agent={agentDetail} onClose={handleClosePanel} onAgentClick={(norm) => setSelectedAgent(norm)} mobile />
          </div>
        </div>
      )}

      {/* Footer — compact on mobile */}
      <div className="px-4 py-2 bg-gray-50 border-t text-xs md:text-sm text-gray-500 flex justify-between">
        <span className="truncate">
          {mapData
            ? connectionTypes.length === 0
              ? `${mapData.meta.showing}/${mapData.meta.total_agents} agents`
              : `${mapData.meta.showing}/${mapData.meta.total_agents} agents \u00B7 ${mapData.meta.total_edges} connections${mapData.meta.category_limited ? ` (limited)` : ''}`
            : 'Loading...'}
        </span>
        {isLoading && <span className="text-blue-500 shrink-0 ml-2">Updating...</span>}
      </div>
    </div>
  );
}
