import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { toast } from 'sonner';
import { submitFeedback } from '../../api/feedback';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: 'message' | 'general';
  sessionId?: string;
  messageDbId?: number;
}

export function FeedbackDialog({ open, onOpenChange, kind, sessionId, messageDbId }: Props) {
  const [comment, setComment] = useState('');
  const [sending, setSending] = useState(false);
  const commentRequired = kind === 'general';

  const handleSubmit = async () => {
    if (commentRequired && !comment.trim()) return;
    setSending(true);
    try {
      const res = await submitFeedback({
        kind,
        session_id: sessionId,
        message_id: messageDbId,
        comment: comment.trim() || undefined,
      });
      toast.success(
        res.github_issue_url
          ? 'Report sent — thanks! Issue opened.'
          : 'Report saved — it will sync to GitHub later.',
      );
      setComment('');
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to send report');
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 z-50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[28rem] max-w-[92vw] -translate-x-1/2 -translate-y-1/2 rounded-xl bg-white p-5 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-gray-900">
            {kind === 'message' ? 'Report this result as problematic' : 'Report a problem'}
          </Dialog.Title>
          <Dialog.Description className="mt-2 text-xs text-gray-500">
            {kind === 'message'
              ? 'Your conversation in this session plus technical traces will be sent to the developers. The report summary (your query, an answer excerpt, and your comment) will be publicly visible on GitHub.'
              : 'Your message will be publicly visible on GitHub. If a chat session is open, its technical traces are attached for the developers.'}
          </Dialog.Description>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={commentRequired ? 'Describe the problem…' : 'Optional: what looks wrong?'}
            className="mt-3 h-24 w-full rounded-md border border-gray-300 p-2 text-sm focus:border-blue-400 focus:outline-none"
          />
          <div className="mt-4 flex justify-end gap-2">
            <Dialog.Close className="rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100">
              Cancel
            </Dialog.Close>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={sending || (commentRequired && !comment.trim())}
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {sending ? 'Sending…' : 'Send report'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
