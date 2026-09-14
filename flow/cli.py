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


def _pipeline_file(run: RunPaths, override: Path | None = None) -> Path:
    """Effective pipeline: -f override > run-local snapshot > project default."""
    if override is not None:
        return override
    if run.pipeline_file.is_file():
        return run.pipeline_file
    return run.project.pipeline_file


def _load_run_context(run: RunPaths):
    cfg = load_config(_pipeline_file(run))
    state = RunState.load(run.state_file)
    driver = BackendDriver(run.project, run, {n: c.env for n, c in cfg.nodes.items()})
    orch = Orchestrator(run.project, run, cfg, state, driver)
    return cfg, state, orch


def cmd_run(args) -> None:
    project = _project(args)
    pipeline_file = (
        Path(args.pipeline).resolve() if getattr(args, "pipeline", None) else None
    )
    cfg = load_config(pipeline_file or project.pipeline_file)
    run_id = new_run_id()
    run = RunPaths(project, run_id)
    state = RunState(pipeline=cfg.name, run_id=run_id)
    driver = BackendDriver(project, run, {n: c.env for n, c in cfg.nodes.items()})
    orch = Orchestrator(
        project, run, cfg, state, driver,
        pipeline_file=pipeline_file or project.pipeline_file,
    )
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


# -- write-side commands ----------------------------------------------------


def cmd_validate(args) -> None:
    f = (
        Path(args.file).resolve()
        if args.file
        else _project(args).pipeline_file
    )
    try:
        cfg = load_config(f)
    except ConfigError as e:
        sys.exit(f"invalid: {e}")
    order = cfg.topological_order()
    print(f"valid: {cfg.name} ({len(cfg.nodes)} nodes)")
    for n in order:
        c = cfg.nodes[n]
        needs = ",".join(c.needs) or "-"
        gate = " [gate]" if c.gate else ""
        print(f"  {n:<20} agent={c.agent:<16} backend={c.backend.value:<6} needs={needs}{gate}")


def cmd_agent(args) -> None:
    project = _project(args)
    if args.agent_cmd == "list":
        agents_dir = project.agents_dir
        if not agents_dir.is_dir():
            sys.exit(f"no agents dir at {agents_dir}")
        found = False
        for d in sorted(agents_dir.iterdir()):
            md = d / C.AGENT_MD
            if d.is_dir() and md.is_file():
                first = next(
                    (l.lstrip("# ").strip() for l in md.read_text().splitlines() if l.strip()),
                    "",
                )
                print(f"{d.name:<24} {first[:60]}")
                found = True
        if not found:
            print("no agents defined")
    elif args.agent_cmd == "show":
        md = project.agent_def_dir(args.name) / C.AGENT_MD
        if not md.is_file():
            sys.exit(f"no agent definition: {md}")
        sys.stdout.write(md.read_text())
    elif args.agent_cmd == "new":
        from flow import prompts

        d = project.agent_def_dir(args.name)
        md = d / C.AGENT_MD
        if md.exists():
            sys.exit(f"already exists: {md}")
        d.mkdir(parents=True, exist_ok=True)
        md.write_text(prompts.agent_md_template(args.name))
        print(f"created {md}")


def cmd_init(args) -> None:
    from flow import prompts

    root = Path(args.dir).resolve() if args.dir else Path.cwd()
    if (root / C.PIPELINE_FILE).exists():
        sys.exit(f"refusing to overwrite: {root / C.PIPELINE_FILE}")
    (root / C.AGENTS_DIR).mkdir(parents=True, exist_ok=True)
    control_md = root / C.AGENTS_DIR / C.CONTROL_NODE / C.AGENT_MD
    if not control_md.exists():
        control_md.parent.mkdir(parents=True, exist_ok=True)
        control_md.write_text(prompts.CONTROL_AGENT_MD)
    (root / C.WORKDIR_NAME).mkdir(parents=True, exist_ok=True)
    (root / C.WORKDIR_NAME / ".gitkeep").touch()
    (root / C.PIPELINE_FILE).write_text(prompts.INIT_FLOW_YAML_TEMPLATE)
    gi = root / ".gitignore"
    if not gi.exists():
        gi.write_text(prompts.INIT_GITIGNORE)
    print(prompts.init_next_steps(str(root)))


def cmd_clean(args) -> None:
    project = _project(args)
    cleaned = 0
    for name in tmux.list_flow_sessions():
        run_id = name[len(C.TMUX_SESSION_PREFIX):]
        state_file = RunPaths(project, run_id).state_file
        if not state_file.is_file():
            continue  # belongs to another project or still starting
        if RunState.load(state_file).all_terminal():
            tmux.kill_session(name)
            print(f"killed session {name} (run finished)")
            cleaned += 1
    if not args.runs and not cleaned:
        print("nothing to clean (no finished-run sessions)")
    if args.runs is not None:
        runs = project.runs_dir
        if not runs.is_dir():
            return
        ids = sorted(p.name for p in runs.iterdir() if p.is_dir())
        doomed = ids[: max(len(ids) - args.runs, 0)]
        if not doomed:
            print(f"only {len(ids)} runs, keeping all")
            return
        for run_id in doomed:
            print(f"delete runs/{run_id}? [y/N]", end=" ", flush=True)
            if input().strip().lower() == "y":
                import shutil

                shutil.rmtree(runs / run_id)
                print(f"deleted runs/{run_id}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="flow", description="multi-agent pipeline orchestrator")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("-p", "--project", help="project root (default: cwd upward search)")

    sp = sub.add_parser("run", help="start a new run")
    common(sp)
    sp.add_argument(
        "-f", "--pipeline",
        help="pipeline yaml to run (default: project flow.yaml)",
    )
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

    sp = sub.add_parser("validate", help="validate a pipeline yaml")
    common(sp)
    sp.add_argument("file", nargs="?", help="pipeline file (default: project flow.yaml)")
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("agent", help="manage agent definitions")
    common(sp)
    agent_sub = sp.add_subparsers(dest="agent_cmd", required=True)
    for cmd, help_ in [("list", "list agents"), ("show", "print agent.md"), ("new", "create agent from template")]:
        s = agent_sub.add_parser(cmd, help=help_)
        common(s)
        if cmd in ("show", "new"):
            s.add_argument("name")
    sp.set_defaults(func=cmd_agent)

    sp = sub.add_parser("init", help="scaffold a new flow project")
    sp.add_argument("dir", nargs="?", help="target directory (default: cwd)")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("clean", help="clean up finished-run tmux sessions (and optionally old runs)")
    common(sp)
    sp.add_argument("--runs", type=int, metavar="N", help="also delete all but the newest N run directories (interactive)")
    sp.set_defaults(func=cmd_clean)

    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (ConfigError, PathError, OrchestratorError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
