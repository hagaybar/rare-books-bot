import { useCallback, useEffect, useRef, useState } from 'react';

export interface TourStep {
  /** CSS selector of the element to spotlight (waited for, up to 6s). */
  target: string;
  title: string;
  body: string;
  /** Runs before the step shows — used to DRIVE the UI (open a city, enter an ego…). */
  before?: () => void | Promise<void>;
}

interface Props {
  steps: TourStep[];
  onClose: (completed: boolean) => void;
}

const PAD = 8;

/** Driven onboarding tour (issue #38): dims the app, spotlights one element at
 *  a time, and navigates the UI between steps so new users *experience* the
 *  flow ("first press here… now see this") instead of reading about it. */
export default function Tour({ steps, onClose }: Props) {
  const [idx, setIdx] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [ready, setReady] = useState(false);
  const cancelled = useRef(false);

  const runStep = useCallback(async (i: number) => {
    setReady(false);
    setRect(null);
    const step = steps[i];
    try { await step.before?.(); } catch { /* navigation best-effort */ }
    // Wait for the target to exist and have a size (views load async)
    const t0 = Date.now();
    while (!cancelled.current && Date.now() - t0 < 6000) {
      const el = document.querySelector(step.target);
      const r = el?.getBoundingClientRect();
      if (el && r && r.width > 4 && r.height > 4) {
        (el as HTMLElement).scrollIntoView?.({ block: 'nearest' });
        setRect(el.getBoundingClientRect());
        setReady(true);
        return;
      }
      await new Promise((res) => setTimeout(res, 120));
    }
    setReady(true); // target never appeared — show the popover centered anyway
  }, [steps]);

  useEffect(() => {
    cancelled.current = false;
    runStep(idx);
    return () => { cancelled.current = true; };
  }, [idx, runStep]);

  // Track layout shifts while a step is visible
  useEffect(() => {
    if (!ready) return;
    const step = steps[idx];
    const sync = () => {
      const r = document.querySelector(step.target)?.getBoundingClientRect();
      if (r && r.width > 4) setRect(r);
    };
    window.addEventListener('resize', sync);
    const t = setInterval(sync, 500);
    return () => { window.removeEventListener('resize', sync); clearInterval(t); };
  }, [ready, idx, steps]);

  const step = steps[idx];
  const last = idx === steps.length - 1;

  // Popover position: below the spotlight when there's room, else above; centered fallback
  const popStyle: React.CSSProperties = rect
    ? (() => {
        const below = rect.bottom + 180 < window.innerHeight;
        const top = below ? rect.bottom + PAD + 6 : Math.max(12, rect.top - 186);
        const left = Math.min(Math.max(12, rect.left + rect.width / 2 - 170), window.innerWidth - 352);
        return { top, left };
      })()
    : { top: '40%', left: '50%', transform: 'translateX(-50%)' };

  return (
    <div className="fixed inset-0 z-[60]">
      {/* Spotlight: a transparent cutout whose huge shadow dims everything else */}
      {rect ? (
        <div
          className="absolute rounded-xl transition-all duration-300"
          style={{
            top: rect.top - PAD, left: rect.left - PAD,
            width: rect.width + PAD * 2, height: rect.height + PAD * 2,
            boxShadow: '0 0 0 9999px rgba(15, 23, 42, 0.6)',
            pointerEvents: 'none',
          }}
        />
      ) : (
        <div className="absolute inset-0 bg-slate-900/60" />
      )}

      {ready && (
        <div
          className="absolute w-[340px] bg-white rounded-xl shadow-2xl p-4 transition-all duration-300"
          style={popStyle}
        >
          <div className="text-[11px] font-semibold text-indigo-600 uppercase tracking-wider">
            {idx + 1} / {steps.length}
          </div>
          <h3 className="mt-0.5 text-base font-semibold text-gray-900">{step.title}</h3>
          <p className="mt-1 text-sm text-gray-600 leading-snug">{step.body}</p>
          <div className="mt-3 flex items-center justify-between">
            <button onClick={() => onClose(false)} className="text-xs text-gray-400 hover:text-gray-600">
              Skip tour
            </button>
            <div className="flex items-center gap-2">
              {idx > 0 && (
                <button
                  onClick={() => setIdx(idx - 1)}
                  className="px-3 py-1.5 text-sm text-gray-600 rounded-lg hover:bg-gray-100"
                >
                  Back
                </button>
              )}
              <button
                onClick={() => (last ? onClose(true) : setIdx(idx + 1))}
                className="px-3.5 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700"
              >
                {last ? 'Done — explore!' : 'Next'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
