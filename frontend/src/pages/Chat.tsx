/**
 * Chat page -- primary discovery interface for the Rare Books Bot.
 *
 * Full-height conversational layout with:
 * - Scrollable message history
 * - Fixed-bottom input bar
 * - Welcome state with example query chips
 * - WebSocket streaming with thinking mode and progressive text
 * - HTTP POST fallback when WebSocket is unavailable
 * - Phase indicator and confidence display
 * - Follow-up suggestion chips
 * - Clarification prompts
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import type { ChatMessage, ChatResponse, StreamingState } from '../types/chat';
import { sendChatMessage, fetchPrimoUrls } from '../api/chat';
import { authenticatedFetch } from '../api/auth';
import { useAppStore } from '../stores/appStore';
import { useAuthStore } from '../stores/authStore';
import MessageBubble from '../components/chat/MessageBubble';
import FollowUpChips from '../components/chat/FollowUpChips';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EXAMPLE_QUERIES = [
  'books published in Amsterdam',
  'Hebrew books printed in Venice',
  'books from the 16th century',
  'books about medicine',
  'books by Maimonides',
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let messageIdCounter = 0;
function nextId(): string {
  messageIdCounter += 1;
  return `msg-${Date.now()}-${messageIdCounter}`;
}

/**
 * Build the WebSocket URL that works with the Vite dev proxy.
 * The Vite config proxies /ws -> ws://localhost:8000, so we build
 * a relative ws:// URL from the current page origin.
 */
function getWsUrl(): string {
  const loc = window.location;
  const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
  // In dev mode (Vite on :5173/:5174), connect directly to backend on :8000
  // to avoid proxy issues. In production (same origin), use loc.host.
  if (loc.port === '5173' || loc.port === '5174') {
    return `${protocol}//${loc.hostname}:8000/ws/chat`;
  }
  return `${protocol}//${loc.host}/ws/chat`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Chat() {
  const { sessionId, setSessionId } = useAppStore();
  const user = useAuthStore((s) => s.user);
  const [searchParams] = useSearchParams();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [primoUrls, setPrimoUrls] = useState<Record<string, string>>({});
  const [restoredSessionId, setRestoredSessionId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  /** Ref to the WebSocket for the current streaming request. */
  const wsRef = useRef<WebSocket | null>(null);
  /** ID of the assistant message being streamed. */
  const streamingMsgIdRef = useRef<string | null>(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Clean up WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  // Restore session from URL ?session=XYZ parameter
  useEffect(() => {
    const urlSessionId = searchParams.get('session');
    if (!urlSessionId || urlSessionId === restoredSessionId) return;

    setRestoredSessionId(urlSessionId);
    setSessionId(urlSessionId);

    // Load session messages from the backend
    (async () => {
      try {
        const res = await authenticatedFetch(`/sessions/${urlSessionId}`);
        if (!res.ok) return;
        const data = await res.json();
        const restored: ChatMessage[] = (data.messages || []).map(
          (msg: { role: string; content: string; timestamp: string }, i: number) => ({
            id: `restored-${i}`,
            role: msg.role as 'user' | 'assistant',
            content: msg.content,
            candidateSet: null,
            suggestedFollowups: [],
            clarificationNeeded: null,
            phase: null,
            confidence: null,
            metadata: {},
            timestamp: new Date(msg.timestamp),
          }),
        );
        if (restored.length > 0) {
          setMessages(restored);
        }
      } catch {
        // Session load failed silently -- user can still start fresh
      }
    })();
  }, [searchParams, restoredSessionId, setSessionId]);

  // ------------------------------------------------------------------
  // Update the streaming assistant message in-place
  // ------------------------------------------------------------------

  const updateStreamingMessage = useCallback(
    (updater: (prev: ChatMessage) => ChatMessage) => {
      const msgId = streamingMsgIdRef.current;
      if (!msgId) return;
      setMessages((prev) =>
        prev.map((m) => (m.id === msgId ? updater(m) : m)),
      );
    },
    [],
  );

  // ------------------------------------------------------------------
  // WebSocket streaming send
  // ------------------------------------------------------------------

  const sendViaWebSocket = useCallback(
    async (text: string): Promise<void> => {
      // Ensure token is fresh before opening WebSocket (WS can't auto-refresh on 401)
      const meRes = await fetch('/auth/me', { credentials: 'include' });
      if (!meRes.ok) {
        const refreshRes = await fetch('/auth/refresh', { method: 'POST', credentials: 'include' });
        if (!refreshRes.ok) {
          throw new Error('Session expired');
        }
      }

      return new Promise((resolve, reject) => {
        let ws: WebSocket;
        try {
          ws = new WebSocket(getWsUrl());
        } catch {
          reject(new Error('WebSocket not supported'));
          return;
        }
        wsRef.current = ws;

        // Create the placeholder assistant message in thinking state
        const assistantMsgId = nextId();
        streamingMsgIdRef.current = assistantMsgId;

        const assistantMsg: ChatMessage = {
          id: assistantMsgId,
          role: 'assistant',
          content: '',
          candidateSet: null,
          suggestedFollowups: [],
          clarificationNeeded: null,
          phase: null,
          confidence: null,
          metadata: {},
          timestamp: new Date(),
          streamingState: 'thinking' as StreamingState,
          thinkingSteps: [],
        };
        setMessages((prev) => [...prev, assistantMsg]);

        const connectionTimeout = setTimeout(() => {
          if (ws.readyState === WebSocket.CONNECTING) {
            ws.close();
            reject(new Error('WebSocket connection timeout'));
          }
        }, 5000);

        ws.onopen = () => {
          clearTimeout(connectionTimeout);
          ws.send(JSON.stringify({
            message: text,
            session_id: sessionId,
          }));
        };

        ws.onmessage = (event) => {
          let data: Record<string, unknown>;
          try {
            data = JSON.parse(event.data as string) as Record<string, unknown>;
          } catch {
            return;
          }

          const msgType = data.type as string;

          switch (msgType) {
            case 'session_created': {
              const newSessionId = data.session_id as string;
              if (newSessionId) {
                setSessionId(newSessionId);
              }
              break;
            }

            case 'thinking': {
              const thinkingText = data.text as string ?? data.message as string ?? '';
              if (thinkingText) {
                updateStreamingMessage((prev) => ({
                  ...prev,
                  streamingState: 'thinking',
                  thinkingSteps: [...(prev.thinkingSteps ?? []), thinkingText],
                }));
              }
              break;
            }

            case 'progress': {
              // Legacy progress messages -- treat as thinking steps
              const progressText = data.message as string ?? '';
              if (progressText) {
                updateStreamingMessage((prev) => ({
                  ...prev,
                  streamingState: 'thinking',
                  thinkingSteps: [...(prev.thinkingSteps ?? []), progressText],
                }));
              }
              break;
            }

            case 'stream_start': {
              updateStreamingMessage((prev) => ({
                ...prev,
                streamingState: 'streaming',
              }));
              break;
            }

            case 'stream_chunk': {
              const chunkText = data.text as string ?? '';
              if (chunkText) {
                updateStreamingMessage((prev) => ({
                  ...prev,
                  streamingState: 'streaming',
                  content: prev.content + chunkText,
                }));
              }
              break;
            }

            case 'batch': {
              // Legacy batch messages from the existing WS protocol
              // Treat as a progress step
              const batchNum = data.batch_num as number ?? 0;
              const totalBatches = data.total_batches as number ?? 0;
              if (batchNum && totalBatches) {
                updateStreamingMessage((prev) => ({
                  ...prev,
                  streamingState: 'thinking',
                  thinkingSteps: [
                    ...(prev.thinkingSteps ?? []),
                    `Loading results (batch ${String(batchNum)}/${String(totalBatches)})...`,
                  ],
                }));
              }
              break;
            }

            case 'complete': {
              const resp = data.response as ChatResponse | undefined;
              if (resp) {
                // Persist session ID from the complete response
                if (resp.session_id && resp.session_id !== sessionId) {
                  setSessionId(resp.session_id);
                }

                updateStreamingMessage((prev) => ({
                  ...prev,
                  streamingState: 'complete',
                  // Use the complete response content if we didn't get stream chunks
                  content: prev.content || resp.message,
                  candidateSet: resp.candidate_set,
                  suggestedFollowups: resp.suggested_followups,
                  clarificationNeeded: resp.clarification_needed,
                  phase: resp.phase,
                  confidence: resp.confidence,
                  metadata: resp.metadata,
                }));

                // Batch-resolve Primo URLs for any new candidates
                if (resp.candidate_set?.candidates.length) {
                  const ids = resp.candidate_set.candidates.map((c) => c.record_id);
                  fetchPrimoUrls(ids)
                    .then((urls) => {
                      if (Object.keys(urls).length > 0) {
                        setPrimoUrls((prev) => ({ ...prev, ...urls }));
                      }
                    })
                    .catch(() => {
                      // Primo URL resolution is non-critical
                    });
                }
              }

              streamingMsgIdRef.current = null;
              ws.close();
              wsRef.current = null;
              resolve();
              break;
            }

            case 'error': {
              const errorMessage = data.message as string ?? 'Unknown WebSocket error';
              streamingMsgIdRef.current = null;
              ws.close();
              wsRef.current = null;
              reject(new Error(errorMessage));
              break;
            }

            default:
              // Unknown message type -- ignore
              break;
          }
        };

        ws.onerror = () => {
          clearTimeout(connectionTimeout);
          streamingMsgIdRef.current = null;
          wsRef.current = null;
          // Remove the placeholder assistant message
          setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId));
          reject(new Error('WebSocket connection failed'));
        };

        ws.onclose = (event) => {
          clearTimeout(connectionTimeout);
          wsRef.current = null;
          // If the connection closed before we got a complete message,
          // finalize whatever we have
          if (streamingMsgIdRef.current === assistantMsgId) {
            // Abnormal close -- mark as complete with whatever text we have
            if (!event.wasClean) {
              updateStreamingMessage((prev) => ({
                ...prev,
                streamingState: 'complete',
                content: prev.content || 'Connection lost. Please try again.',
              }));
            } else {
              // Clean close but no complete message received; finalize
              updateStreamingMessage((prev) => ({
                ...prev,
                streamingState: 'complete',
              }));
            }
            streamingMsgIdRef.current = null;
            resolve();
          }
        };
      });
    },
    [sessionId, setSessionId, updateStreamingMessage],
  );

  // ------------------------------------------------------------------
  // HTTP fallback send (existing logic)
  // ------------------------------------------------------------------

  const sendViaHttp = useCallback(
    async (text: string) => {
      const apiResponse = await sendChatMessage(text, sessionId);

      if (!apiResponse.success || !apiResponse.response) {
        throw new Error(apiResponse.error ?? 'Unknown error from server');
      }

      const resp = apiResponse.response;

      // Persist session ID
      if (resp.session_id && resp.session_id !== sessionId) {
        setSessionId(resp.session_id);
      }

      // Build assistant message
      const botMsg: ChatMessage = {
        id: nextId(),
        role: 'assistant',
        content: resp.message,
        candidateSet: resp.candidate_set,
        suggestedFollowups: resp.suggested_followups,
        clarificationNeeded: resp.clarification_needed,
        phase: resp.phase,
        confidence: resp.confidence,
        metadata: resp.metadata,
        timestamp: new Date(),
        streamingState: 'complete',
      };
      setMessages((prev) => [...prev, botMsg]);

      // Batch-resolve Primo URLs for any new candidates
      if (resp.candidate_set?.candidates.length) {
        const ids = resp.candidate_set.candidates.map((c) => c.record_id);
        const urls = await fetchPrimoUrls(ids);
        if (Object.keys(urls).length > 0) {
          setPrimoUrls((prev) => ({ ...prev, ...urls }));
        }
      }
    },
    [sessionId, setSessionId],
  );

  // ------------------------------------------------------------------
  // Send message handler (WebSocket first, HTTP fallback)
  // ------------------------------------------------------------------

  const handleSend = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || loading) return;

      setInput('');
      if (inputRef.current) {
        inputRef.current.style.height = 'auto';
      }
      setError(null);

      // Add user message
      const userMsg: ChatMessage = {
        id: nextId(),
        role: 'user',
        content: trimmed,
        candidateSet: null,
        suggestedFollowups: [],
        clarificationNeeded: null,
        phase: null,
        confidence: null,
        metadata: {},
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setLoading(true);

      try {
        // Try WebSocket first for streaming experience
        await sendViaWebSocket(trimmed);
      } catch (wsErr) {
        // WebSocket failed -- fall back to HTTP POST
        console.warn('[Chat] WebSocket failed, falling back to HTTP:', wsErr instanceof Error ? wsErr.message : wsErr);
        try {
          await sendViaHttp(trimmed);
        } catch (httpErr) {
          const errMsg = httpErr instanceof Error ? httpErr.message : 'Something went wrong';
          setError(errMsg);
        }
      } finally {
        setLoading(false);
        // Re-focus input
        inputRef.current?.focus();
      }
    },
    [loading, sendViaWebSocket, sendViaHttp],
  );

  // ------------------------------------------------------------------
  // Input handlers
  // ------------------------------------------------------------------

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend(input);
    }
  };

  const handleFollowUp = (text: string) => {
    setInput(text);
    // Focus the input so the user can review/edit before sending
    inputRef.current?.focus();
  };

  // Auto-resize textarea
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  };

  // ------------------------------------------------------------------
  // Derived state: check if we are in streaming mode (WS active)
  // ------------------------------------------------------------------

  const isStreamingActive = streamingMsgIdRef.current !== null;

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Scrollable messages area */}
      <div className="flex-1 overflow-y-auto">
        {isEmpty ? (
          /* ---- Welcome state ---- */
          <div className="flex items-center justify-center min-h-full px-4">
            <div className="text-center max-w-lg">
              {/* Logo / icon */}
              <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center shadow-lg">
                <svg
                  className="w-8 h-8 text-white"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={1.5}
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"
                  />
                </svg>
              </div>

              <h1 className="text-2xl font-bold text-gray-900 mb-2">
                Rare Books Bot
              </h1>
              <p className="text-gray-500 text-sm mb-8 leading-relaxed">
                Explore a collection of 2,796 rare book records spanning 780 years.
                Ask a question in natural language to discover books by place,
                date, publisher, subject, or author.
              </p>

              {/* Example queries */}
              <div className="space-y-2">
                <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Try asking
                </p>
                <FollowUpChips
                  suggestions={EXAMPLE_QUERIES}
                  onSelect={handleFollowUp}
                />
              </div>
            </div>
          </div>
        ) : (
          /* ---- Message history ---- */
          <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
            {messages.map((msg, idx) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                onFollowUp={handleFollowUp}
                isLatest={idx === messages.length - 1 && msg.role === 'assistant'}
                primoUrls={primoUrls}
                loading={loading}
              />
            ))}

            {/* Loading indicator (only when not streaming -- streaming has its own UI) */}
            {loading && !isStreamingActive && (
              <div className="flex justify-start">
                <div className="px-4 py-3 rounded-2xl rounded-bl-md bg-white border border-gray-200 shadow-sm">
                  <div className="flex items-center gap-2">
                    <div className="flex gap-1">
                      <span className="w-2 h-2 rounded-full bg-blue-400 animate-bounce [animation-delay:0ms]" />
                      <span className="w-2 h-2 rounded-full bg-blue-400 animate-bounce [animation-delay:150ms]" />
                      <span className="w-2 h-2 rounded-full bg-blue-400 animate-bounce [animation-delay:300ms]" />
                    </div>
                    <span className="text-xs text-gray-400">Searching the collection...</span>
                  </div>
                </div>
              </div>
            )}

            {/* Scroll anchor */}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="border-t border-red-200 bg-red-50 px-4 py-2">
          <div className="max-w-3xl mx-auto flex items-center gap-2">
            <svg className="w-4 h-4 text-red-500 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
            <span className="text-sm text-red-700 flex-1">{error}</span>
            <button
              type="button"
              onClick={() => setError(null)}
              className="text-red-400 hover:text-red-600 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Input bar */}
      <div className="border-t border-gray-200 bg-white">
        <div className="max-w-3xl mx-auto px-4 py-3">
          {user?.role === 'guest' ? (
            /* Guest: show login prompt instead of input */
            <div className="text-center py-2">
              <p className="text-sm text-gray-500">
                <Link to="/login" className="text-blue-600 hover:text-blue-700 font-medium">
                  Login
                </Link>{' '}
                to use the chat
              </p>
            </div>
          ) : (
            <>
              {/* Quota badge for limited users */}
              {user?.role === 'limited' && user.token_limit != null && (
                <div className="text-xs text-gray-400 text-center mb-1">
                  Tokens: {user.tokens_used_this_month ?? 0} / {user.token_limit}
                </div>
              )}
              <div className="flex items-end gap-2">
                <div className="flex-1 relative">
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={handleInput}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask about rare books..."
                    rows={1}
                    disabled={loading}
                    className="w-full resize-none rounded-xl border border-gray-300 bg-gray-50 px-4 py-2.5
                      text-sm text-gray-900 placeholder:text-gray-400
                      focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                      disabled:opacity-50 disabled:cursor-not-allowed
                      transition-shadow"
                    style={{ maxHeight: '160px' }}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => handleSend(input)}
                  disabled={loading || !input.trim()}
                  className="shrink-0 w-10 h-10 rounded-xl bg-blue-600 text-white
                    flex items-center justify-center
                    hover:bg-blue-700 active:bg-blue-800
                    disabled:bg-gray-300 disabled:cursor-not-allowed
                    transition-colors shadow-sm cursor-pointer"
                  title="Send message"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                  </svg>
                </button>
              </div>
              <p className="text-[10px] text-gray-400 mt-1.5 text-center">
                Press Enter to send, Shift+Enter for new line
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
