import { useEffect, useRef, useState } from 'react';
import { authenticatedFetch } from '../../api/auth';

interface SessionEntry {
  session_id: string;
  title: string | null;
  message_count: number;
  last_activity: string | null;
}

interface Props {
  activeSessionId: string | null;
  onSelect: (sessionId: string) => void;
}

function when(ts: string | null): string {
  if (!ts) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '';
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  if (days === 0) return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days} days ago`;
  return d.toLocaleDateString();
}

/** Past-conversations dropdown (issue #15). Click an entry to reopen it via the
 *  existing ?session= restore path. */
export default function HistoryList({ activeSessionId, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const [sessions, setSessions] = useState<SessionEntry[] | null>(null);
  const [error, setError] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setError(false);
    authenticatedFetch('/chat/history?limit=20')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setSessions)
      .catch(() => setError(true));
  }, [open]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  return (
    <div ref={rootRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium
          text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 hover:text-gray-800 transition-colors"
        aria-expanded={open}
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2m6-2a10 10 0 11-20 0 10 10 0 0120 0z" />
        </svg>
        History
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 w-80 bg-white border border-gray-200 rounded-lg shadow-lg z-50 max-h-96 overflow-y-auto">
          <div className="px-3 pt-2 pb-1 text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
            Recent conversations
          </div>
          {error && <div className="px-3 py-2 text-sm text-gray-400">Couldn’t load history.</div>}
          {sessions && sessions.length === 0 && (
            <div className="px-3 py-2 text-sm text-gray-400">No past conversations yet.</div>
          )}
          {sessions?.map((s) => (
            <button
              key={s.session_id}
              onClick={() => { setOpen(false); onSelect(s.session_id); }}
              // preventDefault on mousedown so focus juggling can't swallow the click
              onMouseDown={(e) => e.preventDefault()}
              className={`w-full text-start px-3 py-2 hover:bg-gray-50 border-t border-gray-100 ${
                s.session_id === activeSessionId ? 'bg-blue-50' : ''
              }`}
            >
              <div className="text-sm text-gray-800 truncate">
                <bdi dir="auto">{s.title || 'Untitled conversation'}</bdi>
              </div>
              <div className="text-[11px] text-gray-400">
                {when(s.last_activity)}{s.message_count ? ` · ${s.message_count} messages` : ''}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
