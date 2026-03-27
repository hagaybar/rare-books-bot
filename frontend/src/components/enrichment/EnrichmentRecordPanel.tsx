import { useQuery } from '@tanstack/react-query';
import { fetchAgentRecords } from '../../api/metadata';

interface Props {
  wikidataId: string | null;
  agentNorm: string;
  displayName: string;
  lifespan: string;
  onClose: () => void;
}

export default function EnrichmentRecordPanel({
  wikidataId,
  agentNorm,
  displayName,
  lifespan,
  onClose,
}: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['agent-records', wikidataId || agentNorm],
    queryFn: () => fetchAgentRecords(wikidataId || undefined, wikidataId ? undefined : agentNorm),
  });

  return (
    <div className="w-96 bg-white border-l shadow-lg flex flex-col h-full flex-shrink-0">
      {/* Header */}
      <div className="p-4 border-b flex justify-between items-start">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">{displayName}</h2>
          <p className="text-sm text-gray-500">
            {lifespan && <span>{lifespan} &middot; </span>}
            {data ? `${data.record_count} records` : '...'}
          </p>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">
          &times;
        </button>
      </div>

      {/* Records list */}
      <div className="flex-1 overflow-y-auto overscroll-contain p-4 space-y-3">
        {isLoading && <p className="text-sm text-gray-400">Loading records...</p>}
        {error && <p className="text-sm text-red-500">Could not load records.</p>}
        {data?.records.map((rec) => (
          <div key={rec.mms_id} className="border-b pb-2">
            {rec.primo_url ? (
              <a
                href={rec.primo_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium text-blue-600 hover:text-blue-800 leading-tight block"
              >
                {rec.title || 'Untitled'} &rarr;
              </a>
            ) : (
              <p className="text-sm font-medium text-gray-900 leading-tight">
                {rec.title || 'Untitled'}
              </p>
            )}
            <p className="text-xs text-gray-400 mt-0.5">
              {[rec.date_raw, rec.place_norm, rec.publisher_norm, rec.role]
                .filter(Boolean)
                .join(' \u00B7 ')}
            </p>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="p-4 border-t flex gap-2">
        <a
          href={`/chat?q=${encodeURIComponent(`books by ${displayName}`)}`}
          className="flex-1 text-center text-sm bg-blue-50 text-blue-700 px-3 py-2 rounded hover:bg-blue-100"
        >
          Ask in Chat &rarr;
        </a>
        <a
          href={data?.records[0]?.primo_url || '#'}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 text-center text-sm bg-gray-50 text-gray-700 px-3 py-2 rounded hover:bg-gray-100"
        >
          View in Primo &rarr;
        </a>
      </div>
    </div>
  );
}
