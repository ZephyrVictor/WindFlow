"""flow CLI entry point."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from flow import __version__
from flow import constants as C
from flow import session as tmux
from flow.config import ConfigError, load_config
from flow.constants import NodeStatus
from flow.driver import BackendDriver
from flow.orchestrator import Orchestrator, OrchestratorError
from flow.paths import (
    PathError,
    ProjectPaths,
    RunPaths,
    latest_run_id,
    new_run_id,
)
from flow.state import RunState


def _project(args) -> ProjectPaths:
    root = Path(args.project).resolve() if getattr(args, "project", None) else Path.cwd()
    return ProjectPaths(root).find_project_root()


def _run(args) -> RunPaths:
    project = _project(args)
    run_id = getattr(args, "run_id", None) or latest_run_id(project)
    if run_id is None:
        sys.exit(f"no runs found under {project.runs_dir}")
    return RunPaths(project, run_id)


def _load_run_context(run: RunPaths):
    cfg = load_config(run.project.pipeline_file)
    state = RunState.load(run.state_file)
    driver = BackendDriver(run.project, run, {n: c.env for n, c in cfg.nodes.items()})
    orch = Orchestrator(run.project, run, cfg, state, driver)
    return cfg, state, orch


def cmd_run(args) -> None:
    project = _project(args)
    cfg = load_config(project.pipeline_file)
    run_id = new_run_id()
    run = RunPaths(project, run_id)
    state = RunState(pipeline=cfg.name, run_id=run_id)
    driver = BackendDriver(project, run, {n: c.env for n, c in cfg.nodes.items()})
    orch = Orchestrator(project, run, cfg, state, driver)
    orch.initialize()
    print(f"run {run_id} started; tmux session: {run.tmux_session_name}")
    try:
        orch.run_loop()
    except KeyboardInterrupt:
        state.save(run.state_file)
        print(f"\ninterrupted; state saved. resume with: flow resume {run_id}")
        return
    print(orch.status_text())


def cmd_status(args) -> None:
    _, _, orch = _load_run_context(_run(args))
    print(orch.status_text())


def cmd_attach(args) -> None:
    run = _run(args)
    if not tmux.has_session(run.tmux_session_name):
        sys.exit(f"no tmux session {run.tmux_session_name}")
    node = getattr(args, "node", None)
    if node:
        cfg, _, _ = _load_run_context(run)
        if node not in cfg.nodes:
            sys.exit(f"unknown node {node}")
        with tmux.hold_node_lock(run, node):
            os.execvp(
                "tmux",
                ["tmux", "attach-session", "-t", run.tmux_session_name],
            )
    os.execvp("tmux", ["tmux", "attach-session", "-t", run.tmux_session_name])


def cmd_log(args) -> None:
    run = _run(args)
    log = run.node_tty_log(args.node)
    if not log.is_file():
        sys.exit(f"no tty log at {log}")
    os.execvp("less", ["less", "-R", str(log)])


def cmd_resume(args) -> None:
    run = _run(args)
    cfg, state, orch = _load_run_context(run)
    if state.all_terminal():
        print("run already finished")
        return
    state.paused = False
    orch.run_loop()
    print(orch.status_text())


def cmd_stop(args) -> None:
    run = _run(args)
    if tmux.has_session(run.tmux_session_name):
        tmux.kill_session(run.tmux_session_name)
        print(f"tmux session {run.tmux_session_name} killed")
    _, state, _ = _load_run_context(run)
    state.paused = True
    state.save(run.state_file)
    print(f"run {run.run_id} marked paused")


def cmd_approve(args) -> None:
    _, _, orch = _load_run_context(_run(args))
    try:
        orch.approve(args.node)
    except OrchestratorError as e:
        sys.exit(str(e))
    print(f"node {args.node} approved (done)")


def cmd_retry(args) -> None:
    _, _, orch = _load_run_context(_run(args))
    try:
        orch.retry(args.node)
    except OrchestratorError as e:
        sys.exit(str(e))
    print(f"node {args.node} reset to pending; run `flow resume`")


def cmd_inject(args) -> None:
    _, _, orch = _load_run_context(_run(args))
    try:
        orch.inject(args.node, args.message)
    except OrchestratorError as e:
        sys.exit(str(e))
    print(f"queued message for {args.node}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="flow", description="multi-agent pipeline orchestrator")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("-p", "--project", help="project root (default: cwd upward search)")

    sp = sub.add_parser("run", help="start a new run")
    common(sp)
    sp.set_defaults(func=cmd_run)

    for name, help_ in [
        ("status", "show run status"),
        ("resume", "resume a paused/interrupted run"),
        ("stop", "kill tmux session and pause run"),
    ]:
        sp = sub.add_parser(name, help=help_)
        common(sp)
        sp.add_argument("run_id", nargs="?", help="run id (default: latest)")
        sp.set_defaults(func=globals()[f"cmd_{name}"])

    sp = sub.add_parser("attach", help="attach to run tmux session")
    common(sp)
    sp.add_argument("node", nargs="?", help="node name; holds its attach lock while attached")
    sp.add_argument("run_id", nargs="?", help="run id (default: latest)")
    sp.set_defaults(func=cmd_attach)

    sp = sub.add_parser("log", help="view a node's tty log")
    common(sp)
    sp.add_argument("node")
    sp.add_argument("run_id", nargs="?", help="run id (default: latest)")
    sp.set_defaults(func=cmd_log)

    sp = sub.add_parser("approve", help="approve a waiting-human gate node")
    common(sp)
    sp.add_argument("node")
    sp.add_argument("run_id", nargs="?")
    sp.set_defaults(func=cmd_approve)

    sp = sub.add_parser("retry", help="reset a node to pending")
    common(sp)
    sp.add_argument("node")
    sp.add_argument("run_id", nargs="?")
    sp.set_defaults(func=cmd_retry)

    sp = sub.add_parser("inject", help="queue a message to a running node")
    common(sp)
    sp.add_argument("node")
    sp.add_argument("message")
    sp.add_argument("run_id", nargs="?")
    sp.set_defaults(func=cmd_inject)

    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (ConfigError, PathError, OrchestratorError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
