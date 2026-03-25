# Definitive Implementation Plan — Process Description

## Purpose

Synthesize 13 fragmented UI evaluation reports into a single definitive implementation plan (`IMPLEMENTATION_PLAN.md`) that serves as the sole source of truth for building the unified Rare Books Bot UI.

## Problem Being Solved

Two orchestrated runs produced 13 reports (310K total) covering UI inventory, deep analysis, project goal inference, alignment assessment, redundancy analysis, new UI definition, migration planning, and empirical verification (database probe, pipeline test, API verification, cross-reference, refinements). The information is complete but fragmented — with contradictions between original analysis and empirical corrections patched as addenda rather than integrated. No single document exists that a developer can use to build the UI.

## Approach

### Phase 1: Extract & Reconcile
- Read all 13 reports and extract key facts into a structured JSON fact base
- For every contradiction between original (01-07) and empirical (08-12): empirical wins
- Categories: architecture, screen specs, data reality, API reality, pipeline reality, backend work, timeline, features, risks
- Output: reconciled facts with contradiction log

### Phase 2: Write the Definitive Plan
- Using the reconciled fact base, write `IMPLEMENTATION_PLAN.md`
- 8 sections covering vision, screen specs, backend inventory, timeline, features, risks
- Every claim grounded in empirical evidence
- Self-contained: a developer can build from this document alone

### Phase 3: Verify Internal Consistency
- QA auditor cross-checks every screen spec against empirical API shapes
- Verifies backend inventory covers all identified gaps
- Checks timeline dependencies and exit criteria
- Flags any remaining contradictions or unsupported assumptions

### Phase 4: Finalize
- Apply verification fixes
- Add verification stamp with pass/fail results
- Declare the document as the sole source of truth

## Key Constraints

- Empirical data ALWAYS overrides theoretical analysis
- No feature may appear in a screen spec unless its API endpoint exists or is in the backend work inventory
- The document must be self-contained — no cross-references to the 13 reports needed
- Every number must trace to actual SQL queries or API response tracing

## Output

`IMPLEMENTATION_PLAN.md` at project root — verified, self-consistent, empirically grounded.

## Mode

Interactive — user approves before run creation.
