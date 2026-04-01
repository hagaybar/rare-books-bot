# Project Audits

This directory contains all project audit reports organized by date and focus.

## Folder Structure

```
audits/
├── YYYY-MM-DD-audit-name/
│   ├── AUDIT_REPORT.md           # Comprehensive findings and analysis
│   ├── FINDINGS.yaml              # Machine-readable structured findings
│   ├── ACTION_PLAN.md             # Prioritized remediation plan
│   └── NEXT_AUDIT_CHECKLIST.md   # Reusable playbook for next audit
└── README.md (this file)
```

## Naming Convention

- **Date format:** `YYYY-MM-DD` (ISO 8601)
- **Suffix:** Descriptive focus area
  - `-general` - Comprehensive codebase audit
  - `-chatbot-readiness` - Chatbot UI integration assessment
  - `-security` - Security-focused audit
  - `-performance` - Performance and scalability audit
  - etc.

## Existing Audits

### 2026-01-12: General Project Audit
**Focus:** Overall codebase health, architecture alignment, and M4 query pipeline maturity

**Key Findings:**
- M4 query pipeline mature and production-ready
- Strong evidence extraction with confidence scores
- Good test coverage for core components
- Normalization pipeline well-documented

**Status:** Completed - M4 stable, ready for next phase (M5/M6)

---

### 2026-01-13: Chatbot UI Readiness Audit
**Focus:** Assessment of codebase readiness for incorporating conversational chatbot interface

**Key Findings:**
- 60% ready - solid foundation, missing conversation layer
- Query pipeline (M4) excellent - no changes needed
- Evidence extraction perfect for chat needs
- Missing: session management, API layer, response formatting
- 3 P0 blockers, 3 P1 critical gaps identified

**Status:** Action plan defined - 3-4 weeks to chatbot MVP

**Recommendation:** Build M6 (conversational layer) on top of M4 without modifying M4

---

## How to Run an Audit

Using the `project-audit` skill:

```bash
# Via Claude Code
/project-audit --focus "Description of audit focus area"

# Example
/project-audit --focus "Evaluate readiness for production deployment"
```

The skill will automatically:
1. Analyze git commit history for context
2. Infer project intent from code and docs
3. Map architecture and boundaries
4. Identify gaps and risks
5. Generate all four output files in dated folder

## Comparing Audits Over Time

```bash
# View audit timeline
ls -l audits/

# Compare findings between audits
diff audits/2026-01-12-general/FINDINGS.yaml \
     audits/2026-01-13-chatbot-readiness/FINDINGS.yaml

# Track resolution progress
grep "status: resolved" audits/*/FINDINGS.yaml
```

## Audit Frequency

**Recommended schedule:**
- **Weekly during active development** (new features, major refactors)
- **Before major milestones** (releases, deployments, onboarding)
- **After architecture changes** (new modules, deleted components)
- **On-demand** when codebase feels "off track"

## Git Integration

Each audit includes git history analysis to understand:
- Recent development activity and patterns
- Decision rationale from commit messages
- Frequently changed files (hotspots)
- Failed experiments (reverted commits)
- Contributor activity and ownership

See `.claude/skills/project-audit/SKILL.md` for full specification.
