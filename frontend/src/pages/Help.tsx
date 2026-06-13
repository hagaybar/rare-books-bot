/**
 * "How It Works" — a friendly, growing explainer of the data flow, from a raw
 * catalog record to a searchable answer. Built incrementally: each topic we map
 * out becomes a new entry in SECTIONS (id + title + body). The running example
 * is one real book — a 1553 Hebrew book printed in Venice by the Bragadin press
 * — followed from MARC XML all the way to an answer.
 */
import { useEffect, useState, type ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Small presentational helpers (kept local — this page is self-contained)
// ---------------------------------------------------------------------------

/** A soft callout box for a concrete example. */
function Example({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50/60 p-4 text-sm">
      {title && (
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-700">
          {title}
        </div>
      )}
      <div className="space-y-1 text-gray-700">{children}</div>
    </div>
  );
}

/** A raw → normalized before/after row. Hebrew renders right-to-left safely. */
function BeforeAfter({ raw, norm, note }: { raw: string; norm: string; note?: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2 font-mono text-[13px]">
      <bdi className="rounded bg-white px-2 py-0.5 ring-1 ring-gray-200">{raw}</bdi>
      <span className="text-gray-400">→</span>
      <bdi className="rounded bg-emerald-50 px-2 py-0.5 ring-1 ring-emerald-200">{norm}</bdi>
      {note && <span className="font-sans text-xs text-gray-500">{note}</span>}
    </div>
  );
}

interface Section {
  id: string;
  title: string;
  body: ReactNode;
}

// ---------------------------------------------------------------------------
// The content. To grow the page, add a new {id, title, body} entry here.
// ---------------------------------------------------------------------------

const SECTIONS: Section[] = [
  {
    id: 'source',
    title: '1. The source of truth: the catalog record',
    body: (
      <>
        <p>
          Every book in this collection begins life as a <strong>MARC XML record</strong> — the
          standard format libraries use to describe a book. Think of it as the book's official
          ID card: who made it, where and when it was printed, what it's about.
        </p>
        <p className="mt-2">
          This is the one rule everything else rests on: <strong>the catalog record is the only
          source of truth.</strong> The system never invents facts. When it answers a question,
          it must be able to point back to the exact field in this record that justifies the
          answer. No record, no claim.
        </p>
        <Example title="Our running example — one real book">
          <p>
            We'll follow a single book through the whole journey: a Hebrew book{' '}
            <strong>printed in Venice in 1553 by the Bragadin press</strong>. On its catalog card,
            the key fields look roughly like this:
          </p>
          <div className="mt-2 space-y-0.5 font-mono text-[13px]">
            <div>
              place &amp; printer ·{' '}
              <bdi>ויניציאה : נדפס במצות האדון מסיר אלוויז בראגאדין</bdi>
            </div>
            <div>year · 1553</div>
            <div>
              language · <span className="text-gray-500">heb (Hebrew)</span>
            </div>
          </div>
        </Example>
      </>
    ),
  },
  {
    id: 'journey',
    title: '2. The journey: from XML to searchable tables',
    body: (
      <>
        <p>
          The raw record doesn't go straight into search. It travels through three steps, and
          keeping them separate is what makes the system trustworthy:
        </p>
        <ol className="mt-2 list-decimal space-y-2 pl-5">
          <li>
            <strong>Parse</strong> — read the XML into a tidy record, faithfully. Nothing is
            interpreted or changed yet; the original values are preserved exactly.
          </li>
          <li>
            <strong>Normalize</strong> — add a cleaned-up version of certain fields{' '}
            <em>alongside</em> the original (never replacing it). This is what lets a search for
            "Venice" find a book whose card says <bdi>ויניציאה</bdi>.
          </li>
          <li>
            <strong>Index</strong> — write everything into the database tables the chatbot
            actually searches (<code>records</code>, <code>imprints</code>, <code>agents</code>,{' '}
            <code>subjects</code>, …).
          </li>
        </ol>
        <Example title="Our book, step by step">
          <p>The place on the Bragadin book travels like this:</p>
          <BeforeAfter raw="ויניציאה" norm="venice" note="raw kept, normalized form added" />
          <p className="mt-2">
            The original <bdi>ויניציאה</bdi> is never thrown away — it sits right next to{' '}
            <code>venice</code> in the <code>imprints</code> table, so the system can both{' '}
            <em>find</em> the book and <em>show its true wording</em>.
          </p>
        </Example>
      </>
    ),
  },
  {
    id: 'normalized',
    title: "3. What we clean up — and what we don't",
    body: (
      <>
        <p>Only <strong>five</strong> things get a normalized version, in two groups:</p>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg bg-gray-50 p-3 text-sm ring-1 ring-gray-200">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
              From the publication line
            </div>
            <ul className="list-disc pl-5">
              <li>Date (publication year/range)</li>
              <li>Place of publication</li>
              <li>Publisher / printer</li>
            </ul>
          </div>
          <div className="rounded-lg bg-gray-50 p-3 text-sm ring-1 ring-gray-200">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
              From each person / body
            </div>
            <ul className="list-disc pl-5">
              <li>Agent name (author, printer…)</li>
              <li>Agent role (their function)</li>
            </ul>
          </div>
        </div>
        <p className="mt-3">
          <strong>Titles and subjects are deliberately left as-is</strong> — they're searched in
          their original wording (subjects later gain a Hebrew companion for bilingual search, but
          that's an add-on, not normalization).
        </p>
        <p className="mt-2">
          Every normalized value carries five things, so it's always reversible and auditable:
          the <strong>raw</strong> value, the <strong>normalized</strong> value, a{' '}
          <strong>confidence</strong> score, the <strong>method</strong> used, and an{' '}
          <strong>evidence path</strong> back to the original field.
        </p>
        <Example title="Our book's printer">
          <BeforeAfter
            raw="נדפס במצות האדון מסיר אלוויז בראגאדין"
            norm="bragadin press, venice"
            note="confidence 0.95 · method: alias_map"
          />
        </Example>
      </>
    ),
  },
  {
    id: 'dates',
    title: '4. Dates, in depth',
    body: (
      <>
        <p>
          Dates are the trickiest field, so they get a whole family of methods. They fall into
          three groups:
        </p>
        <ul className="mt-2 list-disc space-y-2 pl-5">
          <li>
            <strong>Plain numbers</strong> — a 4-digit year, with or without brackets, ranges, and
            "circa" approximations.
          </li>
          <li>
            <strong>Hebrew-calendar conversions</strong> — Hebrew year-letters (gematria) converted
            to a Gregorian year. These are the hardest and most error-prone.
          </li>
          <li>
            <strong>Honest fallbacks</strong> — when a date is missing or unreadable, it's stored as
            empty with a confidence of 0 and a warning, never guessed.
          </li>
        </ul>
        <Example title="The same idea, four ways">
          <BeforeAfter raw="1680" norm="1680" note="exact · 0.99" />
          <BeforeAfter raw="[1680]" norm="1680" note="bracketed · 0.95" />
          <BeforeAfter raw="c. 1650" norm="1645–1655" note="circa, ±5 · 0.80" />
          <BeforeAfter raw="תקס&quot;ה" norm="1804/05" note="Hebrew gematria · lower confidence" />
        </Example>
        <p className="mt-3">
          <strong>Are these repeatable?</strong> Yes — every method is a fixed rule (no AI, no
          randomness), so the same record always produces the same result. But two honest caveats:
          a rule can be <em>reliably wrong</em> (a misread Hebrew year stays wrong every time), and
          a handful of dates were later hand-corrected directly in the database. So re-reading the
          XML reproduces the <em>parser's</em> output exactly — but not those manual corrections
          unless their fix scripts are re-run.
        </p>
      </>
    ),
  },
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function Help() {
  const [active, setActive] = useState<string>(SECTIONS[0].id);

  // Highlight the table-of-contents entry for the section currently in view.
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (visible) setActive(visible.target.id);
      },
      { rootMargin: '-20% 0px -70% 0px' },
    );
    SECTIONS.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, []);

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">How it works</h1>
        <p className="mt-1 text-gray-600">
          From an old book to an answer — follow one real 1553 Venice book through the whole
          journey. This page grows as we map more of the flow.
        </p>
      </header>

      <div className="flex gap-10">
        {/* Sticky mini table of contents */}
        <nav className="hidden w-48 shrink-0 lg:block">
          <div className="sticky top-8">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
              On this page
            </div>
            <ul className="space-y-1 text-sm">
              {SECTIONS.map((s) => (
                <li key={s.id}>
                  <a
                    href={`#${s.id}`}
                    className={`block rounded px-2 py-1 transition-colors ${
                      active === s.id
                        ? 'bg-gray-100 font-medium text-gray-900'
                        : 'text-gray-500 hover:text-gray-800'
                    }`}
                  >
                    {s.title}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </nav>

        {/* Sections */}
        <div className="min-w-0 flex-1 space-y-12">
          {SECTIONS.map((s) => (
            <section key={s.id} id={s.id} className="scroll-mt-8">
              <h2 className="mb-3 text-lg font-semibold text-gray-900">{s.title}</h2>
              <div className="leading-relaxed text-gray-700">{s.body}</div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
