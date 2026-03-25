/**
 * External link to Primo catalog for a given MMS ID.
 *
 * Opens in a new tab. Falls back to client-side URL generation.
 */

import { buildPrimoUrl } from '../../api/chat';

interface PrimoLinkProps {
  mmsId: string;
  /** Override the resolved URL (from batch Primo URL fetch) */
  url?: string;
  children?: React.ReactNode;
}

export default function PrimoLink({ mmsId, url, children }: PrimoLinkProps) {
  const href = url ?? buildPrimoUrl(mmsId);

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 hover:underline transition-colors"
      title="Open in Primo catalog"
    >
      {children ?? (
        <>
          <svg
            className="w-3.5 h-3.5 shrink-0"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"
            />
          </svg>
          <span className="text-xs">Primo</span>
        </>
      )}
    </a>
  );
}
