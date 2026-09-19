"""Run state persistence (state.json) — the single entry point for status changes."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from flow import constants as C


@dataclass
class NodeState:
    status: C.NodeStatus = C.NodeStatus.PENDING
    attempts: int = 0
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None


@dataclass
class RunState:
    pipeline: str
    run_id: str
    paused: bool = False
    nodes: dict[str, NodeState] = field(default_factory=dict)
    # set when this run is a sub-pipeline spawned inside another run's agent
    parent_run_id: str | None = None

    def node(self, name: str) -> NodeState:
        if name not in self.nodes:
            self.nodes[name] = NodeState()
        return self.nodes[name]

    def set_status(self, name: str, status: C.NodeStatus) -> None:
        st = self.node(name)
        st.status = status
        if status == C.NodeStatus.RUNNING:
            st.started_at = _now()
            st.finished_at = None
            st.error = None
            st.attempts += 1
        elif status.terminal:
            st.finished_at = _now()

    def all_terminal(self) -> bool:
        # control is a persistent conversation node, not a pipeline node;
        # exclude it from the completion check
        return all(
            s.status.terminal
            for n, s in self.nodes.items()
            if n != C.CONTROL_NODE
        )

    def save(self, path: Path) -> None:
        data = asdict(self)
        data["paused"] = self.paused
        data["nodes"] = {
            k: {**asdict(v), "status": v.status.value} for k, v in self.nodes.items()
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "RunState":
        raw = json.loads(path.read_text())
        st = cls(
            pipeline=raw["pipeline"],
            run_id=raw["run_id"],
            paused=raw.get("paused", False),
            parent_run_id=raw.get("parent_run_id"),
        )
        for name, ns in raw.get("nodes", {}).items():
            st.nodes[name] = NodeState(
                status=C.NodeStatus(ns["status"]),
                attempts=ns.get("attempts", 0),
                started_at=ns.get("started_at"),
                finished_at=ns.get("finished_at"),
                error=ns.get("error"),
            )
        return st


def _now() -> float:
    import time

    return time.time()
