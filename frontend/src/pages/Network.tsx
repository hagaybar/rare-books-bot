import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { fetchMapData, fetchAgentDetail } from '../api/network';
import { useNetworkStore } from '../stores/networkStore';
import MapView from '../components/network/MapView';
import ControlBar from '../components/network/ControlBar';
import AgentPanel from '../components/network/AgentPanel';
import type { MapNode } from '../types/network';

export default function Network() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  const { connectionTypes, minConfidence, century, place, role, agentLimit } =
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

  return (
    <div className="flex flex-col h-full">
      <ControlBar />

      <div className="flex flex-1 relative overflow-hidden">
        <div className="flex-1 relative">
          <MapView
            nodes={mapData?.nodes ?? []}
            edges={mapData?.edges ?? []}
            selectedAgent={selectedAgent}
            onAgentClick={handleAgentClick}
            onBackgroundClick={handleClosePanel}
            isLoading={isLoading}
          />
          {/* Empty results overlay */}
          {!isLoading && mapData && mapData.nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none">
              <p className="text-gray-500 bg-white/80 px-4 py-2 rounded shadow">
                No agents match these filters. Try broadening your search.
              </p>
            </div>
          )}
        </div>

        {selectedAgent && agentDetail && (
          <AgentPanel agent={agentDetail} onClose={handleClosePanel} onAgentClick={(norm) => setSelectedAgent(norm)} />
        )}
      </div>

      <div className="px-4 py-2 bg-gray-50 border-t text-sm text-gray-500 flex justify-between">
        <span>
          {mapData
            ? `Showing ${mapData.meta.showing} of ${mapData.meta.total_agents} agents \u00B7 ${mapData.meta.total_edges} connections`
            : 'Loading...'}
        </span>
        {isLoading && <span className="text-blue-500">Updating...</span>}
      </div>
    </div>
  );
}
