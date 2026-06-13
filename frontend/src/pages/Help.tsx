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
    id: 'question',
    title: '9. What happens when you ask a question',
    body: (
      <>
        <p>
          Everything so far was about <em>preparing</em> the data. Now the other half: turning your
          question into an answer. It runs through <strong>three stages</strong> — and the key shape
          is that <strong>the AI only touches the two ends; the actual searching in the middle has
          no AI at all.</strong>
        </p>
        <ol className="mt-3 list-decimal space-y-2 pl-5">
          <li>
            <strong>Understand it</strong>{' '}
            <span className="text-gray-400">(this is where the AI reads your question)</span> — the
            AI's only job here is to turn your plain-English question into a precise{' '}
            <strong>search recipe</strong>: a short list of steps for the engine to run. It doesn't
            search and it doesn't write the answer. If the question is too vague to search ("show me
            old books"), it stops and <strong>asks you to clarify</strong> rather than guess.
          </li>
          <li>
            <strong>Do the search</strong> <span className="text-gray-400">(no AI — a fixed
            engine)</span> — a step-by-step engine follows the recipe against the database lists and
            produces the <strong>matching books plus the evidence</strong>: which field, in which
            record, caused each match. Nothing is invented here; it's plain, repeatable work.
          </li>
          <li>
            <strong>Write the answer</strong> <span className="text-gray-400">(AI again)</span> — the
            AI takes what the engine actually found and writes it up in readable, cited prose. It's{' '}
            <strong>fenced in</strong>: it can only talk about books the engine returned. No results,
            no claims.
          </li>
        </ol>
        <p className="mt-4 font-semibold text-gray-900">The moves the engine can make</p>
        <p className="mt-1">The recipe is built from a small, fixed set of moves:</p>
        <div className="mt-2 overflow-hidden rounded-lg ring-1 ring-gray-200">
          <table className="w-full text-sm">
            <tbody className="divide-y divide-gray-200">
              {[
                ['Look up a person / a press', 'take a name and expand it to all its forms via the who’s-who'],
                ['Search with filters', 'the core find — apply conditions (place, year, language…) and return matching books + evidence'],
                ['Count & group', 'tallies and facets — "how many per century", "top places"'],
                ['Pick a sample', 'a representative handful, for "show me some notable items"'],
                ['Find connections', 'who worked with whom across books'],
                ['Fetch extra detail', 'pull in outside info (Wikidata / Wikipedia) for display'],
              ].map(([op, meaning]) => (
                <tr key={op}>
                  <td className="w-1/3 bg-gray-50 px-3 py-2 align-top font-medium text-gray-800">
                    {op}
                  </td>
                  <td className="px-3 py-2 align-top text-gray-700">{meaning}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3">
          A simple question uses one move ("books printed in Venice" → one <em>Search with
          filters</em>). A richer one chains several ("What did the Bragadin press print?" →{' '}
          <em>Look up a press</em>, then <em>Search with filters</em>).
        </p>
        <p className="mt-3">
          <strong>Why this shape matters.</strong> The AI is a <em>translator</em> (your words →
          a recipe) and a <em>writer</em> (results → prose) — never the authority on what's actually
          in the collection. The finding, and the evidence trail back to the catalog record, happen
          in the AI-free middle. That's the project's core promise made structural:{' '}
          <strong>no answer exists before the evidence does.</strong>
        </p>
      </>
    ),
  },
  {
    id: 'recipe',
    title: '10. Stage 1, up close: turning your sentence into a recipe',
    body: (
      <>
        <p>
          This is the one stage where the AI exercises real judgment — so it's worth a close look.
          It receives <strong>your question</strong> (plus a little recent-conversation context, so
          follow-ups like "and only the Hebrew ones" make sense) and must produce a{' '}
          <strong>structured recipe</strong> — not prose, not a search. The recipe has a few parts:
          the <strong>steps</strong> to run, a short note of the <strong>intent</strong> it read
          from your words, a <strong>confidence</strong> score, a <strong>clarification</strong> slot
          (filled <em>instead</em> of steps when it needs to ask you back), and a{' '}
          <strong>"dropped" log</strong> of anything it tried that had to be thrown out.
        </p>
        <p className="mt-2">
          The key constraint: the AI can only build the recipe from a <strong>fixed menu</strong> —
          the seven moves, a fixed list of fields (place, year, language, subject, title, publisher,
          person, role) and four operators (equals, contains, range, is-one-of). It cannot invent a
          new kind of search; it can only assemble one from known pieces.
        </p>
        <p className="mt-4 font-semibold text-gray-900">The rules it must follow</p>
        <ul className="mt-1 list-disc space-y-2 pl-5">
          <li>
            <strong>Never invent constraints.</strong> The recipe must come only from what's in your
            words. "Show me the interesting books" must <em>not</em> become a search for some subject
            the AI made up — that fabrication is explicitly forbidden.
          </li>
          <li>
            <strong>If a term looks garbled, ask — don't guess.</strong> A likely typo triggers a
            clarification, never a silent swap for what the AI assumes you meant.
          </li>
          <li>
            <strong>If the question is too vague, clarify.</strong> Filling the clarification slot{' '}
            <strong>stops the whole process</strong> — you get a question back, not a guessed answer.
          </li>
          <li>
            <strong>Route words to the right field.</strong> A descriptive word should become a{' '}
            <em>subject</em> search, not be mistaken for an author's name.
          </li>
        </ul>
        <p className="mt-4 font-semibold text-gray-900">The safety net behind it</p>
        <p className="mt-1">
          The recipe is <strong>not trusted blindly</strong> — it's checked against the fixed
          rulebook before anything runs. A fixable slip is <strong>repaired</strong> (a single year
          written as "equals 1805" becomes the range the engine supports); an unfixable one is{' '}
          <strong>dropped and logged</strong>, so a half-understood question never pretends to be
          fully understood. In one line: <strong>the AI is a planner whose plan must pass
          validation; if it can't, the system fails safely rather than running a broken search.</strong>
        </p>
        <p className="mt-3">
          <strong>Why this stage is the fragile one.</strong> Because it's the only place the AI
          truly judges, it's where the recognizable mistakes are born: a filter silently{' '}
          <em>dropped</em> (you asked for Venice <em>and</em> the 16th century; it kept only Venice),
          a filter <em>invented</em>, or a word sent to the <em>wrong field</em>. Catching exactly
          these was the point of the project's recent testing push.
        </p>
      </>
    ),
  },
  {
    id: 'engine',
    title: '11. Stage 2, up close: the engine runs the recipe',
    body: (
      <>
        <p>
          This is the deterministic heart — <strong>no AI, fully repeatable</strong>, and the stage
          that actually produces the evidence trail. The engine works through the recipe's steps{' '}
          <strong>in order</strong>, because they can depend on each other: a "look up the Bragadin
          press" step must finish before the "search with filters" step that uses its result.
        </p>
        <p className="mt-3">
          The core move turns each condition in your question into a filter and{' '}
          <strong>combines them with AND — all must hold at once.</strong> "Books printed in Venice
          in the 16th century" becomes <em>place = venice</em> <strong>and</strong>{' '}
          <em>year in 1500–1599</em>, run against the lists, returning the matching books.
        </p>
        <p className="mt-4 font-semibold text-gray-900">The evidence trail — the promise made real</p>
        <p className="mt-1">
          For every book it returns, the engine records <strong>why it matched</strong> — which
          field, holding which value, in which record. That's the trail back to the catalog card:
          not "trust me," but "this book is here <em>because</em> its place field says venice and its
          date field says 1553." The written answer later cites this. (The bug where a match lost its
          trail and just said "source: unknown" was a flaw right here.)
        </p>
        <p className="mt-4 font-semibold text-gray-900">When nothing matches: broadening, openly</p>
        <p className="mt-1">
          If the strict "all conditions at once" search returns <strong>zero</strong> books, the
          engine broadens — gently, under two firm rules:
        </p>
        <ol className="mt-2 list-decimal space-y-2 pl-5">
          <li>
            <strong>Hard limits are never loosened.</strong> Place, year, language, a named person,
            and any "not-this" exclusion stay firm; only <strong>descriptive/topic words</strong> are
            allowed to widen. "Hebrew grammar books in Amsterdam in the 1600s" might broaden the
            topic "grammar" — but it will <em>never</em> quietly drop Amsterdam or the 1600s and hand
            you Frankfurt books from 1750.
          </li>
          <li>
            <strong>Every widening is written down and shown to you</strong> — "no exact subject
            'cartography'; broadened to 'geography' and 'maps' (18 books)." If even the broadened
            search finds nothing, you get an <strong>honest empty result</strong>, never a guess.
          </li>
        </ol>
        <p className="mt-3">
          Two recent refinements live here: trying the <strong>plural/singular</strong> of a topic
          word before giving up (so "limited edition" still finds "limited editions"), and a{' '}
          <strong>selectivity cap</strong> so that when a name can't be resolved, a common word like
          "Jacob" can't flood the results with unrelated books.
        </p>
        <p className="mt-3">
          <strong>What it hands off:</strong> the matching books, the total count, the exact search
          that ran, the evidence for each match, and a record of any broadening. The writer in
          Stage 3 can only speak about what's in this package.
        </p>
      </>
    ),
  },
  {
    id: 'widening',
    title: '12. When a search finds nothing: the widening ladder, step by step',
    body: (
      <>
        <p>
          When a strict search returns nothing, the engine climbs a <strong>ladder of gentle
          widenings, in a fixed order</strong>. Two principles hold at <em>every</em> rung:{' '}
          <strong>hard limits never loosen, and every widening is recorded and shown to you.</strong>
        </p>
        <ol className="mt-3 list-decimal space-y-3 pl-5">
          <li>
            <strong>Soften an exact name to a partial match.</strong> If you pinned a publisher by
            exact name and found nothing, exact-match was probably too strict — a printer's name as
            written on a book is freeform text, not a fixed vocabulary. So a search for "Soncino"
            then also finds the stored form "H. de Soncino". (Only for name-shaped fields — it would
            never do this to a place or a year.)
          </li>
          <li>
            <strong>Split AND'd topics into an OR.</strong> If you asked for several topic words at
            once ("liturgy and poetry") and the combination is empty, maybe each works alone. The
            engine runs each topic separately — still carrying all your hard limits — and{' '}
            <strong>unions</strong> the results, noting which topic brought back which books.
          </li>
          <li>
            <strong>Expand a topic to related ideas.</strong> Each topic word is looked up in a{' '}
            <strong>small, hand-built map of related terms</strong> — "cartography" → "geography",
            "maps" — and the engine searches those instead, recording the swap. (That map is curated
            and fixed, not the AI improvising.)
          </li>
          <li>
            <strong>Try the plural/singular.</strong> If a topic still found nothing, it toggles a
            trailing "-s": "limited edition" → "limited editions". Small, but it closes a real gap
            between how the catalog stores a term and how you might type it.
          </li>
          <li>
            <strong>Honest empty.</strong> If none of that recovers anything, you get a truthful
            "no matches" — never a fabricated or padded result.
          </li>
        </ol>
        <p className="mt-4 font-semibold text-gray-900">The rule that governs all of it</p>
        <p className="mt-1">
          At every rung, your <strong>hard limits ride unchanged into every probe</strong>: place,
          year, language, a named person, and any "not-this" exclusion. Only the{' '}
          <strong>descriptive/topic words</strong> are ever widened. That's why "Hebrew grammar,
          Amsterdam, 1600s" can broaden "grammar" but can <em>never</em> hand you a Frankfurt book
          from 1750 — the widening makes the <em>topic</em> more generous; it never quietly relaxes{' '}
          where, when, what language, or by whom.
        </p>
        <p className="mt-4 font-semibold text-gray-900">A separate path: rescuing an unrecognized name</p>
        <p className="mt-1">
          A second kind of widening fires when a <strong>person or press name couldn't be matched to
          the who's-who at all</strong>. The engine then probes the name's distinctive words one by
          one — but <strong>rejects any word too common to be meaningful</strong>. So an
          unrecognized "Jacob ibn Habib" probes the rare part ("Habib") and refuses the flooding
          part ("Jacob"), instead of returning every Jacob in the collection. (Without this cap, that
          one query used to return 119 wrong books.)
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
