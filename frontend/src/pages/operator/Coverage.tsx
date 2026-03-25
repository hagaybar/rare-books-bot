import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { useCoverage } from '../../hooks/useMetadata';
import FieldBadge from '../../components/shared/FieldBadge';
import type { FieldCoverage, CoverageReport } from '../../types/metadata';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FIELD_KEYS = ['date', 'place', 'publisher', 'agent_name'] as const;
type FieldKey = (typeof FIELD_KEYS)[number];

const FIELD_LABELS: Record<FieldKey, string> = {
  date: 'Date',
  place: 'Place',
  publisher: 'Publisher',
  agent_name: 'Agent Name',
};

/** Map field keys to FieldBadge field type */
const FIELD_BADGE_MAP: Record<FieldKey, 'date' | 'place' | 'publisher' | 'agent'> = {
  date: 'date',
  place: 'place',
  publisher: 'publisher',
  agent_name: 'agent',
};

/** Fields that should use binary (resolved/unresolved) visualization */
const BINARY_FIELDS: FieldKey[] = ['place', 'publisher'];

function fieldCoverageOf(report: CoverageReport, key: FieldKey): FieldCoverage {
  const map: Record<FieldKey, FieldCoverage> = {
    date: report.date_coverage,
    place: report.place_coverage,
    publisher: report.publisher_coverage,
    agent_name: report.agent_name_coverage,
  };
  return map[key];
}

const BAND_COLORS: Record<string, string> = {
  high: '#22c55e',
  medium: '#eab308',
  low: '#f97316',
  very_low: '#ef4444',
};

const BAND_BG_CLASSES: Record<string, string> = {
  high: 'bg-green-500',
  medium: 'bg-yellow-500',
  low: 'bg-orange-500',
  very_low: 'bg-red-500',
};

const PIE_COLORS = [
  '#6366f1',
  '#22c55e',
  '#eab308',
  '#f97316',
  '#ef4444',
  '#3b82f6',
  '#a855f7',
  '#14b8a6',
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function bandKey(min: number, _max: number): string {
  if (min >= 0.95) return 'high';
  if (min >= 0.8) return 'medium';
  if (min >= 0.5) return 'low';
  return 'very_low';
}

function pct(n: number, total: number): number {
  if (total === 0) return 0;
  return Math.round((n / total) * 1000) / 10;
}

function fmt(n: number): string {
  return n.toLocaleString();
}

/** Count records at or above a confidence threshold */
function countResolved(coverage: FieldCoverage, threshold = 0.8): number {
  return coverage.confidence_distribution
    .filter((b) => b.min_confidence >= threshold)
    .reduce((sum, b) => sum + b.count, 0);
}

function qualityScore(report: CoverageReport): number {
  const weights: Record<FieldKey, number> = {
    date: 0.3,
    place: 0.3,
    publisher: 0.2,
    agent_name: 0.2,
  };
  let weightedSum = 0;
  let totalWeight = 0;
  for (const key of FIELD_KEYS) {
    const fc = fieldCoverageOf(report, key);
    const highBand = fc.confidence_distribution.find(
      (b) => b.min_confidence >= 0.95
    );
    const highCount = highBand ? highBand.count : 0;
    const total = fc.total_records;
    if (total > 0) {
      weightedSum += weights[key] * (highCount / total);
      totalWeight += weights[key];
    }
  }
  if (totalWeight === 0) return 0;
  return Math.round((weightedSum / totalWeight) * 1000) / 10;
}

function totalIssues(report: CoverageReport): number {
  let count = 0;
  for (const key of FIELD_KEYS) {
    count += fieldCoverageOf(report, key).flagged_items.length;
  }
  return count;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  subtitle,
  accent,
}: {
  label: string;
  value: string;
  subtitle?: string;
  accent?: string;
}) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm">
      <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
        {label}
      </h2>
      <p className={`mt-2 text-3xl font-semibold ${accent ?? 'text-gray-900'}`}>
        {value}
      </p>
      {subtitle && <p className="mt-1 text-sm text-gray-400">{subtitle}</p>}
    </div>
  );
}

/** Four-band confidence bar for date field */
function CoverageBarFull({
  fieldKey,
  coverage,
}: {
  fieldKey: FieldKey;
  coverage: FieldCoverage;
}) {
  const navigate = useNavigate();
  const total = coverage.total_records;
  const nonNull = coverage.non_null_count;
  const overallPct = pct(nonNull, total);

  const sortedBands = [...coverage.confidence_distribution].sort(
    (a, b) => b.min_confidence - a.min_confidence
  );

  return (
    <button
      type="button"
      onClick={() => navigate(`/operator/workbench?field=${fieldKey}`)}
      className="w-full text-left group"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-gray-700 group-hover:text-indigo-600 transition-colors flex items-center gap-2">
          <FieldBadge field={FIELD_BADGE_MAP[fieldKey]} size="sm" />
          {FIELD_LABELS[fieldKey]}
        </span>
        <span className="text-sm text-gray-500">{overallPct}% populated</span>
      </div>
      <div className="w-full h-5 bg-gray-200 rounded-full overflow-hidden flex">
        {sortedBands.map((band) => {
          const w = pct(band.count, total);
          if (w === 0) return null;
          const bk = bandKey(band.min_confidence, band.max_confidence);
          return (
            <div
              key={band.label}
              className={`${BAND_BG_CLASSES[bk]} h-full transition-all`}
              style={{ width: `${w}%` }}
              title={`${band.label}: ${fmt(band.count)} (${w}%)`}
            />
          );
        })}
      </div>
    </button>
  );
}

/** Binary resolved/unresolved bar for place and publisher */
function CoverageBarBinary({
  fieldKey,
  coverage,
}: {
  fieldKey: FieldKey;
  coverage: FieldCoverage;
}) {
  const navigate = useNavigate();
  const total = coverage.total_records;
  const resolved = countResolved(coverage, 0.8);
  const unresolved = total - resolved;
  const resolvedPct = pct(resolved, total);

  return (
    <button
      type="button"
      onClick={() => navigate(`/operator/workbench?field=${fieldKey}`)}
      className="w-full text-left group"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-gray-700 group-hover:text-indigo-600 transition-colors flex items-center gap-2">
          <FieldBadge field={FIELD_BADGE_MAP[fieldKey]} size="sm" />
          {FIELD_LABELS[fieldKey]}
        </span>
        <span className="text-sm text-gray-500">
          {resolvedPct}% resolved
          {unresolved > 0 && (
            <span className="text-gray-400 ml-1">({fmt(unresolved)} remaining)</span>
          )}
        </span>
      </div>
      <div className="w-full h-5 bg-gray-200 rounded-full overflow-hidden flex">
        {resolved > 0 && (
          <div
            className="bg-green-500 h-full transition-all"
            style={{ width: `${resolvedPct}%` }}
            title={`Resolved: ${fmt(resolved)} (${resolvedPct}%)`}
          />
        )}
        {unresolved > 0 && (
          <div
            className="bg-gray-300 h-full transition-all"
            style={{ width: `${pct(unresolved, total)}%` }}
            title={`Unresolved: ${fmt(unresolved)} (${pct(unresolved, total)}%)`}
          />
        )}
      </div>
      <div className="flex gap-3 mt-1">
        <span className="text-[10px] text-gray-400 flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-sm bg-green-500" />
          Resolved ({fmt(resolved)})
        </span>
        <span className="text-[10px] text-gray-400 flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-sm bg-gray-300" />
          Unresolved ({fmt(unresolved)})
        </span>
      </div>
    </button>
  );
}

/** Renders the appropriate bar type for a field */
function CoverageBar({
  fieldKey,
  coverage,
}: {
  fieldKey: FieldKey;
  coverage: FieldCoverage;
}) {
  if (BINARY_FIELDS.includes(fieldKey)) {
    return <CoverageBarBinary fieldKey={fieldKey} coverage={coverage} />;
  }
  return <CoverageBarFull fieldKey={fieldKey} coverage={coverage} />;
}

function GapCard({
  fieldKey,
  coverage,
}: {
  fieldKey: FieldKey;
  coverage: FieldCoverage;
}) {
  const navigate = useNavigate();
  const gapCount = coverage.null_count + coverage.flagged_items.length;
  const total = coverage.total_records;
  const ratio = total > 0 ? gapCount / total : 0;

  let borderColor = 'border-green-300';
  let textColor = 'text-green-700';
  let bgColor = 'bg-green-50';
  if (ratio > 0.3) {
    borderColor = 'border-red-300';
    textColor = 'text-red-700';
    bgColor = 'bg-red-50';
  } else if (ratio > 0.1) {
    borderColor = 'border-yellow-300';
    textColor = 'text-yellow-700';
    bgColor = 'bg-yellow-50';
  }

  return (
    <button
      type="button"
      onClick={() => navigate(`/operator/workbench?field=${fieldKey}`)}
      className={`w-full text-left rounded-lg border ${borderColor} ${bgColor} p-4 hover:shadow-md transition-shadow`}
    >
      <p className={`text-lg font-semibold ${textColor}`}>{fmt(gapCount)}</p>
      <p className="text-sm text-gray-600">
        {FIELD_LABELS[fieldKey]}: {fmt(coverage.null_count)} null +{' '}
        {fmt(coverage.flagged_items.length)} flagged
      </p>
    </button>
  );
}

/** Insight card for real normalization gaps beyond simple confidence */
function InsightCard({
  title,
  value,
  description,
  severity,
  linkTo,
  linkLabel,
}: {
  title: string;
  value: string;
  description: string;
  severity: 'warning' | 'info' | 'critical';
  linkTo: string;
  linkLabel: string;
}) {
  const navigate = useNavigate();
  const styles = {
    warning: {
      border: 'border-amber-300',
      bg: 'bg-amber-50',
      accent: 'text-amber-700',
      icon: 'text-amber-500',
    },
    info: {
      border: 'border-blue-300',
      bg: 'bg-blue-50',
      accent: 'text-blue-700',
      icon: 'text-blue-500',
    },
    critical: {
      border: 'border-red-300',
      bg: 'bg-red-50',
      accent: 'text-red-700',
      icon: 'text-red-500',
    },
  };
  const s = styles[severity];

  return (
    <div className={`rounded-lg border ${s.border} ${s.bg} p-4`}>
      <div className="flex items-start justify-between">
        <div>
          <p className={`text-sm font-semibold ${s.accent}`}>{title}</p>
          <p className={`text-2xl font-bold ${s.accent} mt-1`}>{value}</p>
          <p className="text-xs text-gray-600 mt-1 leading-relaxed">{description}</p>
        </div>
        <svg className={`w-5 h-5 ${s.icon} shrink-0 mt-1`} fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
        </svg>
      </div>
      <button
        type="button"
        onClick={() => navigate(linkTo)}
        className={`mt-3 text-xs font-medium ${s.accent} hover:underline flex items-center gap-1`}
      >
        {linkLabel}
        <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
        </svg>
      </button>
    </div>
  );
}

function MethodChart({ report }: { report: CoverageReport }) {
  const [activeField, setActiveField] = useState<FieldKey>('date');
  const fc = fieldCoverageOf(report, activeField);
  const data = fc.method_distribution.map((m) => ({
    name: m.method,
    value: m.count,
  }));

  return (
    <div>
      <h3 className="text-lg font-medium text-gray-900 mb-3">
        Method Distribution
      </h3>
      <div className="flex gap-1 mb-4 flex-wrap">
        {FIELD_KEYS.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setActiveField(key)}
            className={`px-3 py-1 text-sm rounded-md transition-colors ${
              activeField === key
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {FIELD_LABELS[key]}
          </button>
        ))}
      </div>
      {data.length === 0 ? (
        <div className="flex items-center justify-center h-48 text-gray-400">
          No method data available
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={55}
              outerRadius={95}
              paddingAngle={2}
              dataKey="value"
              nameKey="name"
            >
              {data.map((_entry, idx) => (
                <Cell
                  key={`cell-${idx.toString()}`}
                  fill={PIE_COLORS[idx % PIE_COLORS.length]}
                />
              ))}
            </Pie>
            <Tooltip
              formatter={(value) => fmt(Number(value))}
            />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function ConfidenceLegend() {
  const items = [
    { label: 'High (>=0.95)', color: BAND_COLORS.high },
    { label: 'Medium (0.80-0.95)', color: BAND_COLORS.medium },
    { label: 'Low (0.50-0.80)', color: BAND_COLORS.low },
    { label: 'Very Low (<0.50)', color: BAND_COLORS.very_low },
  ];
  return (
    <div className="flex gap-4 flex-wrap">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-1.5">
          <span
            className="inline-block w-3 h-3 rounded-sm"
            style={{ backgroundColor: item.color }}
          />
          <span className="text-xs text-gray-500">{item.label}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skeleton loader
// ---------------------------------------------------------------------------

function DashboardSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm"
          >
            <div className="h-4 bg-gray-200 rounded w-24 mb-3" />
            <div className="h-8 bg-gray-200 rounded w-16" />
          </div>
        ))}
      </div>
      <div className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm mb-8">
        <div className="h-5 bg-gray-200 rounded w-48 mb-4" />
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="mb-4">
            <div className="h-4 bg-gray-200 rounded w-32 mb-1" />
            <div className="h-5 bg-gray-200 rounded w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function Coverage() {
  const { data: report, isLoading, isError, error } = useCoverage();

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-900 mb-2">
        Coverage Dashboard
      </h1>
      <p className="text-gray-500 mb-8">
        Overview of normalization coverage, confidence distributions, and flagged
        items across all metadata fields.
      </p>

      {isLoading && <DashboardSkeleton />}

      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-red-700">
          <h2 className="font-semibold mb-1">Failed to load coverage data</h2>
          <p className="text-sm">
            {error instanceof Error ? error.message : 'Unknown error'}
          </p>
        </div>
      )}

      {report && (
        <>
          {/* --- Summary Stats --- */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <StatCard
              label="Total Records"
              value={fmt(report.total_imprint_rows)}
              subtitle={`${fmt(report.total_agent_rows)} agent rows`}
            />
            <StatCard
              label="Data Quality Score"
              value={`${qualityScore(report)}%`}
              subtitle="Weighted high-confidence ratio"
              accent={
                qualityScore(report) >= 70
                  ? 'text-green-600'
                  : qualityScore(report) >= 40
                    ? 'text-yellow-600'
                    : 'text-red-600'
              }
            />
            <StatCard
              label="Fields Tracked"
              value={String(FIELD_KEYS.length)}
              subtitle="date, place, publisher, agent"
            />
            <StatCard
              label="Issues Found"
              value={fmt(totalIssues(report))}
              subtitle="Flagged items across all fields"
              accent={totalIssues(report) > 0 ? 'text-red-600' : 'text-green-600'}
            />
          </div>

          {/* --- Coverage Bars --- */}
          <div className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm mb-8">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium text-gray-900">
                Per-Field Coverage
              </h2>
              <ConfidenceLegend />
            </div>
            <p className="text-xs text-gray-400 mb-4">
              Place and Publisher show binary resolved/unresolved view.
              Date and Agent use four-band confidence visualization.
              Click any bar to drill into the Workbench.
            </p>
            <div className="space-y-4">
              {FIELD_KEYS.map((key) => (
                <CoverageBar
                  key={key}
                  fieldKey={key}
                  coverage={fieldCoverageOf(report, key)}
                />
              ))}
            </div>
          </div>

          {/* --- Real Gaps: Normalization Insights --- */}
          <div className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm mb-8">
            <h2 className="text-lg font-medium text-gray-900 mb-1">
              Normalization Insights
            </h2>
            <p className="text-xs text-gray-400 mb-4">
              Beyond simple confidence scores, these are the real improvement opportunities
              that would increase discoverability and data quality.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <InsightCard
                title="Agent Normalization Gap"
                value="4,366"
                description="Agent names at base_clean level only (0% alias-mapped). 44.1% of agent roles classified as 'other'. These records need authority matching."
                severity="critical"
                linkTo="/operator/workbench?field=agent"
                linkLabel="View agent records"
              />
              <InsightCard
                title="Hebrew Publishers"
                value="553"
                description="Hebrew-script publishers scored at 0.95 confidence but not transliterated to Latin script. Discovery limited for non-Hebrew queries."
                severity="warning"
                linkTo="/operator/workbench?field=publisher"
                linkLabel="View publisher records"
              />
              <InsightCard
                title="Low-Confidence Records"
                value="121"
                description="Records with confidence below threshold across all fields. A small set relative to the collection, but easy wins for correction."
                severity="info"
                linkTo="/operator/workbench"
                linkLabel="View in Workbench"
              />
            </div>
          </div>

          {/* --- Bottom: Gaps + Method Chart --- */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Gap summary */}
            <div className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm">
              <h3 className="text-lg font-medium text-gray-900 mb-4">
                Gap Summary
              </h3>
              <div className="space-y-3">
                {FIELD_KEYS.map((key) => (
                  <GapCard
                    key={key}
                    fieldKey={key}
                    coverage={fieldCoverageOf(report, key)}
                  />
                ))}
              </div>
            </div>

            {/* Method distribution */}
            <div className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm">
              <MethodChart report={report} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
