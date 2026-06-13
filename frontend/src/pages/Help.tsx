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

/** Plain-language definitions for the few unavoidable technical words. */
const GLOSSARY: { term: string; plain: string }[] = [
  {
    term: 'Catalog record (MARC)',
    plain:
      "The library's digital catalog card for a book, written in MARC — the standard format libraries share. It's the single source of truth here.",
  },
  {
    term: 'Field (e.g. 264, 008)',
    plain:
      'One labelled slot on the catalog card. Numbers like 264 (publication line) or 008 (coded summary) are just the librarians’ names for those slots.',
  },
  {
    term: 'Normalize / tidy up',
    plain:
      'Adding a cleaned, standard version of a value next to the original — e.g. the messy printed date "c. 1650" gets a tidy "1645–1655" beside it. The original is never erased.',
  },
  {
    term: 'Raw vs. normalized',
    plain:
      'Raw = exactly what the cataloger typed. Normalized = the tidy, searchable version. Both are kept, so nothing is lost and every answer can be traced back.',
  },
  {
    term: 'Lookup list (alias map)',
    plain:
      'A translation dictionary that maps many spellings of one thing to a single standard name — ויניציאה / Venezia / In Venetia all → venice.',
  },
  {
    term: 'Standard name (canonical form)',
    plain: 'The one agreed spelling everything collapses to, so search works across spellings and scripts.',
  },
  {
    term: 'Confidence',
    plain: 'A 0–1 score for how sure the tidy-up is. An exact year scores ~0.99; a tricky Hebrew-calendar conversion scores lower.',
  },
  {
    term: 'Evidence / provenance',
    plain: 'A pointer from any answer back to the exact spot in the original record that justifies it — the "show your work" trail.',
  },
  {
    term: 'Gives the same result every time',
    plain:
      'A step that, fed the same record, always produces the same output (no AI, nothing random in the moment). Most tidy-up steps are like this.',
  },
  {
    term: 'Authority / who’s-who',
    plain:
      'A curated reference record for a real person or printing house — its true name, dates, and place — that many spellings across the catalog can be linked to. Built and corrected by people over time.',
  },
  {
    term: 'Also-known-as spelling (variant)',
    plain:
      'One of the many ways a name was written on different books. All of a person or press’s variants are tied to its one authority record, so a search finds them all.',
  },
  {
    term: 'Role / relator',
    plain:
      'What a person did on the book — author, printer, translator, editor. Catalogers record these with standard codes called "relators".',
  },
  {
    term: 'Enrichment (Wikidata / web)',
    plain:
      'Extra detail pulled in from outside sources (like Wikidata) to fill gaps the catalog left — e.g. a person’s occupation. Useful, but not reproducible from the catalog card alone.',
  },
];

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
            <strong>Read it</strong> <span className="text-gray-400">(the step engineers call
            "parsing")</span> — copy the catalog record into a tidy form, faithfully. Nothing is
            interpreted or changed yet; the original wording is kept exactly.
          </li>
          <li>
            <strong>Tidy it up</strong> <span className="text-gray-400">("normalizing")</span> — add
            a cleaned-up version of a few fields <em>next to</em> the original (never replacing it).
            This is what lets a search for "Venice" find a book whose card says <bdi>ויניציאה</bdi>.
          </li>
          <li>
            <strong>File it away</strong> <span className="text-gray-400">("indexing")</span> — store
            everything in organized lists the system can search in an instant: one list for the
            books, one for places &amp; printers, one for the people involved, one for subjects, and
            so on.
          </li>
        </ol>
        <Example title="Our book, step by step">
          <p>The place on the Bragadin book travels like this:</p>
          <BeforeAfter raw="ויניציאה" norm="venice" note="raw kept, normalized form added" />
          <p className="mt-2">
            The original <bdi>ויניציאה</bdi> is never thrown away — it sits right next to{' '}
            <code>venice</code> in the places &amp; printers list, so the system can both{' '}
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
          <strong>Do these give the same result every time?</strong> Yes — every method is a
          hand-written rule (no AI, nothing random), so the same record always produces the same
          result. Two honest caveats, though: a rule can be <em>reliably wrong</em> (a misread
          Hebrew year stays wrong every time it runs), and a handful of dates were later corrected
          by hand directly in the database. So re-reading the catalog record reproduces the rules'
          output exactly — but not those manual corrections, unless they're re-applied.
        </p>
      </>
    ),
  },
  {
    id: 'place',
    title: '5. Places, and a twist about repeatability',
    body: (
      <>
        <p>A book's place of publication can come from two spots in the record:</p>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          <li>
            <strong>The publication line</strong> — the city as printed on the book, in whatever
            spelling or script the cataloger typed. This is the main source.{' '}
            <span className="text-gray-400">(librarians call this field 264, or 260 on older
            records)</span>
          </li>
          <li>
            <strong>A country code</strong> — a short coded country field, used only as a backup
            when the publication line has no usable city; it gives a country, not a city.{' '}
            <span className="text-gray-400">(field 008)</span>
          </li>
        </ul>
        <p className="mt-2">
          The goal is to gather every spelling and script of one city under a single{' '}
          <strong>standard name</strong> (like <code>venice</code>) while keeping the original
          wording untouched.
        </p>
        <Example title="Many spellings, one city">
          <BeforeAfter raw="In Venetia" norm="venice" />
          <BeforeAfter raw="Venezia" norm="venice" />
          <BeforeAfter raw="ויניציאה" norm="venice" note="our Bragadin book" />
          <p className="mt-2">
            All three land on <code>venice</code>, so a search for "Venice" finds the Hebrew book —
            and the screen still shows its real wording <bdi>ויניציאה</bdi>.
          </p>
        </Example>
        <p className="mt-3">
          How does it know <bdi>ויניציאה</bdi> means Venice? It checks the cleaned-up name against a{' '}
          <strong>lookup list</strong> — essentially a translation dictionary that says "this
          spelling means this city."{' '}
          <span className="text-gray-400">(engineers call it an "alias map")</span> Almost every
          place in the collection is matched this way; the few with no city fall back to
          country-level, or are honestly marked "unknown" rather than guessed.
        </p>
        <p className="mt-3">
          <strong>One subtle point — and it differs from dates.</strong> Checking a name against
          that lookup list always gives the same answer for the same book; no AI is involved in that
          moment. But the <em>list itself</em> was first drafted with the help of an AI model, which
          proposed matches like <bdi>ויניציאה</bdi> → <code>venice</code> (with safeguards, and
          refusing anything unclear). Drafting it that way isn't perfectly repeatable on its own — so
          the finished list was <strong>saved once and frozen</strong> as a fixed file. The result:
          the system gives the same answers today, because that one AI-assisted step already happened
          and its output was locked in. Put simply — dates are spelled out by hand-written rules from
          top to bottom; places are looked up against a dictionary that an AI helped write and that
          is now fixed in place.
        </p>
      </>
    ),
  },
  {
    id: 'publisher',
    title: '6. Printers & publishers — two layers',
    body: (
      <>
        <p>
          The printer or publisher is the <strong>"who printed it"</strong> part of the same
          publication line, right after the place.{' '}
          <span className="text-gray-400">(the subfield librarians call 264$b)</span> For our
          Bragadin book it reads <bdi>נדפס במצות האדון מסיר אלוויז בראגאדין</bdi>. Publishers get{' '}
          <strong>two</strong> layers of tidying, not one.
        </p>
        <p className="mt-3">
          <strong>Layer 1 — the same tidy-up as places.</strong> Many spellings of one printer
          collapse to a single standard name, using the same kind of lookup list:
        </p>
        <Example title="Many spellings, one press">
          <BeforeAfter raw="G. Bragadin" norm="bragadin press, venice" />
          <BeforeAfter raw="Nella Stamparia Bragadina" norm="bragadin press, venice" />
          <BeforeAfter raw="נדפס במצות האדון … בראגאדין" norm="bragadin press, venice" />
        </Example>
        <p className="mt-3">
          <strong>Layer 2 — a who's-who of printing houses.</strong> This is the part places don't
          have. Alongside the tidy name there's a separate <strong>reference list of real printing
          houses</strong> <span className="text-gray-400">(engineers call it the "publisher
          authorities")</span> — about 230 of them, each with the press's actual identity: its real
          name, its city, and the years it was active (the Bragadin press of Venice, roughly
          1550–1710).
        </p>
        <p className="mt-2">
          Each house also gathers its <strong>"also-known-as" spellings</strong> — the many ways
          that printer's name was written, across both Latin and Hebrew — so they all point to the{' '}
          <em>one</em> press. That's what lets a question like "books by the Bragadin press" find
          Hebrew-printed books whose cards never contain the Latin word "Bragadin".
        </p>
        <p className="mt-3">
          <strong>Same result every time?</strong> Layer 1 behaves just like places — fixed to
          apply, resting on a frozen AI-drafted list. Layer 2 is different: the who's-who is a{' '}
          <strong>curated reference list</strong>, built and corrected by people (with AI help) and
          grown over time — not an automatic rule. Connecting those 1550s Hebrew Bragadin books to
          the press, for instance, was a reviewed, human-approved addition to this list. It's your
          first look at the project's <strong>"authorities"</strong> — a who's-who that matters even
          more for people than for presses.
        </p>
      </>
    ),
  },
  {
    id: 'agents',
    title: '7. People & groups — the richest case',
    body: (
      <>
        <p>
          "Agents" are the people and groups attached to a book — authors, printers, translators,
          editors, and also organizations and collections.{' '}
          <span className="text-gray-400">(catalog fields 100/700 for people, 110/710 for
          organizations)</span> In this collection: about 4,600 people, 280 organizations, a handful
          of meetings. Each carries a <strong>name</strong> and a <strong>role</strong> (their job
          on the book). Two things get tidied — with one honest limit.
        </p>
        <p className="mt-3">
          <strong>1. The name → a tidy name.</strong> This is purely mechanical: lowercase, remove
          punctuation. <em>That's all.</em> The honest catch: this step does <strong>not</strong>{' '}
          merge a person's different-language names. <bdi>Maimonides, Moses</bdi> and{' '}
          <bdi>משה בן מימון</bdi> come out as two separate tidy names — light cleaning, no
          identity-matching here.
        </p>
        <p className="mt-3">
          <strong>2. The role → a standard job word</strong> (author, printer, translator…). Most
          come straight from codes the cataloger recorded{' '}
          <span className="text-gray-400">(librarians call these "relators")</span>. But where the
          card left the role blank or non-standard, many were <strong>filled in from outside
          sources</strong> — matched against Wikidata, and a few by web search. Some still have no
          role at all, and that's left honestly blank.
        </p>
        <p className="mt-3">
          <strong>The who's-who, at full strength.</strong> Pulling a person's many name-forms
          together into one identity happens in the same who's-who layer as printers — but here it
          goes furthest, and it leans on the <strong>catalog's own identity numbers</strong>. The
          National Library of Israel filed both <bdi>Maimonides, Moses</bdi> and{' '}
          <bdi>משה בן מימון</bdi> under the <em>same</em> number — so the system ties both scripts to{' '}
          <strong>one person</strong>, automatically.
        </p>
        <Example title="One person, two scripts, one identity">
          <BeforeAfter raw="Maimonides, Moses" norm="① person #…654005171" />
          <BeforeAfter raw="משה בן מימון" norm="① person #…654005171" note="same identity number" />
          <p className="mt-2">
            About 85% of people carry such a catalog link, so they unify cleanly. The other ~15%
            don't — and for those the system falls back on hand-built "also-known-as" lists, which
            are incomplete. <em>That gap is where several recent bugs lived.</em>
          </p>
        </Example>
        <p className="mt-3">
          <strong>Same result every time?</strong> This field braids three answers at once. The{' '}
          <strong>tidy name</strong> is fully repeatable. The <strong>role</strong> is mixed — the
          catalog-code part repeats, but the Wikidata/web-filled part comes from outside and may
          change if re-run. The <strong>identity link</strong> repeats where the catalog did the
          linking, but the gap-filling is human curation that lives outside the catalog record.
        </p>
      </>
    ),
  },
  {
    id: 'authorities',
    title: "8. The who's-who, up close: how it's built and used",
    body: (
      <>
        <p>
          The who's-who (the "authority" lists for people and presses) is worth a closer look,
          because it's what makes a search for one name find a book that spelled that name a
          completely different way. It is <strong>assembled by a program</strong> from the records,
          in layers.
        </p>
        <p className="mt-3 font-semibold text-gray-900">How it's built</p>
        <ol className="mt-1 list-decimal space-y-2 pl-5">
          <li>
            <strong>Gather by the catalog's identity number.</strong> All of a person's records are
            grouped by the identity number the cataloger assigned{' '}
            <span className="text-gray-400">(the authority link in the record)</span>. Each group
            becomes one who's-who entry, holding the real identity: the agreed name, whether it's a
            person or an organization, and links out to reference sources like Wikidata.
          </li>
          <li>
            <strong>Attach every spelling as an "also-known-as".</strong> Four kinds: the tidy names
            from the records themselves; alternative spellings; the <strong>other-script form</strong>{' '}
            (e.g. the Hebrew version of a Latin name); and an auto-generated "First Last" from
            "Last, First".
          </li>
          <li>
            <strong>Fill in from outside.</strong> A separate look-up to reference sources (mainly
            Wikidata) supplies many of those alternative and cross-script spellings, plus dates and
            occupations. This is how the system can bridge scripts even when the catalog itself
            didn't link them.
          </li>
          <li>
            <strong>Bare entries for the unlinked.</strong> The ~15% of people with no catalog
            identity number still get a minimal entry — just their one name, no extra spellings, no
            cross-script bridge. These thin entries are where searches most often miss.
          </li>
        </ol>
        <p className="mt-3 font-semibold text-gray-900">How it's used</p>
        <p className="mt-1">
          At search time it does one job: <strong>expand your term into every form of that
          identity.</strong> Ask "books by Maimonides" and the system finds the one who's-who entry,
          collects <em>all</em> its name-forms — <bdi>maimonides, moses</bdi>,{' '}
          <bdi>משה בן מימון</bdi>, reorderings, variants — and searches for them together. That's why
          a Hebrew-printed book surfaces for an English query: not translation, just "these are all
          the same person." Presses work the same way through their list of spellings.
        </p>
        <p className="mt-3">
          <strong>How much of this is reproducible?</strong> The backbone — grouping by the
          catalog's identity numbers — comes straight from the records, so it rebuilds the same way
          every time. But the cross-script and variant spellings depend on that <em>outside</em>{' '}
          Wikidata look-up (not reproducible from the card alone), and the whole who's-who is a{' '}
          <strong>rebuilt, derived list</strong> — which means it can drift or break. Most of this
          project's recent fixes lived right here: names accidentally split on commas, one person
          split into two entries, or an over-eager guess when a name <em>isn't</em> found. That
          fragility is exactly why the system now has automatic checks guarding these lists.
        </p>
      </>
    ),
  },
  {
    id: 'glossary',
    title: 'In plain words — a mini glossary',
    body: (
      <>
        <p>
          A few words turn up across the project. Here they are in everyday language — no library
          or engineering background needed.
        </p>
        <dl className="mt-3 space-y-3">
          {GLOSSARY.map((g) => (
            <div key={g.term} className="rounded-lg bg-gray-50 p-3 ring-1 ring-gray-200">
              <dt className="text-sm font-semibold text-gray-900">{g.term}</dt>
              <dd className="mt-1 text-sm text-gray-700">{g.plain}</dd>
            </div>
          ))}
        </dl>
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
