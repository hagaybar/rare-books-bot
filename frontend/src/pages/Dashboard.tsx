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
import { useCoverage } from '../hooks/useMetadata';
import type { FieldCoverage, CoverageReport } from '../types/metadata';

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

function CoverageBar({
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

  // Sort bands from high to low for consistent stacking
  const sortedBands = [...coverage.confidence_distribution].sort(
    (a, b) => b.min_confidence - a.min_confidence
  );

  return (
    <button
      type="button"
      onClick={() => navigate(`/workbench?field=${fieldKey}`)}
      className="w-full text-left group"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-gray-700 group-hover:text-indigo-600 transition-colors">
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
      onClick={() => navigate(`/workbench?field=${fieldKey}`)}
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
      <div className="flex gap-1 mb-4">
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

export default function Dashboard() {
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
