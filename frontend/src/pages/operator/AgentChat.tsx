import { useState, useRef, useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  useCoverage,
  useAgentChat,
  useSubmitCorrection,
} from '../../hooks/useMetadata';
import type {
  AgentChatResponse,
  AgentProposal,
  AgentClusterSummary,
  FieldCoverage,
  CoverageReport,
} from '../../types/metadata';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const AGENT_FIELDS = ['place', 'date', 'publisher', 'agent'] as const;
type AgentField = (typeof AGENT_FIELDS)[number];

const FIELD_LABELS: Record<AgentField, string> = {
  place: 'Place',
  date: 'Date',
  publisher: 'Publisher',
  agent: 'Agent',
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ChatMessage {
  role: 'user' | 'agent';
  content: string;
  data?: AgentChatResponse;
}

type ProposalStatus = 'approved' | 'rejected' | 'edited';

// ---------------------------------------------------------------------------
// Coverage sidebar helpers
// ---------------------------------------------------------------------------

function fieldCoverageOf(
  report: CoverageReport,
  field: AgentField
): FieldCoverage | null {
  const map: Record<AgentField, FieldCoverage | undefined> = {
    date: report.date_coverage,
    place: report.place_coverage,
    publisher: report.publisher_coverage,
    agent: report.agent_name_coverage,
  };
  return map[field] ?? null;
}

function confidenceBucket(
  fc: FieldCoverage,
  minThreshold: number,
  maxThreshold: number
): number {
  return fc.confidence_distribution
    .filter(
      (b) => b.min_confidence >= minThreshold && b.min_confidence < maxThreshold
    )
    .reduce((sum, b) => sum + b.count, 0);
}

function highConfidenceCount(fc: FieldCoverage): number {
  return fc.confidence_distribution
    .filter((b) => b.min_confidence >= 0.95)
    .reduce((sum, b) => sum + b.count, 0);
}

function mediumConfidenceCount(fc: FieldCoverage): number {
  return confidenceBucket(fc, 0.8, 0.95);
}

function lowConfidenceCount(fc: FieldCoverage): number {
  return fc.confidence_distribution
    .filter((b) => b.min_confidence < 0.8)
    .reduce((sum, b) => sum + b.count, 0);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TypingIndicator() {
  return (
    <div className="flex items-start gap-3 mb-4">
      <div className="w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center text-xs font-bold text-gray-600 shrink-0">
        AI
      </div>
      <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-3">
        <div className="flex gap-1.5">
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  );
}

function CoverageSidebar({ field }: { field: AgentField }) {
  const { data: report, isLoading, isError } = useCoverage();

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-12 bg-gray-200 rounded" />
        ))}
      </div>
    );
  }

  if (isError || !report) {
    return (
      <div className="text-sm text-gray-400">Unable to load coverage data.</div>
    );
  }

  const fc = fieldCoverageOf(report, field);
  if (!fc) {
    return (
      <div className="text-sm text-gray-400">No coverage data for this field.</div>
    );
  }

  const high = highConfidenceCount(fc);
  const medium = mediumConfidenceCount(fc);
  const low = lowConfidenceCount(fc);
  const unmapped = fc.null_count;
  const total = fc.total_records;

  const pct = (n: number) =>
    total > 0 ? `${Math.round((n / total) * 1000) / 10}%` : '0%';

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
        {FIELD_LABELS[field]} Coverage
      </h3>

      <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
        <div className="text-2xl font-bold text-gray-900">
          {total.toLocaleString()}
        </div>
        <div className="text-xs text-gray-500 uppercase">Total Records</div>
      </div>

      <div className="space-y-2">
        <CoverageStat
          label="High confidence"
          count={high}
          pct={pct(high)}
          color="bg-green-500"
        />
        <CoverageStat
          label="Medium confidence"
          count={medium}
          pct={pct(medium)}
          color="bg-yellow-500"
        />
        <CoverageStat
          label="Low confidence"
          count={low}
          pct={pct(low)}
          color="bg-orange-500"
        />
        <CoverageStat
          label="Unmapped"
          count={unmapped}
          pct={pct(unmapped)}
          color="bg-red-500"
        />
      </div>

      {/* Visual bar */}
      <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden flex">
        {total > 0 && (
          <>
            <div
              className="bg-green-500 h-full"
              style={{ width: pct(high) }}
            />
            <div
              className="bg-yellow-500 h-full"
              style={{ width: pct(medium) }}
            />
            <div
              className="bg-orange-500 h-full"
              style={{ width: pct(low) }}
            />
            <div
              className="bg-red-500 h-full"
              style={{ width: pct(unmapped) }}
            />
          </>
        )}
      </div>
    </div>
  );
}

function CoverageStat({
  label,
  count,
  pct,
  color,
}: {
  label: string;
  count: number;
  pct: string;
  color: string;
}) {
  return (
    <div className="flex items-center justify-between text-sm">
      <div className="flex items-center gap-2">
        <span className={`w-2.5 h-2.5 rounded-sm ${color}`} />
        <span className="text-gray-600">{label}</span>
      </div>
      <div className="text-right">
        <span className="font-medium text-gray-900">
          {count.toLocaleString()}
        </span>
        <span className="text-gray-400 ml-1 text-xs">{pct}</span>
      </div>
    </div>
  );
}

function ProposalTable({
  proposals,
  field,
  proposalStatuses,
  editValues,
  onApprove,
  onReject,
  onEdit,
  onEditChange,
  onEditConfirm,
  onApproveAll,
}: {
  proposals: AgentProposal[];
  field: AgentField;
  proposalStatuses: Map<string, ProposalStatus>;
  editValues: Map<string, string>;
  onApprove: (p: AgentProposal) => void;
  onReject: (raw: string) => void;
  onEdit: (raw: string, currentCanonical: string) => void;
  onEditChange: (raw: string, value: string) => void;
  onEditConfirm: (p: AgentProposal) => void;
  onApproveAll: () => void;
}) {
  // Avoid unused variable warning
  void field;

  const allHandled = proposals.every((p) => proposalStatuses.has(p.raw_value));

  return (
    <div className="mt-3">
      {!allHandled && (
        <div className="mb-2 flex justify-end">
          <button
            type="button"
            onClick={onApproveAll}
            className="text-xs bg-green-600 text-white px-3 py-1 rounded-md hover:bg-green-700 transition-colors"
          >
            Approve All
          </button>
        </div>
      )}

      <div className="overflow-x-auto border border-gray-200 rounded-lg">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="text-left px-3 py-2 text-xs font-medium text-gray-500 uppercase">
                Raw Value
              </th>
              <th className="text-left px-3 py-2 text-xs font-medium text-gray-500 uppercase">
                Proposed Canonical
              </th>
              <th className="text-center px-3 py-2 text-xs font-medium text-gray-500 uppercase">
                Confidence
              </th>
              <th className="text-left px-3 py-2 text-xs font-medium text-gray-500 uppercase">
                Reasoning
              </th>
              <th className="text-center px-3 py-2 text-xs font-medium text-gray-500 uppercase">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {proposals.map((p) => {
              const status = proposalStatuses.get(p.raw_value);
              const isEditing = editValues.has(p.raw_value);

              return (
                <tr key={p.raw_value} className="hover:bg-gray-50">
                  <td className="px-3 py-2 font-mono text-xs text-gray-700 max-w-[160px] truncate">
                    {p.raw_value}
                  </td>
                  <td className="px-3 py-2 text-gray-900 max-w-[160px]">
                    {isEditing ? (
                      <input
                        type="text"
                        value={editValues.get(p.raw_value) ?? ''}
                        onChange={(e) =>
                          onEditChange(p.raw_value, e.target.value)
                        }
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') onEditConfirm(p);
                        }}
                        className="w-full border border-blue-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                        autoFocus
                      />
                    ) : (
                      <span className="truncate block">{p.canonical_value}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <ConfidenceBadge value={p.confidence} />
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-500 max-w-[200px] truncate">
                    {p.reasoning}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {status ? (
                      <StatusBadge status={status} />
                    ) : isEditing ? (
                      <button
                        type="button"
                        onClick={() => onEditConfirm(p)}
                        className="text-xs bg-blue-600 text-white px-2 py-1 rounded hover:bg-blue-700"
                      >
                        Confirm
                      </button>
                    ) : (
                      <div className="flex gap-1 justify-center">
                        <button
                          type="button"
                          onClick={() => onApprove(p)}
                          className="text-xs bg-green-600 text-white px-2 py-1 rounded hover:bg-green-700"
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          onClick={() => onReject(p.raw_value)}
                          className="text-xs bg-red-600 text-white px-2 py-1 rounded hover:bg-red-700"
                        >
                          Reject
                        </button>
                        <button
                          type="button"
                          onClick={() => onEdit(p.raw_value, p.canonical_value)}
                          className="text-xs bg-gray-600 text-white px-2 py-1 rounded hover:bg-gray-700"
                        >
                          Edit
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  let cls = 'bg-green-100 text-green-800';
  if (value < 0.8) cls = 'bg-red-100 text-red-800';
  else if (value < 0.95) cls = 'bg-yellow-100 text-yellow-800';
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {pct}%
    </span>
  );
}

function StatusBadge({ status }: { status: ProposalStatus }) {
  const config: Record<ProposalStatus, { label: string; cls: string }> = {
    approved: { label: 'Approved', cls: 'bg-green-100 text-green-800' },
    rejected: { label: 'Rejected', cls: 'bg-red-100 text-red-800' },
    edited: { label: 'Edited', cls: 'bg-blue-100 text-blue-800' },
  };
  const c = config[status];
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${c.cls}`}>
      {c.label}
    </span>
  );
}

function ClusterCards({
  clusters,
  onInvestigate,
}: {
  clusters: AgentClusterSummary[];
  onInvestigate: (clusterId: string) => void;
}) {
  return (
    <div className="mt-3 grid gap-2 grid-cols-1 sm:grid-cols-2">
      {clusters.map((c) => (
        <div
          key={c.cluster_id}
          className="border border-gray-200 rounded-lg p-3 bg-white shadow-sm"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-semibold text-indigo-600 uppercase">
              {c.cluster_type}
            </span>
            <span className="text-xs text-gray-400">
              Priority: {c.priority_score.toFixed(1)}
            </span>
          </div>
          <div className="flex items-center gap-4 text-sm text-gray-700 mb-2">
            <span>{c.value_count} values</span>
            <span>{c.total_records.toLocaleString()} records</span>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => onInvestigate(`propose:${c.cluster_id}`)}
              className="text-xs bg-indigo-600 text-white px-3 py-1.5 rounded-md hover:bg-indigo-700 transition-colors font-medium"
            >
              Propose Mappings
            </button>
            <button
              type="button"
              onClick={() => onInvestigate(`cluster:${c.cluster_id}`)}
              className="text-xs text-gray-500 hover:text-gray-700 font-medium px-2 py-1.5"
            >
              Details
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AgentChat() {
  const [activeField, setActiveField] = useState<AgentField>('place');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [proposalStatuses, setProposalStatuses] = useState<
    Map<string, ProposalStatus>
  >(new Map());
  const [editValues, setEditValues] = useState<Map<string, string>>(new Map());

  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const queryClient = useQueryClient();
  const agentMutation = useAgentChat();
  const correctionMutation = useSubmitCorrection();

  // Auto-scroll to bottom when messages change or loading state changes
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, agentMutation.isPending]);

  // Focus input on field change
  useEffect(() => {
    inputRef.current?.focus();
  }, [activeField]);

  const switchField = useCallback(
    (field: AgentField) => {
      if (field === activeField) return;
      setActiveField(field);
      setMessages([]);
      setProposalStatuses(new Map());
      setEditValues(new Map());
      setInputValue('');
    },
    [activeField]
  );

  const sendMessage = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || agentMutation.isPending) return;

      // Add user message
      setMessages((prev) => [...prev, { role: 'user', content: trimmed }]);
      setInputValue('');

      agentMutation.mutate(
        { field: activeField, message: trimmed },
        {
          onSuccess: (data) => {
            setMessages((prev) => [
              ...prev,
              { role: 'agent', content: data.response, data },
            ]);
          },
          onError: (err) => {
            setMessages((prev) => [
              ...prev,
              {
                role: 'agent',
                content: `Error: ${err instanceof Error ? err.message : 'Unknown error occurred'}`,
              },
            ]);
          },
        }
      );
    },
    [activeField, agentMutation]
  );

  const handleApprove = useCallback(
    (proposal: AgentProposal) => {
      correctionMutation.mutate(
        {
          field: activeField,
          rawValue: proposal.raw_value,
          canonicalValue: proposal.canonical_value,
          evidence: proposal.reasoning,
        },
        {
          onSuccess: () => {
            setProposalStatuses((prev) => {
              const next = new Map(prev);
              next.set(proposal.raw_value, 'approved');
              return next;
            });
            queryClient.invalidateQueries({ queryKey: ['coverage'] });
          },
        }
      );
    },
    [activeField, correctionMutation, queryClient]
  );

  const handleReject = useCallback((rawValue: string) => {
    setProposalStatuses((prev) => {
      const next = new Map(prev);
      next.set(rawValue, 'rejected');
      return next;
    });
  }, []);

  const handleEdit = useCallback(
    (rawValue: string, currentCanonical: string) => {
      setEditValues((prev) => {
        const next = new Map(prev);
        next.set(rawValue, currentCanonical);
        return next;
      });
    },
    []
  );

  const handleEditChange = useCallback((rawValue: string, value: string) => {
    setEditValues((prev) => {
      const next = new Map(prev);
      next.set(rawValue, value);
      return next;
    });
  }, []);

  const handleEditConfirm = useCallback(
    (proposal: AgentProposal) => {
      const editedValue = editValues.get(proposal.raw_value);
      if (!editedValue) return;

      correctionMutation.mutate(
        {
          field: activeField,
          rawValue: proposal.raw_value,
          canonicalValue: editedValue,
          evidence: proposal.reasoning,
        },
        {
          onSuccess: () => {
            setProposalStatuses((prev) => {
              const next = new Map(prev);
              next.set(proposal.raw_value, 'edited');
              return next;
            });
            setEditValues((prev) => {
              const next = new Map(prev);
              next.delete(proposal.raw_value);
              return next;
            });
            queryClient.invalidateQueries({ queryKey: ['coverage'] });
          },
        }
      );
    },
    [activeField, correctionMutation, editValues, queryClient]
  );

  const handleApproveAll = useCallback(
    (proposals: AgentProposal[]) => {
      for (const p of proposals) {
        if (!proposalStatuses.has(p.raw_value)) {
          handleApprove(p);
        }
      }
    },
    [handleApprove, proposalStatuses]
  );

  const handleInvestigate = useCallback(
    (message: string) => {
      sendMessage(message);
    },
    [sendMessage]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(inputValue);
      }
    },
    [inputValue, sendMessage]
  );

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="mb-4">
        <h1 className="text-2xl font-semibold text-gray-900 mb-2">
          Agent Chat
        </h1>
        <p className="text-gray-500">
          Interact with normalization agents to analyze clusters, propose
          canonical values, and batch-resolve issues.
        </p>
      </div>

      {/* Agent field tabs */}
      <div className="flex gap-1 mb-4">
        {AGENT_FIELDS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => switchField(f)}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeField === f
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
            }`}
          >
            {FIELD_LABELS[f]}
          </button>
        ))}
      </div>

      {/* Two-column layout */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* Left: Chat (70%) */}
        <div className="flex-[7] flex flex-col bg-white rounded-lg border border-gray-200 shadow-sm min-h-0">
          {/* Messages */}
          <div className="flex-1 p-4 overflow-y-auto">
            {messages.length === 0 && !agentMutation.isPending && (
              <div className="flex flex-col items-center justify-center h-full text-center px-8">
                <div className="w-16 h-16 rounded-full bg-indigo-100 flex items-center justify-center mb-4">
                  <svg className="w-8 h-8 text-indigo-600" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold text-gray-800 mb-2">
                  {FIELD_LABELS[activeField]} Normalization Agent
                </h3>
                <p className="text-gray-500 text-sm mb-6 max-w-md">
                  This agent analyzes gaps in {FIELD_LABELS[activeField].toLowerCase()} normalization,
                  clusters related issues, and proposes fixes using AI. Start by clicking
                  the button below.
                </p>
                <button
                  type="button"
                  onClick={() => sendMessage('Analyze')}
                  className="bg-indigo-600 text-white px-6 py-3 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm"
                >
                  Start Analysis
                </button>
                <div className="mt-8 text-left max-w-sm">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">How it works</p>
                  <ol className="text-xs text-gray-400 space-y-1.5">
                    <li>1. <strong>Analyze</strong> -- Agent scans for normalization gaps</li>
                    <li>2. <strong>Investigate cluster</strong> -- Pick a cluster to explore</li>
                    <li>3. <strong>Propose mappings</strong> -- AI suggests canonical values</li>
                    <li>4. <strong>Approve / Reject / Edit</strong> -- You make the call</li>
                  </ol>
                </div>
              </div>
            )}

            {messages.map((msg, idx) => (
              <MessageBubble
                key={idx}
                message={msg}
                field={activeField}
                proposalStatuses={proposalStatuses}
                editValues={editValues}
                onApprove={handleApprove}
                onReject={handleReject}
                onEdit={handleEdit}
                onEditChange={handleEditChange}
                onEditConfirm={handleEditConfirm}
                onApproveAll={handleApproveAll}
                onInvestigate={handleInvestigate}
              />
            ))}

            {agentMutation.isPending && <TypingIndicator />}

            <div ref={chatEndRef} />
          </div>

          {/* Quick actions + input */}
          <div className="border-t border-gray-200 p-4">
            {/* Quick action buttons */}
            <div className="flex gap-2 mb-3">
              <button
                type="button"
                onClick={() => sendMessage('Analyze')}
                disabled={agentMutation.isPending}
                className="text-xs border border-indigo-200 text-indigo-600 px-3 py-1.5 rounded-md hover:bg-indigo-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Analyze Gaps
              </button>
              <button
                type="button"
                onClick={() => sendMessage('propose:0')}
                disabled={agentMutation.isPending}
                className="text-xs border border-green-200 text-green-600 px-3 py-1.5 rounded-md hover:bg-green-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Propose Mappings (Top Cluster)
              </button>
            </div>

            {/* Input */}
            <div className="flex gap-3">
              <input
                ref={inputRef}
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`Ask the ${FIELD_LABELS[activeField]} agent...`}
                disabled={agentMutation.isPending}
                className="flex-1 border border-gray-300 rounded-md px-4 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
              />
              <button
                type="button"
                onClick={() => sendMessage(inputValue)}
                disabled={agentMutation.isPending || !inputValue.trim()}
                className="bg-indigo-600 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Send
              </button>
            </div>
          </div>
        </div>

        {/* Right: Coverage sidebar (30%) */}
        <div className="flex-[3] bg-white rounded-lg border border-gray-200 shadow-sm p-5 overflow-y-auto">
          <CoverageSidebar field={activeField} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------

function MessageBubble({
  message,
  field,
  proposalStatuses,
  editValues,
  onApprove,
  onReject,
  onEdit,
  onEditChange,
  onEditConfirm,
  onApproveAll,
  onInvestigate,
}: {
  message: ChatMessage;
  field: AgentField;
  proposalStatuses: Map<string, ProposalStatus>;
  editValues: Map<string, string>;
  onApprove: (p: AgentProposal) => void;
  onReject: (raw: string) => void;
  onEdit: (raw: string, currentCanonical: string) => void;
  onEditChange: (raw: string, value: string) => void;
  onEditConfirm: (p: AgentProposal) => void;
  onApproveAll: (proposals: AgentProposal[]) => void;
  onInvestigate: (clusterId: string) => void;
}) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[80%] bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm">
          {message.content}
        </div>
      </div>
    );
  }

  // Agent message
  const data = message.data;
  const hasProposals = data?.proposals && data.proposals.length > 0;
  const hasClusters = data?.clusters && data.clusters.length > 0;

  return (
    <div className="flex items-start gap-3 mb-4">
      <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-xs font-bold text-gray-600 shrink-0">
        AI
      </div>
      <div className="max-w-[90%] min-w-0">
        <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-gray-800 whitespace-pre-wrap">
          {message.content}
        </div>

        {hasProposals && data?.proposals && (
          <ProposalTable
            proposals={data.proposals}
            field={field}
            proposalStatuses={proposalStatuses}
            editValues={editValues}
            onApprove={onApprove}
            onReject={onReject}
            onEdit={onEdit}
            onEditChange={onEditChange}
            onEditConfirm={onEditConfirm}
            onApproveAll={() => onApproveAll(data.proposals)}
          />
        )}

        {hasClusters && data?.clusters && (
          <ClusterCards
            clusters={data.clusters}
            onInvestigate={onInvestigate}
          />
        )}
      </div>
    </div>
  );
}
