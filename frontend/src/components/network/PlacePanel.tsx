import type { PlaceDetail } from '../../api/network';

interface Props {
  place: PlaceDetail;
  onClose: () => void;
  mobile?: boolean;
}

/** "Books printed here" panel (issue #29). */
export default function PlacePanel({ place, onClose, mobile }: Props) {
  const containerClass = mobile
    ? 'bg-white'
    : 'w-80 bg-white border-l shadow-lg overflow-y-auto flex-shrink-0';

  return (
    <div className={containerClass}>
      <div className={`${mobile ? 'px-4 pt-1 pb-3' : 'p-4'} border-b`}>
        <div className="flex justify-between items-start">
          <div className="min-w-0 flex-1">
            <h2 className={`${mobile ? 'text-base' : 'text-lg'} font-semibold text-gray-900 capitalize truncate`} dir="auto">
              {place.place_norm}
            </h2>
            <p className="text-sm text-gray-500">
              {place.total} book{place.total !== 1 ? 's' : ''} printed here
            </p>
          </div>
          {!mobile && (
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none ml-2">
              &times;
            </button>
          )}
        </div>
      </div>

      <div className={`${mobile ? 'px-4 py-3' : 'p-4'}`}>
        {place.works.length === 0 ? (
          <p className="text-sm text-gray-400">No imprints from this place in the collection.</p>
        ) : (
          <ul className="space-y-2">
            {place.works.map((w) => (
              <li key={w.mms_id} className="text-sm">
                {w.primo_url ? (
                  <a
                    href={w.primo_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    dir="auto"
                    className="text-blue-600 hover:text-blue-800 font-medium"
                  >
                    {w.title ?? w.mms_id}
                  </a>
                ) : (
                  <span dir="auto" className="font-medium text-gray-800">{w.title ?? w.mms_id}</span>
                )}
                <div className="text-xs text-gray-500">
                  {[w.date_label, w.publisher_display].filter(Boolean).join(' · ')}
                </div>
              </li>
            ))}
          </ul>
        )}
        {place.total > place.works.length && (
          <p className="text-xs text-gray-400 mt-3">
            Showing {place.works.length} of {place.total}.
          </p>
        )}
      </div>
    </div>
  );
}
