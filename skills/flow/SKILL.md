---
name: flow
description: Orchestrate multi-agent pipelines with claude/codex CLI backends running in tmux. Use when the user asks to build, run, or adjust an agent pipeline ("编排流水线", "搭一个多agent系统", "multi-agent pipeline", run agents in parallel with dependencies), create or edit agent definitions for a pipeline, or intervene in a running flow run (approve/retry/inject/status/attach). Covers project scaffolding, flow.yaml DAG authoring, validation, and the sub-pipeline fan-out pattern.
---

# flow — Multi-Agent Pipeline Orchestrator

flow runs multi-agent pipelines where each agent is a native `claude` or `codex` CLI subprocess living in its own tmux window. You (the reading agent) can author projects, launch runs, and intervene mid-run — all through the `flow` CLI and plain markdown files.

**Announce at start:** "Using flow skill — <what you're doing>."

## 1. Concept model

```
<project>/                    any directory containing flow.yaml
├── flow.yaml                 the DAG (nodes reference agents/, needs = dependencies)
├── agents/<name>/agent.md    agent definitions (role / workflow / memory rules / constraints)
├── workdir/                  shared working area (persistent across runs)
└── runs/<run-id>/
    ├── memory/               context.md (read-only) · findings.md (append-only) · decisions.md
    ├── agents/<node>/        agent.md snapshot, task.md, summary.md, tty.log, done.flag
    ├── artifacts/            final outputs
    ├── state.json            node status machine
    └── pipeline.yaml         snapshot of the yaml this run actually used
```

- Each node = one tmux window in session `flow-<run-id>` (plus a `control` window if `control: true`).
- Node status: `pending → running → (waiting-human | failed) → done`. Failure pauses the whole run for a human.
- Completion detection is hook-based (claude Stop hook / codex notify → done.flag); the orchestrator never scrapes terminal output.
- Memory injection is **path-reference** (pull model): prompts tell agents to Read file paths, never inline content.
- `summary.md` per node is the narrow interface injected into downstream nodes.

## 2. Creating a project (standard sequence)

```bash
flow init <dir>               # scaffold: flow.yaml template + agents/ (incl. control) + workdir/ + .gitignore
flow agent new <name> -p <dir>   # four-section agent.md template (role/workflow/memory/constraints)
# ... edit agent.md content and flow.yaml ...
flow validate [-p <dir>]      # MUST pass before running
flow run [-p <dir>]           # starts tmux session flow-<run-id>, blocks until done/paused
```

`flow init` pre-creates `agents/control/agent.md` (the persistent control window's definition, required by `control: true`). Customizing it is optional.

**Always `flow validate` after editing any yaml.** Validation errors name the exact node and field.

### Writing good agent.md (four sections, all required)

1. **角色** — specific role, what this agent owns in the pipeline
2. **工作方式** — numbered steps: read what (with paths), process how, write outputs **where (absolute paths)**
3. **共享记忆约定** — how it appends to `runs/<run-id>/memory/findings.md` (append-only, signed with node name, never edit others' entries). Common tag convention: `[major]` confirmed / `[minor]` suspicious / `[chain]` chain-clue (入口可控性 → 数据流 → sink → 前置条件)
4. **约束** — boundaries and evidence standards (e.g. "claims must cite function name/offset"), always absolute paths for outputs

Pitfall learned in production: if a task says "produce artifacts/report.md" without anchoring, the agent may write it under workdir/. Specify the full run-relative or absolute path in agent.md.

## 3. flow.yaml schema

```yaml
name: my-pipeline
control: true                # persistent control agent window (recommended)
nodes:
  reader:
    agent: reader            # must exist as agents/reader/agent.md
    backend: claude          # claude | codex
    task: one-line task      # short; details go in agent.md, not here
    needs: []                # node names that must be done first
    gate: false              # true = human approval before downstream starts
    timeout: null            # seconds; null = no timeout (default)
    retry: 0                 # default 0; failure pauses the run
    inject: [memory/context.md]   # paths (run-relative or absolute) the agent must read first
    env: {}                  # extra env vars for this node (e.g. ANTHROPIC_MODEL)
```

Validation rules (all reported with node+field): agent must exist; backend in {claude, codex}; needs must reference known nodes; no cycles (Kahn's); node name `control` reserved; env values must be strings.

## 4. Running & intervening

| Command | Use |
|---|---|
| `flow run [-f FILE] [-p DIR]` | start run (`-f` for sub-pipeline yaml); blocks until done/paused |
| `flow status [run_id] [-p DIR]` | node status table (run_id defaults to latest) |
| `flow attach [node] [run_id]` | attach to tmux session; with node name, holds that node's attach lock (orchestrator defers prompt delivery while locked) |
| `flow log <node> [run_id]` | open the node's tty.log in less |
| `flow approve <node>` | release a waiting-human gate |
| `flow retry <node>` | reset node to pending (destroys its window → fresh session); then `flow resume` |
| `flow inject <node> <message>` | queue a message delivered to a running node |
| `flow resume` / `flow stop` | continue a paused run / kill session + pause |
| `flow validate [file]` | validate yaml |
| `flow agent list/show/new` | manage agent definitions |
| `flow clean [-p DIR] [--runs N]` | kill tmux sessions of finished runs; `--runs N` interactively delete old run dirs |

**Intervention decision guide:**
- Node produced wrong/partial work but is still running → `flow inject` with corrective instructions
- Node finished wrong / context polluted (e.g. bad input poisoned the conversation) → `flow retry` (fresh session, not inject)
- Human sign-off needed on quality → design the node with `gate: true` from the start
- Interactive debugging → `flow attach <node>` (you talk to that CLI directly; orchestrator pauses deliveries to it)

## 5. Orchestration patterns

**Serial chain** — `b.needs: [a]`; b's inject should include `agents/a/summary.md`.

**Parallel fan-out** — multiple nodes with empty `needs` (or same needs); they share workdir, so make them write disjoint paths (each writes its own output file; reads of upstream are safe).

**Quality gate** — `gate: true` on a node whose output decides everything downstream; run pauses at waiting-human until `flow approve`.

**Sub-pipeline fan-out (dynamic node count)** — when the set of worker nodes is only known at runtime (e.g. per-target audit jobs):
1. An upstream agent writes per-job skill files (a work order: goal / entry points / hypotheses / checklist / tool commands) into `runs/<parent-run>/plan/skills/<job>/skill.md`
2. Same agent writes a **sub flow.yaml** into `runs/<parent-run>/plan/flow.yaml`: worker nodes with `needs: []`, `inject` listing the job's skill.md + parent run memory files via **absolute paths**
3. Runs it synchronously: `flow run -p <project> -f runs/<parent>/plan/flow.yaml` (blocks; the parent node's done.flag fires only after)
4. Workers append findings to the **parent run's** findings.md (absolute path in inject)
5. Cap sub-pipeline nodes (~4); prioritize and record cuts in decisions.md
The sub run gets its own tmux session and its own run dir; `flow status/approve/retry` on it resolve from its own pipeline snapshot. Clean up its session afterwards with `flow clean`.

## 6. Operating rules

- After **any** yaml edit: `flow validate` before `flow run`/`resume`.
- Inject paths are resolved run-relative when not absolute — prefer absolute paths in generated sub-pipelines.
- Outputs: anchor every produced file to an explicit absolute path in agent.md.
- Don't send text into other agents' TUIs via tmux yourself — go through `flow inject`/`approve`/`retry` (auditable, conflict-free).
- Long tasks may legitimately take many minutes; check `flow status` and tail tty.log before assuming a hang. Nodes show `running` until their CLI fires the done hook.
- When a run finishes, offer `flow clean` to reap finished-run sessions.
