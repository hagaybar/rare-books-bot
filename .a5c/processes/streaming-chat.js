/**
 * @process streaming-chat
 * @description Streaming chat with thinking mode — 3 tasks.
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill frontend-design specializations/web-development/skills/frontend-design/SKILL.md
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const { projectRoot = '/home/hagaybar/projects/rare-books-bot' } = inputs;
  const spec = 'docs/superpowers/specs/2026-03-28-streaming-chat-design.md';

  ctx.log('info', 'Streaming chat with thinking mode (3 tasks)');

  const task1 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 1: Backend — narrator streaming + pipeline progress callbacks',
    description: `Read ${spec} completely. Implement backend streaming.

Working directory: ${projectRoot}
Branch: feature/auth-security

### 1. Narrator streaming (scripts/chat/narrator.py)

Read the existing narrator module first. Add an async streaming variant:

The narrator currently calls OpenAI and returns the full text. Add a new function (or modify existing) that:
- Accepts a chunk_callback async function
- Calls OpenAI with stream=True
- For each chunk, calls await chunk_callback(text)
- Returns the full assembled text

If the narrator uses the openai library's client.chat.completions.create(), the streaming version is:
\`\`\`python
response = client.chat.completions.create(model=..., messages=..., stream=True)
full_text = []
for chunk in response:
    if chunk.choices[0].delta.content:
        text = chunk.choices[0].delta.content
        full_text.append(text)
        if chunk_callback:
            await chunk_callback(text)
return "".join(full_text)
\`\`\`

IMPORTANT: Read how the narrator is actually structured. It may use a different pattern. Adapt accordingly.

### 2. Pipeline progress callbacks (app/api/main.py)

In the /ws/chat WebSocket handler, update the pipeline execution to send thinking messages at key points:

1. Before interpreter: send {"type": "thinking", "text": "Interpreting your query..."}
2. After query compilation: send {"type": "thinking", "text": "Searching for {description}..."}
3. After SQL execution: send {"type": "thinking", "text": "Found {N} matching records"}
4. After enrichment: send {"type": "thinking", "text": "Analyzing related scholars..."}
5. Before narrator: send {"type": "stream_start"}
6. During narrator: forward each chunk as {"type": "stream_chunk", "text": "..."}
7. After done: send {"type": "complete", "response": {...}}

The challenge: the scholar pipeline (scripts/chat/) is synchronous. You need to either:
a) Add await points by making the pipeline async with callbacks
b) Or run the pipeline in a thread and use progress markers

Read the actual pipeline code in scripts/chat/interpreter.py and how it's called in app/api/main.py to determine the best approach.

A practical approach: wrap the existing synchronous pipeline but add WebSocket sends at the key integration points in main.py (before/after each pipeline stage call).

### 3. Generate human-readable filter description

Add a helper that converts a query plan into readable text:
- "Searching for books published in Amsterdam between 1500 and 1599..."
- "Searching for books by Maimonides..."
- "Searching for Hebrew books about medicine..."

This reads the compiled query plan's filters and produces a natural sentence.

Verify: poetry run python -c "from app.api.main import app; print('OK')"
Commit: git add scripts/chat/ app/api/ && git commit -m "feat: narrator streaming + pipeline progress callbacks for thinking mode"`,
    testCommand: `cd ${projectRoot} && poetry run python -c "from app.api.main import app; print('OK')"`,
  });

  const task2 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 2: Frontend — WebSocket chat + streaming message rendering',
    description: `Read ${spec} completely. Implement frontend streaming.

Working directory: ${projectRoot}
Branch: feature/auth-security

### 1. Switch Chat.tsx to WebSocket

The chat page currently uses HTTP POST (fetch('/chat')). Switch to WebSocket for the primary flow:

In frontend/src/pages/Chat.tsx:
- On send, open WebSocket to ws://localhost:8000/ws/chat (or use existing connection)
- Send the message JSON
- Handle incoming messages by type:
  - "session_created" → store session_id
  - "thinking" → update thinking state
  - "stream_start" → switch to streaming mode
  - "stream_chunk" → append text to current message
  - "complete" → finalize message, store full response
  - "error" → show error

### 2. Create ThinkingBlock component

Create frontend/src/components/chat/ThinkingBlock.tsx:

\`\`\`tsx
interface Props {
  steps: string[];       // accumulated thinking messages
  isActive: boolean;     // still thinking?
  isCollapsed: boolean;  // user collapsed it?
  onToggle: () => void;
}
\`\`\`

When active (thinking in progress):
- Show a box with muted blue/gray background, subtle pulse animation
- Display the latest thinking text
- Small 💭 icon

When complete (collapsed):
- Show "💭 Show reasoning (N steps)" toggle
- Click expands to show all steps as a numbered list

When complete (expanded):
- Show all thinking steps as a list
- Click collapses

### 3. Update MessageBubble for streaming

In frontend/src/components/chat/MessageBubble.tsx:
- Add a streaming prop or detect streaming state
- When streaming: show text as it arrives, with blinking cursor at end
- The cursor is a CSS animation: a small vertical bar that blinks

### 4. Message state machine

Each assistant message has a state:
- THINKING: showing thinking block, collecting steps
- STREAMING: narrator text streaming in
- COMPLETE: full response rendered

Track this in the chat component state or in each message object.

### 5. WebSocket URL

Use the same host as the page, with ws:// or wss:// protocol:
\`\`\`typescript
const wsUrl = \`\${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}\${window.location.host}/ws/chat\`;
\`\`\`

Or for dev with Vite proxy, the WebSocket proxy should already be configured (check vite.config.ts for /ws).

Verify: cd frontend && npx tsc --noEmit && npm run build
Commit: git add frontend/src/ && git commit -m "feat: WebSocket streaming chat with thinking mode UI"`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -5`,
  });

  const task3 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 3: Integration test + push',
    description: `Verify the streaming chat works end-to-end.

Working directory: ${projectRoot}
Branch: feature/auth-security

1. Check TypeScript compiles: cd frontend && npx tsc --noEmit
2. Check frontend builds: cd frontend && npm run build
3. Check backend imports: poetry run python -c "from app.api.main import app; print('OK')"
4. Fix any issues found

Commit any fixes and push:
git add -A && git status
git commit -m "feat: streaming chat integration — thinking mode + progressive response" (if there are changes)
git push origin feature/auth-security

Return JSON: { taskName: "Integration", status: "completed" }`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -3`,
  });

  ctx.log('info', 'Streaming chat complete');
  return { success: true };
}

const agentTask = defineTask('stream-agent', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior full-stack developer implementing streaming chat',
      task: args.taskName,
      context: { projectRoot: args.projectRoot },
      instructions: [
        `Working directory: ${args.projectRoot}`,
        'Branch: feature/auth-security',
        args.description,
        `Verification: ${args.testCommand}`,
        'Return JSON: { taskName, status, filesChanged }',
      ],
      outputFormat: 'JSON',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));
