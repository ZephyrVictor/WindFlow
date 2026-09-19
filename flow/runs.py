"""Cross-run queries: scan a project's runs, parent/child relations, tree view.

Sub-pipelines spawned with `flow run -f` live beside their parent in runs/
and record parent_run_id; these helpers make the relation visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from flow import constants as C
from flow import session as tmux
from flow.paths import ProjectPaths, RunPaths
from flow.state import RunState


@dataclass
class RunSummary:
    run_id: str
    project: ProjectPaths
    pipeline_name: str
    paused: bool
    parent_run_id: str | None
    node_statuses: dict[str, str]

    @property
    def run(self) -> RunPaths:
        return RunPaths(self.project, self.run_id)

    @property
    def alive(self) -> bool:
        return tmux.has_session(self.run.tmux_session_name)

    @property
    def running_count(self) -> int:
        # control is a persistent conversation, not pipeline work
        return sum(
            1 for n, s in self.node_statuses.items()
            if s == C.NodeStatus.RUNNING.value and n != C.CONTROL_NODE
        )

    @property
    def terminal(self) -> bool:
        return all(
            C.NodeStatus(s).terminal
            for n, s in self.node_statuses.items()
            if n != C.CONTROL_NODE
        )

    @property
    def tmux_mark(self) -> str:
        """alive | gone | paused(gone) | MISSING(zombie).

        MISSING = run believes it is running but its tmux session is gone
        and nobody paused it — the orchestrator died or the session was
        killed externally. Prime `flow clean` / resume-or-forget material.
        """
        if self.alive:
            return "tmux=alive"
        if self.terminal:
            return "tmux=gone"
        if self.paused:
            return "tmux=paused(gone)"
        return "tmux=MISSING(zombie)"

    @property
    def state_mark(self) -> str:
        if self.paused:
            return "paused"
        if self.terminal:
            return "done"
        return "running"


def scan_runs(project: ProjectPaths) -> list[RunSummary]:
    """All runs under the project that have a readable state.json."""
    out: list[RunSummary] = []
    if not project.runs_dir.is_dir():
        return out
    for d in sorted(project.runs_dir.iterdir()):
        if not d.is_dir():
            continue
        state_file = d / C.STATE_FILE
        if not state_file.is_file():
            continue
        try:
            st = RunState.load(state_file)
        except (ValueError, OSError):
            continue
        out.append(
            RunSummary(
                run_id=d.name,
                project=project,
                pipeline_name=st.pipeline,
                paused=st.paused,
                parent_run_id=st.parent_run_id,
                node_statuses={
                    n: s.status.value for n, s in st.nodes.items()
                },
            )
        )
    return out


def children_map(runs: list[RunSummary]) -> dict[str | None, list[RunSummary]]:
    """parent run id -> its children; None holds the roots.

    A child whose parent dir no longer exists is surfaced as a root so it
    stays reachable in the tree.
    """
    ids = {r.run_id for r in runs}
    out: dict[str | None, list[RunSummary]] = {None: []}
    for r in runs:
        parent = r.parent_run_id
        if parent is not None and parent not in ids:
            parent = None
        out.setdefault(parent, []).append(r)
    return out


def non_terminal_run_ids(runs: list[RunSummary]) -> list[str]:
    return [r.run_id for r in runs if not r.terminal]


def _describe(r: RunSummary) -> str:
    parts = [r.run_id, r.pipeline_name, f"[{r.state_mark}]"]
    if r.running_count:
        parts.append(f"running={r.running_count}")
    parts.append(r.tmux_mark)
    line = "  ".join(parts)
    if r.alive:
        windows = tmux.list_window_names(r.run.tmux_session_name)
        if windows:
            line += "\n      windows: " + " ".join(windows)
    return line


def render_run_tree(runs: list[RunSummary]) -> str:
    kids = children_map(runs)

    def walk(run_id: str | None, prefix: str, out: list[str]) -> None:
        children = kids.get(run_id, [])
        for i, r in enumerate(children):
            last = i == len(children) - 1
            branch = "└─ " if last else "├─ "
            out.append(prefix + branch + _describe(r))
            walk(r.run_id, prefix + ("   " if last else "│  "), out)

    out: list[str] = []
    walk(None, "", out)
    return "\n".join(out) if out else "no runs found"
