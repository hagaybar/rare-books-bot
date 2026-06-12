/**
 * Feedback API client for POST /feedback ("mark as problematic" reports).
 */

import { authenticatedFetch } from './auth';

export interface FeedbackRequest {
  kind: 'message' | 'general';
  session_id?: string;
  message_id?: number;
  comment?: string;
}

export interface FeedbackResponse {
  report_id: string;
  github_issue_url: string | null;
}

/**
 * Submit a feedback report.
 *
 * @param req  Feedback payload (kind, optional session/message refs, comment)
 * @returns FeedbackResponse with report id and GitHub issue URL (null if pending)
 * @throws Error on network or HTTP errors
 */
export async function submitFeedback(req: FeedbackRequest): Promise<FeedbackResponse> {
  const resp = await authenticatedFetch('/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    const detail: { detail?: string } = await resp.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Feedback failed (${resp.status})`);
  }
  return resp.json() as Promise<FeedbackResponse>;
}
