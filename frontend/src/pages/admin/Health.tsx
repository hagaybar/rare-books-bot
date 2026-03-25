import { useState, useEffect, useCallback } from 'react';

interface HealthBasic {
  status: string;
  database_connected: boolean;
  session_store_ok: boolean;
}

interface HealthExtended {
  db_file_size_bytes: number;
  db_last_modified: string | null;
  qa_db_exists: boolean;
  qa_db_size_bytes: number;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatDate(iso: string | null): string {
  if (!iso) return '--';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function Health() {
  const [basic, setBasic] = useState<HealthBasic | null>(null);
  const [extended, setExtended] = useState<HealthExtended | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      const [basicRes, extendedRes] = await Promise.all([
        fetch('/health'),
        fetch('/health/extended'),
      ]);

      if (!basicRes.ok) throw new Error(`Health check failed: ${basicRes.status}`);
      if (!extendedRes.ok) throw new Error(`Extended health check failed: ${extendedRes.status}`);

      const basicData = (await basicRes.json()) as HealthBasic;
      const extendedData = (await extendedRes.json()) as HealthExtended;

      setBasic(basicData);
      setExtended(extendedData);
      setError(null);
      setLastChecked(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch health data');
      setBasic(null);
      setExtended(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 30_000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  const statusColor =
    basic?.status === 'healthy'
      ? 'green'
      : basic?.status === 'degraded'
        ? 'yellow'
        : 'red';

  const statusStyles: Record<string, { bg: string; text: string; ring: string; dot: string }> = {
    green: { bg: 'bg-green-50', text: 'text-green-700', ring: 'ring-green-200', dot: 'bg-green-500' },
    yellow: { bg: 'bg-yellow-50', text: 'text-yellow-700', ring: 'ring-yellow-200', dot: 'bg-yellow-500' },
    red: { bg: 'bg-red-50', text: 'text-red-700', ring: 'ring-red-200', dot: 'bg-red-500' },
  };

  const s = statusStyles[statusColor] ?? statusStyles.red;

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-900 mb-2">System Health</h1>
      <p className="text-gray-500 mb-6">
        Monitor system status, database connections, and resource usage.
      </p>

      {loading && (
        <div className="flex items-center justify-center h-64 text-gray-400">
          <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-indigo-500" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading health data...
        </div>
      )}

      {error && !loading && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-red-700 mb-6">
          <h2 className="font-semibold mb-1">Health Check Failed</h2>
          <p className="text-sm">{error}</p>
          <button
            type="button"
            onClick={() => { setLoading(true); fetchHealth(); }}
            className="mt-3 text-sm font-medium text-red-600 hover:text-red-800 underline"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && basic && (
        <div className="space-y-6">
          {/* Status Card */}
          <div className={`rounded-lg border ring-1 ${s.ring} ${s.bg} p-6`}>
            <div className="flex items-center gap-3">
              <span className={`inline-block w-3 h-3 rounded-full ${s.dot}`} />
              <h2 className={`text-xl font-semibold capitalize ${s.text}`}>
                {basic.status}
              </h2>
            </div>
            {lastChecked && (
              <p className="text-xs text-gray-500 mt-2">
                Last checked: {lastChecked.toLocaleTimeString()}
              </p>
            )}
          </div>

          {/* Service Status */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <StatusCard
              label="Database Connection"
              ok={basic.database_connected}
              description={basic.database_connected ? 'Connected and responding' : 'Cannot connect to database'}
            />
            <StatusCard
              label="Session Store"
              ok={basic.session_store_ok}
              description={basic.session_store_ok ? 'Initialized and ready' : 'Not initialized'}
            />
          </div>

          {/* Database Details */}
          {extended && (
            <div>
              <h3 className="text-lg font-medium text-gray-900 mb-3">Database Details</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <InfoCard label="Bibliographic DB Size" value={formatBytes(extended.db_file_size_bytes)} />
                <InfoCard label="Last Modified" value={formatDate(extended.db_last_modified)} />
                <InfoCard
                  label="QA Database"
                  value={extended.qa_db_exists ? 'Present' : 'Not Found'}
                  valueColor={extended.qa_db_exists ? 'text-green-700' : 'text-gray-400'}
                />
                <InfoCard
                  label="QA DB Size"
                  value={extended.qa_db_exists ? formatBytes(extended.qa_db_size_bytes) : '--'}
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatusCard({ label, ok, description }: { label: string; ok: boolean; description: string }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <div className="flex items-center gap-2 mb-1">
        <span className={`inline-block w-2 h-2 rounded-full ${ok ? 'bg-green-500' : 'bg-red-500'}`} />
        <h4 className="text-sm font-medium text-gray-700">{label}</h4>
      </div>
      <p className={`text-sm ${ok ? 'text-green-600' : 'text-red-600'}`}>{description}</p>
    </div>
  );
}

function InfoCard({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <p className={`text-lg font-semibold tabular-nums ${valueColor ?? 'text-gray-900'}`}>{value}</p>
    </div>
  );
}
