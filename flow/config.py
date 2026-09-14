"""flow.yaml parsing and DAG validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from flow import constants as C
from flow.paths import ProjectPaths


class ConfigError(Exception):
    pass


@dataclass
class NodeConfig:
    name: str
    agent: str
    backend: C.Backend
    task: str
    needs: list[str] = field(default_factory=list)
    gate: bool = False
    timeout: float | None = None
    retry: int = 0
    inject: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class PipelineConfig:
    name: str
    nodes: dict[str, NodeConfig]
    control: bool = False
    control_backend: C.Backend = C.DEFAULT_CONTROL_BACKEND

    def topological_order(self) -> list[str]:
        """Kahn's algorithm; deterministic (insertion order preserved)."""
        indeg = {n: len(set(c.needs)) for n, c in self.nodes.items()}
        children: dict[str, list[str]] = {n: [] for n in self.nodes}
        for n, c in self.nodes.items():
            for d in set(c.needs):
                children[d].append(n)
        queue = [n for n in self.nodes if indeg[n] == 0]
        order: list[str] = []
        while queue:
            n = queue.pop(0)
            order.append(n)
            for ch in children[n]:
                indeg[ch] -= 1
                if indeg[ch] == 0:
                    queue.append(ch)
        if len(order) != len(self.nodes):
            raise ConfigError("cycle detected in `needs` dependency graph")
        return order


def _parse_node(name: str, raw: dict, agents_dir: Path) -> NodeConfig:
    def err(msg: str) -> ConfigError:
        return ConfigError(f"node `{name}`: {msg}")

    if not isinstance(raw, dict):
        raise err("must be a mapping")
    agent = raw.get("agent")
    if not agent:
        raise err("missing required field `agent`")
    if not (agents_dir / agent / C.AGENT_MD).is_file():
        raise err(f"agent `{agent}` not found under {agents_dir} (need {C.AGENT_MD})")
    backend_raw = raw.get("backend")
    try:
        backend = C.Backend(backend_raw)
    except ValueError:
        valid = [b.value for b in C.Backend]
        raise err(f"invalid backend `{backend_raw}` (expected one of {valid})")
    task = raw.get("task")
    if not task or not isinstance(task, str):
        raise err("missing required field `task`")
    needs = raw.get("needs") or []
    if not isinstance(needs, list) or not all(isinstance(x, str) for x in needs):
        raise err("`needs` must be a list of node names")
    gate = raw.get("gate", False)
    timeout = raw.get("timeout")
    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
        raise err("`timeout` must be a positive number or null")
    retry = raw.get("retry", 0)
    if not isinstance(retry, int) or retry < 0:
        raise err("`retry` must be a non-negative integer")
    inject = raw.get("inject") or []
    if not isinstance(inject, list) or not all(isinstance(x, str) for x in inject):
        raise err("`inject` must be a list of run-relative paths")
    env = raw.get("env") or {}
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in env.items()
    ):
        raise err("`env` must be a mapping of string to string")
    return NodeConfig(
        name=name,
        agent=agent,
        backend=backend,
        task=task,
        needs=list(dict.fromkeys(needs)),
        gate=gate,
        timeout=timeout,
        retry=retry,
        inject=inject,
        env=env,
    )


def load_config(pipeline_file: Path) -> PipelineConfig:
    project = ProjectPaths(pipeline_file.parent).find_project_root()
    try:
        raw = yaml.safe_load(pipeline_file.read_text())
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML in {pipeline_file}: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"{pipeline_file} must be a mapping")
    name = raw.get("name")
    if not name:
        raise ConfigError("missing required field `name`")
    nodes_raw = raw.get("nodes")
    if not isinstance(nodes_raw, dict) or not nodes_raw:
        raise ConfigError("missing required field `nodes` (non-empty mapping)")

    nodes: dict[str, NodeConfig] = {}
    for nname, nraw in nodes_raw.items():
        if nname == C.CONTROL_NODE:
            raise ConfigError(f"node name `{C.CONTROL_NODE}` is reserved")
        nodes[nname] = _parse_node(nname, nraw, project.agents_dir)

    for cfg in nodes.values():
        for dep in cfg.needs:
            if dep not in nodes:
                raise ConfigError(f"node `{cfg.name}`: needs unknown node `{dep}`")

    control = raw.get("control", False)
    control_backend_raw = raw.get("control_backend")
    control_backend = C.DEFAULT_CONTROL_BACKEND
    if control_backend_raw is not None:
        try:
            control_backend = C.Backend(control_backend_raw)
        except ValueError:
            valid = [b.value for b in C.Backend]
            raise ConfigError(f"invalid control_backend (expected one of {valid})")

    cfg = PipelineConfig(
        name=str(name), nodes=nodes, control=control, control_backend=control_backend
    )
    cfg.topological_order()  # raises on cycle
    return cfg
