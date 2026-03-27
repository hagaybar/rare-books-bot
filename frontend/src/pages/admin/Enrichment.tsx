/**
 * Entity Enrichment Browser
 *
 * Browse enriched agent data from Wikidata: biographies, images,
 * external identifiers, and linked records.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import ConfidenceBadge from '../../components/shared/ConfidenceBadge';
import EnrichmentRecordPanel from '../../components/enrichment/EnrichmentRecordPanel';

interface PersonInfo {
  birth_year: number | null;
  death_year: number | null;
  birth_place: string | null;
  death_place: string | null;
  nationality: string | null;
  occupations: string[];
  description: string | null;
}

interface EnrichedAgent {
  agent_norm: string;
  agent_raw: string;
  agent_type: string;
  role_raw: string | null;
  authority_uri: string | null;
  nli_id: string | null;
  wikidata_id: string | null;
  viaf_id: string | null;
  isni_id: string | null;
  loc_id: string | null;
  label: string | null;
  description: string | null;
  person_info: PersonInfo | null;
  image_url: string | null;
  wikipedia_url: string | null;
  confidence: number | null;
  record_count: number;
}

interface EnrichmentStats {
  total: number;
  with_wikidata: number;
  with_viaf: number;
  with_person_info: number;
  with_image: number;
  with_wikipedia: number;
  agents_linked: number;
  total_agents: number;
}

async function fetchStats(): Promise<EnrichmentStats> {
  const res = await fetch('/metadata/enrichment/stats');
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

interface FacetValue {
  value: string;
  count: number;
}

interface Facets {
  roles: FacetValue[];
  occupations: FacetValue[];
  centuries: FacetValue[];
}

interface AgentFilters {
  search: string;
  hasBio: boolean;
  hasImage: boolean;
  role: string;
  occupation: string;
  century: string;
}

async function fetchFacets(): Promise<Facets> {
  const res = await fetch('/metadata/enrichment/facets');
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

async function fetchAgents(
  limit: number,
  offset: number,
  filters: AgentFilters,
): Promise<{ total: number; items: EnrichedAgent[] }> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    has_bio: String(filters.hasBio),
    has_image: String(filters.hasImage),
  });
  if (filters.search) params.set('search', filters.search);
  if (filters.role) params.set('role', filters.role);
  if (filters.occupation) params.set('occupation', filters.occupation);
  if (filters.century) params.set('century', filters.century);
  const res = await fetch(`/metadata/enrichment/agents?${params}`);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className={`rounded-lg border p-4 ${color}`}>
      <div className="text-2xl font-bold">{value.toLocaleString()}</div>
      <div className="text-sm text-gray-600">{label}</div>
    </div>
  );
}

function AgentCard({ agent, onSelectAgent }: { agent: EnrichedAgent; onSelectAgent: (agent: EnrichedAgent) => void }) {
  const [expanded, setExpanded] = useState(false);
  const pi = agent.person_info;

  const lifespan =
    pi?.birth_year || pi?.death_year
      ? `${pi.birth_year ?? '?'}–${pi.death_year ?? '?'}`
      : null;

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden hover:shadow-md transition-shadow">
      <div className="flex gap-4 p-4">
        {/* Image */}
        {agent.image_url ? (
          <img
            src={agent.image_url}
            alt={agent.label ?? agent.agent_norm}
            className="w-16 h-20 object-cover rounded shrink-0 bg-gray-100"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />
        ) : (
          <div className="w-16 h-20 rounded bg-gray-100 flex items-center justify-center shrink-0">
            <svg
              className="w-8 h-8 text-gray-300"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0"
              />
            </svg>
          </div>
        )}

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="font-semibold text-gray-900 truncate">
                {agent.label ?? agent.agent_norm}
              </h3>
              {agent.agent_raw !== agent.label && agent.agent_raw && (
                <div className="text-xs text-gray-400 truncate">
                  {agent.agent_raw}
                </div>
              )}
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); onSelectAgent(agent); }}
              className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full shrink-0 hover:bg-blue-100 cursor-pointer transition-colors"
            >
              {agent.record_count} records
            </button>
          </div>

          {(lifespan || agent.description) && (
            <p className="text-sm text-gray-600 mt-1">
              {lifespan && (
                <span className="font-medium">{lifespan}</span>
              )}
              {lifespan && agent.description && ' — '}
              {agent.description}
            </p>
          )}

          {pi?.occupations && pi.occupations.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {pi.occupations.slice(0, 5).map((occ) => (
                <span
                  key={occ}
                  className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded"
                >
                  {occ}
                </span>
              ))}
            </div>
          )}

          {/* External links */}
          <div className="flex flex-wrap gap-2 mt-2">
            {agent.wikipedia_url && (
              <a
                href={agent.wikipedia_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-blue-600 hover:underline"
              >
                Wikipedia
              </a>
            )}
            {agent.wikidata_id && (
              <a
                href={`https://www.wikidata.org/wiki/${agent.wikidata_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-blue-600 hover:underline"
              >
                Wikidata
              </a>
            )}
            {agent.viaf_id && (
              <a
                href={`https://viaf.org/viaf/${agent.viaf_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-blue-600 hover:underline"
              >
                VIAF
              </a>
            )}
            {agent.confidence != null && (
              <ConfidenceBadge confidence={agent.confidence} />
            )}
          </div>
        </div>
      </div>

      {/* Expandable details */}
      {pi && (
        <>
          <button
            onClick={() => setExpanded(!expanded)}
            className="w-full text-xs text-gray-500 hover:bg-gray-50 py-1.5 border-t flex items-center justify-center gap-1"
          >
            {expanded ? 'Hide details' : 'Show details'}
            <svg
              className={`w-3 h-3 transition-transform ${expanded ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </button>
          {expanded && (
            <div className="px-4 pb-3 text-sm text-gray-600 border-t bg-gray-50 space-y-1">
              {pi.birth_place && (
                <div>
                  <span className="text-gray-400">Born:</span>{' '}
                  {pi.birth_place}
                  {pi.birth_year && ` (${pi.birth_year})`}
                </div>
              )}
              {pi.death_place && (
                <div>
                  <span className="text-gray-400">Died:</span>{' '}
                  {pi.death_place}
                  {pi.death_year && ` (${pi.death_year})`}
                </div>
              )}
              {pi.nationality && (
                <div>
                  <span className="text-gray-400">Nationality:</span>{' '}
                  {pi.nationality}
                </div>
              )}
              <div className="flex gap-2 pt-1 text-xs">
                {agent.nli_id && (
                  <span className="text-gray-400">NLI: {agent.nli_id}</span>
                )}
                {agent.isni_id && (
                  <span className="text-gray-400">ISNI: {agent.isni_id}</span>
                )}
                {agent.loc_id && (
                  <span className="text-gray-400">LOC: {agent.loc_id}</span>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function FacetSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: FacetValue[];
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-500 mb-1">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-2 py-1.5 text-sm border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        <option value="">All</option>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.value} ({opt.count})
          </option>
        ))}
      </select>
    </div>
  );
}

export default function Enrichment() {
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(0);
  const [selectedAgent, setSelectedAgent] = useState<EnrichedAgent | null>(null);
  const [filters, setFilters] = useState<AgentFilters>({
    search: '',
    hasBio: false,
    hasImage: false,
    role: '',
    occupation: '',
    century: '',
  });
  const PAGE_SIZE = 24;

  // Debounce search
  const [searchTimeout, setSearchTimeout] = useState<ReturnType<typeof setTimeout> | null>(null);
  const handleSearch = (value: string) => {
    setSearch(value);
    if (searchTimeout) clearTimeout(searchTimeout);
    setSearchTimeout(
      setTimeout(() => {
        setDebouncedSearch(value);
        setPage(0);
      }, 300),
    );
  };

  const updateFilter = (key: keyof AgentFilters, value: string | boolean) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(0);
  };

  const activeFilters = { ...filters, search: debouncedSearch };
  const activeFilterCount = [
    activeFilters.search,
    activeFilters.hasBio,
    activeFilters.hasImage,
    activeFilters.role,
    activeFilters.occupation,
    activeFilters.century,
  ].filter(Boolean).length;

  const clearFilters = () => {
    setSearch('');
    setDebouncedSearch('');
    setFilters({ search: '', hasBio: false, hasImage: false, role: '', occupation: '', century: '' });
    setPage(0);
  };

  const statsQuery = useQuery({
    queryKey: ['enrichment-stats'],
    queryFn: fetchStats,
    staleTime: 60_000,
  });

  const facetsQuery = useQuery({
    queryKey: ['enrichment-facets'],
    queryFn: fetchFacets,
    staleTime: 60_000,
  });

  const agentsQuery = useQuery({
    queryKey: ['enriched-agents', PAGE_SIZE, page * PAGE_SIZE, activeFilters],
    queryFn: () => fetchAgents(PAGE_SIZE, page * PAGE_SIZE, activeFilters),
    staleTime: 30_000,
  });

  const stats = statsQuery.data;
  const facets = facetsQuery.data;
  const agents = agentsQuery.data;
  const totalPages = agents ? Math.ceil(agents.total / PAGE_SIZE) : 0;

  const selectedLifespan =
    selectedAgent?.person_info?.birth_year || selectedAgent?.person_info?.death_year
      ? `${selectedAgent.person_info.birth_year ?? '?'}\u2013${selectedAgent.person_info.death_year ?? '?'}`
      : '';

  return (
    <div className="flex gap-0 h-full">
      <div className="flex-1 min-w-0 space-y-6 overflow-y-auto">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Entity Enrichment
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Agents enriched from Wikidata with biographies, images, and external
          identifiers
        </p>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            label="Total enrichment records"
            value={stats.total}
            color="bg-white"
          />
          <StatCard
            label="With Wikidata profile"
            value={stats.with_wikidata}
            color="bg-blue-50"
          />
          <StatCard
            label="Agents linked"
            value={stats.agents_linked}
            color="bg-green-50"
          />
          <StatCard
            label={`Coverage (of ${stats.total_agents})`}
            value={Math.round((stats.agents_linked / stats.total_agents) * 100)}
            color="bg-amber-50"
          />
        </div>
      )}

      {/* Search + Facet Filters */}
      <div className="bg-white rounded-lg border p-4 space-y-3">
        {/* Search bar */}
        <div className="flex gap-3 items-center">
          <input
            type="text"
            placeholder="Search by name, label, or description..."
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            className="flex-1 px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {activeFilterCount > 0 && (
            <button
              onClick={clearFilters}
              className="text-xs text-red-600 hover:text-red-800 px-2 py-1 border border-red-200 rounded hover:bg-red-50"
            >
              Clear all ({activeFilterCount})
            </button>
          )}
        </div>

        {/* Facet dropdowns */}
        {facets && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            <FacetSelect
              label="Occupation"
              value={filters.occupation}
              onChange={(v) => updateFilter('occupation', v)}
              options={facets.occupations}
            />
            <FacetSelect
              label="Century"
              value={filters.century}
              onChange={(v) => updateFilter('century', v)}
              options={facets.centuries}
            />
            <FacetSelect
              label="Role in collection"
              value={filters.role}
              onChange={(v) => updateFilter('role', v)}
              options={facets.roles}
            />
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Data quality</label>
              <div className="flex flex-col gap-1.5 pt-1">
                <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={filters.hasBio}
                    onChange={(e) => updateFilter('hasBio', e.target.checked)}
                    className="rounded"
                  />
                  Has biography
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={filters.hasImage}
                    onChange={(e) => updateFilter('hasImage', e.target.checked)}
                    className="rounded"
                  />
                  Has portrait
                </label>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Agent grid */}
      {agentsQuery.isLoading && (
        <div className="text-center py-12 text-gray-400">Loading...</div>
      )}

      {agentsQuery.isError && (
        <div className="text-center py-12 text-red-500">
          Failed to load agents
        </div>
      )}

      {agents && agents.items.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          No enriched agents found
          {activeFilterCount > 0 && (
            <button
              onClick={clearFilters}
              className="block mx-auto mt-2 text-blue-600 hover:underline text-sm"
            >
              Clear filters
            </button>
          )}
        </div>
      )}

      {agents && agents.items.length > 0 && (
        <>
          <div className="text-sm text-gray-500">
            Showing {page * PAGE_SIZE + 1}–
            {Math.min((page + 1) * PAGE_SIZE, agents.total)} of{' '}
            {agents.total.toLocaleString()} agents
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {agents.items.map((agent) => (
              <AgentCard key={agent.agent_norm} agent={agent} onSelectAgent={setSelectedAgent} />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex justify-center items-center gap-2 pt-4">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-3 py-1.5 text-sm rounded border disabled:opacity-50 hover:bg-gray-50"
              >
                Previous
              </button>
              <span className="text-sm text-gray-500">
                Page {page + 1} of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="px-3 py-1.5 text-sm rounded border disabled:opacity-50 hover:bg-gray-50"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
      </div>

      {selectedAgent && (
        <EnrichmentRecordPanel
          wikidataId={selectedAgent.wikidata_id}
          agentNorm={selectedAgent.agent_norm}
          displayName={selectedAgent.label || selectedAgent.agent_norm}
          lifespan={selectedLifespan}
          onClose={() => setSelectedAgent(null)}
        />
      )}
    </div>
  );
}
