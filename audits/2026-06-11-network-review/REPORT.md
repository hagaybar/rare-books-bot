# Network View Review — 2026-06-11

**Charter (from the user):** evaluate https://cenlib-rare-books.nurdillo.com/network as *a means to explore the collection in a new view*; find the most valuable improvements. Hands-on testing encouraged (no API costs involved).

**Method:** chair drove the live UI via Playwright against a local instance (screenshots in this directory), swept the API across all knob combinations, and probed the data layer with SQL; then a three-expert committee (network-viz/digital-humanities, rare-books librarianship, frontend engineering) verified and extended the findings — every claim below is backed by a live API call, SQL result, or file:line.

---

## The verdict in one paragraph

Today the Network view is a **Wikipedia constellation floating over a map of Europe** — pretty, but disconnected from the collection it exists to explore. 76% of its edges are Wikipedia-category trivia ("Shared category: 1725 deaths"); its search has **never worked in any deployed environment**; clicking Spinoza shows his Wikipedia bio but **none of the 4 books we actually hold**; its one catalog link searches Primo for a meaningless internal integer; and the entities that define a rare-books collection — **the printing houses (Bomberg, Plantin, Soncino, Aldine) — are not nodes at all**. Meanwhile, the data to make this view extraordinary is *already in the database, unused*: 2,202 agent-pairs co-occurring on the same title pages, 3,535 author–publisher pairs, a curated publisher authority table with dates and places, and 99.5% imprint-date coverage begging for a time slider. The gap between current and potential is unusually large — and unusually cheap to close, because almost nothing requires new data.

---

## A. The shockers (all verified live)

| # | Finding | Evidence |
|---|---------|----------|
| A1 | **Search is dead-on-arrival everywhere**: `/network/search` is missing from both nginx (docker/nginx.conf:150-165) and the Vite proxy — the SPA fallback returns index.html with HTTP 200, `res.json()` throws inside a debounced callback, and the rejection is swallowed. No query has ever returned results in dev or production. | frontend expert; verified config + code path |
| A2 | **Clicking a person shows zero of our books**: AgentDetail has no works field; Spinoza shows `record_count: 4` as a dead number while the works join (verified, sub-millisecond) sits unused. The view's "explore the collection" promise breaks at the exact moment of curiosity. | chair + librarian expert |
| A3 | **The Primo link searches for a SQLite rowid**: network.py:313-318 passes the internal integer PK (e.g. `1843`) as the catalog query, with a comment claiming it's the MMS ID (real: `990011128320204146`). It's also never rendered in the panel. Both escape hatches to the catalog are dead (the chat handoff `?q=` is also silently dropped by Chat.tsx). | all three experts |
| A4 | **Printing houses are not nodes**: Bomberg — the librarian's actual June-3rd query — returns nothing; he exists only in `imprints.publisher_norm`. 2,130 distinct publishers + 229 curated `publisher_authorities` entries (53 with location AND dates) are entirely outside the network. | chair + librarian expert |
| A5 | **76% of all edges are category noise**: 22,132 of 28,945 edges are shared-Wikipedia-category links, mostly maintenance trivia ("Year of birth uncertain": 761 pairs, "1911 Encyclopædia Britannica articles": 440). The genuinely scholarly categories (Kabbalists: 629, Christian Hebraists: 528) drown undifferentiated among them. | chair + librarian expert |
| A6 | **No edge can explain itself**: `network_edges.evidence` is populated for 28.8k rows but never SELECTed by the API; `relationship` is NULL for 98% of edges; arcs are `pickable: false`. A scholar can never ask "why are these two connected?" — a violation of the project's own Answer Contract. | all three experts |
| A7 | **Display names corrupted to book titles**: Joseph Karo — one of the best-connected Hebrew nodes (169 connections, 13 records) — is labeled **"Kessef Mishneh"**, his book. Cause: the display-name fallback takes `authority_enrichment.label` unvalidated; ~39 names match catalog title strings. | chair + librarian expert |
| A8 | **The shipped default shows ZERO arcs and the legend lies**: the frontend's `DEFAULT_STATE.connectionTypes = []` sends `connection_types=none` → no edges at all; the Legend renders all six edge types unconditionally regardless of what's active. First impression: 150 dots, no relationships, a legend describing things that aren't there. | frontend expert |
| A9 | **53% of agents are total isolates**; collection-derived edges = 96 of 28,945 (0.3%); and the only collection edge type (co_publication) ships 73 of its 96 edges *below* the API's default confidence cutoff — selecting that layer can never show more than 23 arcs. | network-DH expert |
| A10 | **Stacked-node roulette**: 150 default nodes share 38 coordinates (Paris 20, Venice 18, Amsterdam 16); the jitter ring spans 1–2 px at default zoom while nodes are 8–14 px — clicking "Paris" selects an arbitrary agent with no hint that 19 others are underneath. | chair + frontend expert |
| A11 | **Anachronistic edges**: same_place_period uses record imprint dates as person-activity dates — Gravelot (d. 1773) is "active in London 1896–1906" via a posthumous reprint. | network-DH expert |
| A12 | Smaller: TextLayer lacks `characterSet` (529 non-ASCII names → missing glyphs incl. Hebrew); `min_confidence` is dead store state with no UI control; no URL state (views unshareable); zero a11y on controls; node size ignores the active filter (computed `filtered_count` is discarded). | frontend expert |

**One chair claim corrected by the committee** (adversarial review working as intended): agent-detail connection *types* are not null — the `relationship` field is, for 98% of edges; my earlier jq read the wrong key.

---

## B. What this view should be — the target

> **The print-culture network of THIS collection**: presses as hubs, books as evidence, people connected because they appear on the same title pages — with Wikipedia as garnish, not the main course.

The committee's converged architecture (full text in the network-DH expert's `view_architecture`):

1. **Three coordinated views over one shared filter state**: the geographic map (reframed as "print geography" whose hero feature is a time slider over imprint dates — 99.5% coverage — showing printing migrate Venice→Basel→Amsterdam), a **force-directed ego view** as the default click-interaction (a person/press and their 1–2-hop world, escaping the coordinate-stacking problem entirely), and the **agent/publisher panel** showing *our books first*, Wikipedia second.
2. **Collection-first edge taxonomy**: new `same_record` edges (2,202 pairs ready in SQL, role-typed: "translated by", "praeses–respondent") and `printed_by` edges (3,535 pairs) as the *default* layers — every one born with MARC evidence (an MMS ID, a title) — with teacher_student/llm_extraction as a "documented relationships" layer, wikilink opt-in, and **category retired from arcs into a community-coloring facet** (curated allow-list: Kabbalists yes, "1725 deaths" no).
3. **Publishers as first-class nodes**, seeded from `publisher_authorities` — Bomberg, Bragadin, Aldine, Elzevir, Plantin become the hubs that organically cluster authors by print circle.
4. **Pathfinding** ("how are Karo and Spinoza connected?") — verified feasible today: the non-category graph has a giant component of 1,058 nodes; BFS is sub-millisecond. Dramatically better once paths run through actual books ("connected via the Bragadin press, Venice") rather than Wikipedia links.

## C. Ranked roadmap

### Tier 1 — "The honesty week" (each item ≤1 day; transforms trust)
1. **Route `/network/search`** in nginx + Vite proxy (2 config lines; consider moving the API under `/api/` to end the SPA-route collision class). Then harden the combobox (empty/error states, keyboard, abort).
2. **Works list in the agent panel** — our books first, with dates/places/Primo links (join verified).
3. **Fix the Primo URL** (mms_id, not rowid) and render it; make Chat.tsx consume `?q=` so the panel's chat handoff works (compose from agent_norm, not the possibly-corrupt display name).
4. **Ship edge `evidence` + `relationship` end-to-end**; arcs pickable with a "why connected" tooltip.
5. **Fix the default view**: curated edge types ON (teacher_student + co_publication + same_place_period ≈ hundreds of meaningful arcs); legend reflects active toggles; fix co_publication's below-threshold confidence.
6. **Display-name guardrail**: reject authority labels that match a work title; prefer agent_authorities canonical names; rebuild.
7. Stack popover: click a multi-agent dot → list of co-located agents ("Paris — 20 agents"); `characterSet: 'auto'`; URL state sync.

### Tier 2 — "Become the collection's network" (~1–2 weeks)
8. **`same_record` + `printed_by` edge builders** (deterministic, MARC-evidenced; connects hundreds of the 1,430 isolates).
9. **Publisher/printing-house nodes** with distinct glyphs, from publisher_authorities + top publisher_norms.
10. **Category curation**: allow-list scholarly categories as a coloring facet; drop maintenance noise; fix same_place_period date intersection (A11).
11. Place-click → "books printed here" (verified: Venice 16th c. = 74 records, 44 Hebrew — the exact lesson-curation scenario).
12. Cross-script search through agent_aliases (bomberg/בומבירגי both resolve); bilingual name display with bdi.

### Tier 3 — "Exploration modes" (~2 weeks, the wow tier)
13. **Ego-network mode** (force-directed click-through with breadcrumbs) — the committee's pick for stickiest scholar interaction.
14. **Time slider on imprint dates** with animation — geography's unique payoff.
15. **Pathfinding** with evidence-labeled paths.
16. **Chat↔network loop**: CandidateSet → "show on map" (plot imprint places); network selection → "ask in chat".
17. Lift the 150-node cap (verified: 500 nodes + 5.6k edges = 0.96 MB / 0.22 s; the full graph is small for deck.gl), with zoom-aware label/edge culling.

### Explicitly deferred / flagged
- **Censorship networks** (a real user interest): NOT promisable today — exactly 1 censorship mention exists in the whole DB. This is a MARC-export question (copy-specific 590s, expurgation notes, censor signatures) to raise with cataloging before any UI work.

---

## Artifacts
- `network-default.png` — the shipped first impression (near-empty arcs)
- `network-wikilink.png` — the "Mentioned Together" hairball over Europe
- Expert payloads embedded in session; all SQL/API probes reproducible against the local instance.
