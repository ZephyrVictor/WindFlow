"""All enums, filenames, and magic values live here. Modules must import from
this file instead of repeating literals."""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class Backend(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_HUMAN = "waiting-human"
    DONE = "done"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in (NodeStatus.DONE, NodeStatus.FAILED)


PIPELINE_FILE = "flow.yaml"
AGENTS_DIR = "agents"
WORKDIR_NAME = "workdir"
RUNS_DIR = "runs"

# run-relative names
MEMORY_DIR = "memory"
NODE_DIR = "agents"
ARTIFACTS_DIR = "artifacts"
STATE_FILE = "state.json"
TMUX_CONF = ".tmux.conf"
ATTACH_LOCK = "attach.lock"
INJECT_QUEUE_FILE = "inject-queue.json"
CONTROL_NODE = "control"

# node-relative names
AGENT_MD = "agent.md"
TASK_FILE = "task.md"
SUMMARY_FILE = "summary.md"
MEMORY_FILE = "memory.md"
TTY_LOG = "tty.log"
DONE_FLAG = "done.flag"
SESSION_ID_FILE = "session.id"
CLAUDE_SETTINGS = "claude-settings.json"
CODEX_HOME_DIR = ".codex-home"

# shared memory files (run-relative, under memory/)
MEM_CONTEXT = "context.md"
MEM_FINDINGS = "findings.md"
MEM_DECISIONS = "decisions.md"

# tmux session prefix; full name = f"{TMUX_SESSION_PREFIX}{run_id}"
TMUX_SESSION_PREFIX = "flow-"
WINDOW_INDEX_SEP = "-"
TMUX_CONF_CONTENT = "\n".join(
    [
        "set -g mouse on",
        "set -g history-limit 100000",
        "set-window-option -g mode-keys vi",
    ]
)

# orchestrator tuning
POLL_INTERVAL_SECONDS = 2.0
ATTACH_RETRY_SECONDS = 5.0

# defaults
DEFAULT_CONTROL_BACKEND = Backend.CLAUDE
