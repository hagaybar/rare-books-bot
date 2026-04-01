/**
 * @process health002-model-cleanup
 * @description HEALTH-002: Organize Pydantic models — add index, consolidate shared types, document boundaries
 * @inputs { projectRoot: string }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 */

import pkg from '@a5c-ai/babysitter-sdk';
const { defineTask } = pkg;

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
  } = inputs;

  // ============================================================================
  // STEP 1: Create shared_models.py with truly shared types
  // ============================================================================

  ctx.log('info', 'Step 1: Create shared_models.py');

  const sharedModels = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Create scripts/shared_models.py with cross-module types',
    description: `Create a shared_models.py file for types used across multiple modules.

After analysis, the real cross-module types are:

1. GroundingLink (plan_models.py) — used by executor, narrator, and API
2. ExternalIdentifier (enrichment/models.py) — conceptually similar to GroundingLink

These two represent external authority links but with different structures. Unify them:

Create scripts/shared_models.py:
\`\`\`python
"""Shared Pydantic models used across multiple modules.

Model Index:
- ExternalLink: Unified external reference (replaces GroundingLink + ExternalIdentifier overlap)

Module-specific models remain in their respective files:
- scripts/chat/models.py: Chat session, messages, conversation state
- scripts/chat/plan_models.py: Execution plan, steps, grounding data, narrator I/O
- scripts/schemas/query_plan.py: Query filters and plans (M4 layer)
- scripts/enrichment/models.py: Enrichment pipeline I/O
- scripts/marc/models.py: MARC XML canonical records (M1)
- scripts/marc/m2_models.py: Normalization layer (M2)
- scripts/query/models.py: Query execution results
- app/api/models.py: API request/response wrappers
- app/api/auth_models.py: Authentication models
- app/api/metadata_models.py: Metadata quality UI models
"""
from pydantic import BaseModel


class ExternalLink(BaseModel):
    """Unified external reference link used across grounding and enrichment.

    Replaces the conceptual overlap between GroundingLink and ExternalIdentifier.
    """
    source: str  # "primo", "wikipedia", "wikidata", "viaf", "nli", "loc", "isni"
    label: str  # Human-readable display label
    url: str  # The actual URL
    entity_type: str | None = None  # "record" or "agent" (grounding context)
    entity_id: str | None = None  # mms_id or agent name (grounding context)
    identifier: str | None = None  # Raw identifier value (enrichment context)
\`\`\`

DO NOT change any existing imports yet — just create the file.

Verification: source ${projectRoot}/.venv/bin/activate && python3 -c "from scripts.shared_models import ExternalLink; print('OK')"`,
    testCommand: `source ${projectRoot}/.venv/bin/activate && python3 -c "from scripts.shared_models import ExternalLink; print('OK')"`,
  });
  ctx.log('info', `Shared models: ${JSON.stringify(sharedModels)}`);

  // ============================================================================
  // STEP 2: Add model index documentation
  // ============================================================================

  ctx.log('info', 'Step 2: Add model index');

  const modelIndex = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Create docs/model_index.md documenting all Pydantic models',
    description: `Create docs/model_index.md — a comprehensive index of all 109 Pydantic models.

Organize by domain. For each model: name, file, one-line purpose.

Structure:
# Pydantic Model Index

## Chat Domain (scripts/chat/)
### Session & Messages (models.py)
- ConversationPhase — Enum: conversation state machine
- Message — Single chat message with optional query/result attachments
- ChatSession — Conversation session with history
- ChatResponse — Chatbot response with results and metadata
... etc

### Execution Pipeline (plan_models.py)
- InterpretationPlan — LLM interpreter output (intents + steps + directives)
- ExecutionStep — Single step in execution plan
- RecordSummary — Bibliographic record for narrator consumption
- GroundingData — Evidence records + agents + aggregations + links
- ExecutionResult — Complete executor output
- ScholarResponse — Final narrator output
... etc

## Query Layer (scripts/schemas/, scripts/query/)
### Query Plans (query_plan.py)
- Filter — Single query filter condition
- QueryPlan — Structured query with filters
... etc

## MARC Pipeline (scripts/marc/)
### Canonical Records — M1 (models.py)
- CanonicalRecord — Raw bibliographic record from MARC XML
... etc

### Normalization — M2 (m2_models.py)
- DateNormalization, PlaceNormalization, etc.

## Enrichment (scripts/enrichment/)
- EnrichmentRequest, EnrichmentResult, PersonInfo, etc.

## API Layer (app/api/)
### Request/Response (models.py, auth_models.py, metadata_models.py)
- ChatRequest, UserInfo, CorrectionRequest, etc.

## Cross-Module (scripts/shared_models.py)
- ExternalLink — Unified external reference

Read all 10 model files to build the complete index. Be thorough.`,
    testCommand: `ls ${projectRoot}/docs/model_index.md`,
  });
  ctx.log('info', `Model index: ${JSON.stringify(modelIndex)}`);

  // ============================================================================
  // STEP 3: Build verification
  // ============================================================================

  const buildCheck = await ctx.task(shellTask, {
    projectRoot,
    phase: 'build verification',
    command: `cd ${projectRoot}/frontend && npx tsc --noEmit && cd ${projectRoot} && source .venv/bin/activate && python3 -c "from app.api.main import app; print('Backend OK')"`,
    timeout: 120000,
  });
  ctx.log('info', `Build: ${JSON.stringify(buildCheck)}`);

  // ============================================================================
  // STEP 4: Deploy
  // ============================================================================

  const deployApproval = await ctx.task(breakpointTask, {
    question: 'HEALTH-002 addressed. Deploy?',
    options: ['Approve', 'Reject'],
  });

  if (!deployApproval?.approved) {
    return { success: true, deployed: false };
  }

  const deploy = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Commit HEALTH-002 fix and deploy',
    description: `Commit and deploy:

1. Stage: scripts/shared_models.py, docs/model_index.md, audits/2026-04-01-full-stack/FIX_REPORT.md
2. Commit:
   docs: HEALTH-002 — add shared_models.py and model index documentation

   Created scripts/shared_models.py with ExternalLink (unified external reference).
   Created docs/model_index.md documenting all 109 Pydantic models across 10 files.

   Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

3. Push to origin main
4. Run ./deploy.sh`,
    testCommand: `cd ${projectRoot} && git log --oneline -1`,
  });
  ctx.log('info', `Deploy: ${JSON.stringify(deploy)}`);

  return { success: true, deployed: true };
}

const agentTask = defineTask('agent-impl', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Python architect documenting and organizing Pydantic models',
      task: args.taskName,
      context: { projectRoot: args.projectRoot },
      instructions: [
        `Working directory: ${args.projectRoot}`,
        args.description,
        'Read relevant files before making changes.',
        `Verification: ${args.testCommand}`,
        'Return JSON: { taskName, status, filesChanged, details }',
      ],
      outputFormat: 'JSON',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const shellTask = defineTask('shell-cmd', (args, taskCtx) => ({
  kind: 'shell',
  title: args.phase,
  shell: { command: args.command, cwd: args.projectRoot, timeout: args.timeout || 60000 },
  io: { outputJsonPath: `tasks/${taskCtx.effectId}/output.json` },
}));

const breakpointTask = defineTask('breakpoint-gate', (args, taskCtx) => ({
  kind: 'breakpoint',
  title: args.question,
  breakpoint: { question: args.question, options: args.options },
}));
