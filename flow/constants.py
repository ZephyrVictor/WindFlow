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
    SKIPPED = "skipped"

    @property
    def terminal(self) -> bool:
        return self in (NodeStatus.DONE, NodeStatus.FAILED, NodeStatus.SKIPPED)

    @property
    def satisfied(self) -> bool:
        """Downstream may launch: DONE normally, SKIPPED after human gave up."""
        return self in (NodeStatus.DONE, NodeStatus.SKIPPED)


PIPELINE_FILE = "flow.yaml"
AGENTS_DIR = "agents"
WORKDIR_NAME = "workdir"
RUNS_DIR = "runs"

# environment variable carrying the id of the run a process belongs to;
# sub-pipelines inherit it so children can record their parent
FLOW_RUN_ID_ENV = "FLOW_RUN_ID"

# run-relative names
MEMORY_DIR = "memory"
NODE_DIR = "agents"
ARTIFACTS_DIR = "artifacts"
STATE_FILE = "state.json"
TMUX_CONF = ".tmux.conf"
ATTACH_LOCK = "attach.lock"
INJECT_QUEUE_FILE = "inject-queue.json"
INJECT_LOG_FILE = "inject-log.jsonl"
RUN_PIPELINE_FILE = "pipeline.yaml"
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
# rate limit for "inject held" warnings, per node
INJECT_WARN_INTERVAL_SECONDS = 300.0


class DialogState(str, Enum):
    """Classification of a node's pane when delivering a message.

    READY — input line rendered, safe to type
    DIALOG — an option dialog is open (AskUserQuestion etc.); never type
    NOT_SUBMITTED — a paste chip sits in the input box (Enter was lost);
        resubmission is handled by the driver
    UNKNOWN — cannot tell; hold the message rather than misfire
    """

    READY = "ready"
    DIALOG = "dialog"
    NOT_SUBMITTED = "not-submitted"
    UNKNOWN = "unknown"


# substrings that identify an option dialog in the pane bottom region
DIALOG_MARKER_STRINGS = [
    "Choose an option",
    "choose an option",
    "Select an option",
    "select an option",
    "Enter to select",
    "Press Enter to select",
]
# numbered-option line, e.g. "  1. Do the thing" / "1) Do the thing"
DIALOG_OPTION_PATTERN = r"^\s*[0-9]{1,2}[.)]\s+\S"
# paste chip left in the input box, e.g. "[Pasted text #1 +23 lines]"
PASTED_TEXT_PATTERN = r"\[Pasted text #\d+"
# how many non-empty trailing lines count as the pane's "bottom region"
PANE_BOTTOM_LINES = 12

# defaults
DEFAULT_CONTROL_BACKEND = Backend.CLAUDE
