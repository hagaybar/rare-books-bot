import { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { fetchMapData, fetchAgentDetail, fetchPlaceDetail, fetchEgo, fetchPath, fetchPlaces } from '../api/network';
import { useNetworkStore } from '../stores/networkStore';
import MapView from '../components/network/MapView';
import EgoView from '../components/network/EgoView';
import Breadcrumbs from '../components/network/Breadcrumbs';
import PathFinder from '../components/network/PathFinder';
import TimeSlider from '../components/network/TimeSlider';
import CityView from '../components/network/CityView';
import CityToolbar from '../components/network/CityToolbar';
import Tour, { type TourStep } from '../components/network/Tour';
import ControlBar from '../components/network/ControlBar';
import AgentPanel from '../components/network/AgentPanel';
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
  // Any place mention pivots to the full city profile (CityView), wherever you are.
  const selectPlace = (norm: string) => {
    setSelectedAgent(null);
    useNetworkStore.getState().setViewMode('map');
    useNetworkStore.getState().setMapLayer('cities');
    setSelectedPlace(norm);
  };

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

  // Time slider (issue #32): a sliding imprint-year window over the map.
  const yearMin = mapData?.meta.year_min ?? 1450;
  const yearMax = mapData?.meta.year_max ?? 1950;
  const [timeMode, setTimeMode] = useState(false);
  const [windowWidth, setWindowWidth] = useState(100);
  const [windowStart, setWindowStart] = useState(yearMin);
  const [playing, setPlaying] = useState(false);

  const openTimeline = () => { setWindowStart(yearMin); setTimeMode(true); setPlaying(true); };
  const closeTimeline = () => { setTimeMode(false); setPlaying(false); };

  // Animate the window forward, looping back to the start when it reaches the end.
  useEffect(() => {
    if (!timeMode || !playing) return;
    const id = setInterval(() => {
      setWindowStart((prev) => (prev + 10 > yearMax - windowWidth ? yearMin : prev + 10));
    }, 650);
    return () => clearInterval(id);
  }, [timeMode, playing, yearMin, yearMax, windowWidth]);

  // Nodes/edges visible under the active time window (client-side for smoothness).
  const timeFiltered = useMemo(() => {
    const all = { nodes: mapData?.nodes ?? [], edges: mapData?.edges ?? [] };
    if (!timeMode) return all;
    const end = windowStart + windowWidth;
    const visible = new Set(
      all.nodes
        .filter((n) => n.active_start != null && n.active_end != null && n.active_start <= end && n.active_end >= windowStart)
        .map((n) => n.agent_norm),
    );
    return {
      nodes: all.nodes.filter((n) => visible.has(n.agent_norm)),
      edges: all.edges.filter((e) => visible.has(e.source) && visible.has(e.target)),
    };
  }, [mapData, timeMode, windowStart, windowWidth]);

  // Place-first map: cities (aggregated) is the default geographic view.
  const mapLayer = useNetworkStore((s) => s.mapLayer);
  const setMapLayer = useNetworkStore((s) => s.setMapLayer);
  const { data: places } = useQuery({
    queryKey: ['network-places'],
    queryFn: fetchPlaces,
    staleTime: 5 * 60 * 1000,
  });
  const citiesActive = viewMode === 'map' && mapLayer === 'cities';
  const cityOpen = citiesActive && !!selectedPlace && !!placeDetail;

  // Chat -> map overlay (issue #34): a result set handed off via sessionStorage.
  const [chatOverlay, setChatOverlay] = useState<{
    label: string; total: number; located: number; places: Record<string, number>;
  } | null>(null);
  useEffect(() => {
    if (searchParams.get('overlay') !== 'chat') return;
    try {
      const raw = sessionStorage.getItem('chatMapOverlay');
      if (raw) {
        setChatOverlay(JSON.parse(raw));
        useNetworkStore.getState().setViewMode('map');
        useNetworkStore.getState().setMapLayer('cities');
      }
    } catch { /* malformed payload — ignore */ }
    // ?overlay= itself is stripped by the agent-sync effect (the last URL writer).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const clearChatOverlay = () => {
    setChatOverlay(null);
    sessionStorage.removeItem('chatMapOverlay');
  };

  // Driven onboarding tour (issue #38): spotlights elements AND navigates the
  // UI between steps, so new users experience the flow rather than read it.
  const [tourOpen, setTourOpen] = useState(false);
  const tourSteps: TourStep[] = useMemo(() => [
    {
      target: '[data-tour="map-area"]',
      title: 'Where this collection was printed',
      body: 'Every circle is a printing city, sized by how many of our books were printed there. The map is the front door — Paris, London, Amsterdam, Venice…',
      before: () => {
        useNetworkStore.getState().setViewMode('map');
        useNetworkStore.getState().setMapLayer('cities');
        setSelectedAgent(null); setSelectedPlace(null); setTimeMode(false);
      },
    },
    {
      target: '[data-tour="city-finder"]',
      title: 'Find any city',
      body: 'Click a circle directly, or pick from this ranked list — no hunting for tiny dots in the European cluster.',
    },
    {
      target: '[data-tour="city-view"]',
      title: 'A city’s profile',
      body: 'We opened Venice for you: when printing happened there, the printers and notable people, what subjects were printed, and the books themselves.',
      before: () => selectPlace('venice'),
    },
    {
      target: '[data-tour="ego-reading"]',
      title: 'A person’s world — with a reading',
      body: 'Clicking a person opens their network. This card interprets its shape — Buchon’s web of medieval authors marks him as an editor resurrecting older texts. "Interpret with AI" goes deeper.',
      before: () => handleCityPerson('buchon, j. a. c', 'Jean Alexandre Buchon'),
    },
    {
      target: '[data-tour="connection-toggles"]',
      title: 'Choose the relationships',
      body: 'These toggles pick which connection types are drawn — shared books, printed-by, teacher & student, Wikipedia mentions. The lens you look through.',
    },
    {
      target: '[data-tour="pathfinder"]',
      title: 'How are two people connected?',
      body: 'Ask for the shortest path between the current figure and anyone else — each hop labeled with its evidence.',
    },
    {
      target: '[data-tour="time-button"]',
      title: 'Play through time',
      body: 'Back on the map: press play and watch printing migrate across the centuries — Venice fades as Amsterdam and Paris rise. Enjoy exploring!',
      before: () => {
        useNetworkStore.getState().setViewMode('map');
        useNetworkStore.getState().setMapLayer('cities');
        setSelectedAgent(null); setSelectedPlace(null);
      },
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], []);
  const closeTour = (completed: boolean) => {
    setTourOpen(false);
    try { localStorage.setItem('rb-network-tour-done', completed ? 'done' : 'skipped'); } catch { /* private mode */ }
  };
  // Don't hijack first-time users: OFFER the tour in a small dismissible
  // pop-up instead of auto-starting it. 'Not now' hides it for this visit;
  // 'Don't show again' persists; taking/skipping the tour also persists.
  const [tourOffer, setTourOffer] = useState(false);
  useEffect(() => {
    try {
      if (localStorage.getItem('rb-network-tour-done')) return;
      if (sessionStorage.getItem('rb-tour-offer-dismissed')) return;
    } catch { return; }
    if (searchParams.get('agent') || searchParams.get('session') || searchParams.get('overlay')) return;
    const t = setTimeout(() => setTourOffer(true), 1500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const dismissOffer = (forever: boolean) => {
    setTourOffer(false);
    try {
      if (forever) localStorage.setItem('rb-network-tour-done', 'declined');
      else sessionStorage.setItem('rb-tour-offer-dismissed', '1');
    } catch { /* private mode */ }
  };

  // Time window on cities: re-weight each circle by books printed *within the
  // window* (decade resolution). Stable array order + zero counts (instead of
  // filtering) so deck.gl can animate radius transitions per city.
  const timedPlaces = useMemo(() => {
    if (!places) return places;
    if (!timeMode || !citiesActive) return places;
    const end = windowStart + windowWidth;
    return places.map((p) => ({
      ...p,
      record_count: p.decades.reduce(
        (sum, d) => (d.decade + 9 >= windowStart && d.decade <= end ? sum + d.count : sum),
        0,
      ),
    }));
  }, [places, timeMode, citiesActive, windowStart, windowWidth]);

  // From a city profile, "notable person" jumps into their ego world.
  const handleCityPerson = (norm: string, displayName: string) => {
    setSelectedPlace(null);
    setSelectedAgent(norm);
    enterEgo({ agent_norm: norm, display_name: displayName });
  };

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

  // Keep ?agent= in sync with the selection. This is the last URL writer in the
  // mount batch, so it also strips the one-shot ?overlay= trigger (issue #34) —
  // earlier deletions get clobbered by this updater's `prev`.
  useEffect(() => {
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev);
      if (selectedAgent) p.set('agent', selectedAgent);
      else p.delete('agent');
      p.delete('overlay');
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
            {citiesActive ? 'Where This Collection Was Printed' : 'Scholarly Network Map'}
          </h1>
          <p className="text-sm text-gray-500 hidden md:block">
            {citiesActive
              ? `${places?.length ?? '…'} printing cities, sized by how many of our books were printed there — click one to explore`
              : `Explore connections between ${mapData?.meta.total_agents?.toLocaleString() ?? '...'} historical figures across Europe and the Middle East`}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0 ml-2">
        {/* Guided tour entry (issue #38) */}
        <button
          onClick={() => setTourOpen(true)}
          className="inline-flex items-center gap-1 px-2.5 py-1.5 text-sm text-gray-500 hover:text-indigo-600 rounded-lg hover:bg-indigo-50"
          title="Take a 2-minute guided tour"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z" />
          </svg>
          Tour
        </button>
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

        {/* Mobile filter toggle button (people-network filters — hidden in cities mode) */}
        {!citiesActive && (
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
        )}
        </div>
      </div>

      {/* Cities mode: a slim city finder. People/ego: the full network controls. */}
      {citiesActive ? (
        <CityToolbar places={places ?? []} onSelect={selectPlace} />
      ) : (
        <div className="hidden md:block">
          <ControlBar onAgentSelect={setSelectedAgent} />
        </div>
      )}

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
      {!citiesActive && !filtersOpen && activeFilterCount > 0 && (
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
        <div className="flex-1 relative min-h-0" data-tour="map-area">
          {viewMode === 'ego' ? (
            egoData ? (
              <EgoView
                data={egoData}
                colorBy={colorBy}
                communities={mapData?.meta.communities}
                connectionTypes={connectionTypes}
                onNodeClick={handleEgoNodeClick}
              />
            ) : (
              <div className="absolute inset-0 flex items-center justify-center text-gray-500 text-sm">
                {egoLoading ? 'Loading network…' : 'Search or pick a node to explore its connections.'}
              </div>
            )
          ) : (
            <MapView
              nodes={timeFiltered.nodes}
              edges={timeFiltered.edges}
              places={timedPlaces}
              cityHighlight={citiesActive ? chatOverlay?.places ?? null : null}
              mapLayer={mapLayer}
              selectedAgent={selectedAgent}
              onAgentClick={handleAgentClick}
              onBackgroundClick={handleClosePanel}
              onPlaceSelect={selectPlace}
              isLoading={isLoading}
              colorBy={colorBy}
              communities={mapData?.meta.communities}
            />
          )}

          {/* City drill-down: a full profile view, not a map (place redesign) */}
          {cityOpen && placeDetail && (
            <CityView city={placeDetail} onBack={handleClosePanel} onPersonClick={handleCityPerson} />
          )}

          {/* Place-first layer toggle: Cities (default) vs People */}
          {viewMode === 'map' && !cityOpen && (
            <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 inline-flex rounded-lg border border-gray-300 overflow-hidden text-sm shadow-sm bg-white" role="group" aria-label="Map layer">
              <button
                onClick={() => setMapLayer('cities')}
                aria-pressed={mapLayer === 'cities'}
                className={`px-3 py-1.5 ${mapLayer === 'cities' ? 'bg-blue-600 text-white' : 'text-gray-700 hover:bg-gray-50'}`}
              >
                Printing cities
              </button>
              <button
                onClick={() => setMapLayer('people')}
                aria-pressed={mapLayer === 'people'}
                className={`px-3 py-1.5 border-l border-gray-300 ${mapLayer === 'people' ? 'bg-blue-600 text-white' : 'text-gray-700 hover:bg-gray-50'}`}
              >
                People
              </button>
            </div>
          )}

          {(viewMode === 'ego' || mapLayer === 'people') && (
            <Legend colorBy={colorBy} activeTypes={connectionTypes} communities={mapData?.meta.communities} />
          )}

          {/* Chat-results overlay banner (issue #34) */}
          {citiesActive && !cityOpen && chatOverlay && (
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 bg-amber-50 border border-amber-300 rounded-full shadow-md px-4 py-2 text-sm text-amber-900 max-w-[min(92%,640px)]">
              <span className="truncate">
                From chat: <span className="font-medium">“{chatOverlay.label}”</span>
                {' — '}{chatOverlay.located} of {chatOverlay.total} results located
              </span>
              <button onClick={clearChatOverlay} className="shrink-0 text-amber-700 hover:text-amber-900 font-medium" title="Clear and return to the full map">
                ✕
              </button>
            </div>
          )}

          {/* Time slider — issue #32; on cities it re-weights circles per window */}
          {viewMode === 'map' && !cityOpen && !chatOverlay && !timeMode && mapData && (
            <button
              onClick={openTimeline}
              data-tour="time-button"
              className="absolute bottom-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1.5 bg-white/95 backdrop-blur-sm border border-gray-300 rounded-full shadow-md px-4 py-2 text-sm font-medium text-gray-700 hover:bg-white"
            >
              <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2m6-2a10 10 0 11-20 0 10 10 0 0120 0z" />
              </svg>
              Play through time
            </button>
          )}
          {viewMode === 'map' && !cityOpen && !chatOverlay && timeMode && mapData && (
            <TimeSlider
              min={yearMin}
              max={yearMax}
              windowStart={windowStart}
              windowWidth={windowWidth}
              playing={playing}
              activeLabel={citiesActive
                ? `${timedPlaces?.filter((p) => p.record_count > 0).length ?? 0} cities · ${timedPlaces?.reduce((s, p) => s + p.record_count, 0) ?? 0} books`
                : `${timeFiltered.nodes.length} active`}
              onStartChange={(y) => { setPlaying(false); setWindowStart(y); }}
              onWidthChange={setWindowWidth}
              onTogglePlay={() => setPlaying((p) => !p)}
              onClose={closeTimeline}
            />
          )}
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
            <AgentPanel agent={agentDetail} onClose={handleClosePanel} onAgentClick={selectAgent} onPlaceSelect={selectPlace} onExplore={(n, d) => { handleExplore(n, d); handleClosePanel(); }} mobile />
          </div>
        </div>
      )}

      {tourOpen && <Tour steps={tourSteps} onClose={closeTour} />}

      {/* First-visit tour offer — small, polite, dismissible (issue #38 follow-up) */}
      {tourOffer && !tourOpen && (
        <div className="fixed bottom-16 right-4 z-50 w-80 bg-white border border-gray-200 rounded-xl shadow-xl p-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">New here?</h3>
              <p className="mt-0.5 text-sm text-gray-600 leading-snug">
                Take a 2-minute guided tour — it opens a city, a person's network,
                and the timeline for you.
              </p>
            </div>
            <button onClick={() => dismissOffer(false)} aria-label="Dismiss"
                    className="text-gray-400 hover:text-gray-600 shrink-0 p-0.5">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className="mt-3 flex items-center justify-between">
            <button onClick={() => dismissOffer(true)} className="text-xs text-gray-400 hover:text-gray-600 underline">
              Don't show again
            </button>
            <button
              onClick={() => { setTourOffer(false); setTourOpen(true); }}
              className="px-3.5 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700"
            >
              Take the tour
            </button>
          </div>
        </div>
      )}

      {/* Footer — compact on mobile */}
      <div className="px-4 py-2 bg-gray-50 border-t text-xs md:text-sm text-gray-500 flex justify-between">
        <span className="truncate">
          {citiesActive
            ? places
              ? `${places.length} printing cities \u00B7 ${places.reduce((s, p) => s + p.record_count, 0)} located imprints`
              : 'Loading...'
            : mapData
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
