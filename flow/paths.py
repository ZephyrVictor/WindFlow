"""Directory conventions and path resolution.

A project is any directory containing flow.yaml. Layout:

    <project>/
    ├── flow.yaml
    ├── agents/<name>/agent.md         # agent definitions, project-scoped
    ├── workdir/                       # shared working area (persistent)
    └── runs/<run-id>/
        ├── memory/{context,findings,decisions}.md
        ├── agents/<node>/{agent.md, task.md, memory.md, summary.md, tty.log, done.flag, ...}
        ├── artifacts/
        ├── state.json
        ├── .tmux.conf
        └── attach.lock
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path

from flow import constants as C


class PathError(Exception):
    pass


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    @property
    def pipeline_file(self) -> Path:
        return self.root / C.PIPELINE_FILE

    @property
    def agents_dir(self) -> Path:
        return self.root / C.AGENTS_DIR

    @property
    def workdir(self) -> Path:
        return self.root / C.WORKDIR_NAME

    @property
    def runs_dir(self) -> Path:
        return self.root / C.RUNS_DIR

    def agent_def_dir(self, agent_name: str) -> Path:
        return self.agents_dir / agent_name

    def find_project_root(self) -> "ProjectPaths":
        """Project root is the nearest ancestor containing flow.yaml."""
        cur = self.root.resolve()
        for cand in (cur, *cur.parents):
            if (cand / C.PIPELINE_FILE).is_file():
                return ProjectPaths(cand)
        raise PathError(f"no {C.PIPELINE_FILE} found in {cur} or its ancestors")


@dataclass(frozen=True)
class RunPaths:
    project: ProjectPaths
    run_id: str

    @property
    def root(self) -> Path:
        return self.project.runs_dir / self.run_id

    @property
    def memory_dir(self) -> Path:
        return self.root / C.MEMORY_DIR

    @property
    def nodes_dir(self) -> Path:
        return self.root / C.NODE_DIR

    @property
    def artifacts_dir(self) -> Path:
        return self.root / C.ARTIFACTS_DIR

    @property
    def state_file(self) -> Path:
        return self.root / C.STATE_FILE

    @property
    def tmux_conf(self) -> Path:
        return self.root / C.TMUX_CONF

    @property
    def attach_lock(self) -> Path:
        return self.root / C.ATTACH_LOCK

    @property
    def tmux_session_name(self) -> str:
        return f"{C.TMUX_SESSION_PREFIX}{self.run_id}"

    def node_dir(self, node: str) -> Path:
        return self.nodes_dir / node

    def node_agent_md(self, node: str) -> Path:
        return self.node_dir(node) / C.AGENT_MD

    def node_task_file(self, node: str) -> Path:
        return self.node_dir(node) / C.TASK_FILE

    def node_memory_file(self, node: str) -> Path:
        return self.node_dir(node) / C.MEMORY_FILE

    def node_summary_file(self, node: str) -> Path:
        return self.node_dir(node) / C.SUMMARY_FILE

    def node_tty_log(self, node: str) -> Path:
        return self.node_dir(node) / C.TTY_LOG

    def node_done_flag(self, node: str) -> Path:
        return self.node_dir(node) / C.DONE_FLAG

    def node_session_id(self, node: str) -> Path:
        return self.node_dir(node) / C.SESSION_ID_FILE

    def node_claude_settings(self, node: str) -> Path:
        return self.node_dir(node) / C.CLAUDE_SETTINGS

    def node_codex_home(self, node: str) -> Path:
        return self.node_dir(node) / C.CODEX_HOME_DIR

    def window_name(self, index: int, node: str) -> str:
        return f"{index:02d}{C.WINDOW_INDEX_SEP}{node}"

    def create(self) -> None:
        for d in (
            self.root,
            self.memory_dir,
            self.nodes_dir,
            self.artifacts_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


def new_run_id() -> str:
    now = _dt.datetime.now()
    base = now.strftime("%Y%m%d-%H%M%S")
    return base


def latest_run_id(project: ProjectPaths) -> str | None:
    runs = project.runs_dir
    if not runs.is_dir():
        return None
    ids = sorted(p.name for p in runs.iterdir() if p.is_dir())
    return ids[-1] if ids else None
