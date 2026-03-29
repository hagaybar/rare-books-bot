/**
 * Chat API client for POST /chat and GET /chat/history endpoints.
 */

import type { ChatResponseAPI } from '../types/chat';
import { authenticatedFetch } from './auth';

// ---------------------------------------------------------------------------
// Recent chats (sidebar)
// ---------------------------------------------------------------------------

export interface RecentChat {
  session_id: string;
  title: string;
  message_count: number;
  last_activity: string;
}

/**
 * Fetch the 5 most recent chat sessions for the current user.
 *
 * Returns an empty array on error (non-critical UI element).
 */
export async function fetchRecentChats(): Promise<RecentChat[]> {
  try {
    const res = await authenticatedFetch('/chat/history');
    if (!res.ok) return [];
    return (await res.json()) as RecentChat[];
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Chat messages
// ---------------------------------------------------------------------------

/**
 * Send a message to the chat endpoint.
 *
 * @param message  User's natural-language query
 * @param sessionId  Optional session ID for multi-turn conversations
 * @returns Parsed ChatResponseAPI from the backend
 * @throws Error on network or HTTP errors
 */
export async function sendChatMessage(
  message: string,
  sessionId?: string | null,
): Promise<ChatResponseAPI> {
  const body: Record<string, unknown> = { message };
  if (sessionId) {
    body.session_id = sessionId;
  }

  const res = await authenticatedFetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Chat API error ${res.status}: ${text}`);
  }

  return res.json() as Promise<ChatResponseAPI>;
}

/**
 * Batch-resolve Primo URLs for a set of MMS IDs.
 *
 * @param mmsIds  Array of MMS IDs to resolve
 * @returns Map from MMS ID to Primo permalink URL
 */
export async function fetchPrimoUrls(
  mmsIds: string[],
): Promise<Record<string, string>> {
  if (mmsIds.length === 0) return {};

  try {
    const res = await authenticatedFetch('/metadata/primo-urls', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mms_ids: mmsIds }),
    });

    if (!res.ok) {
      // Fallback silently -- Primo URLs are non-critical
      return {};
    }

    const data = (await res.json()) as Record<string, string>;
    return data;
  } catch {
    // Batch endpoint may not be available; return empty
    return {};
  }
}

/**
 * Generate a client-side Primo permalink as a fallback.
 *
 * @param mmsId  The MMS ID for the record
 * @returns Primo URL string
 */
export function buildPrimoUrl(mmsId: string): string {
  return `https://tau.primo.exlibrisgroup.com/nde/search?query=${encodeURIComponent(mmsId)}&tab=TAU&search_scope=TAU&vid=972TAU_INST:NDE`;
}
