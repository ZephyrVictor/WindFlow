"""All tmux operations and attach-lock management live here."""

from __future__ import annotations

import fcntl
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

from flow import constants as C
from flow.paths import RunPaths


class TmuxError(Exception):
    pass


def _run(args: list[str], check: bool = True):
    proc = subprocess.run(
        ["tmux", *args], capture_output=True, text=True
    )
    if check and proc.returncode != 0:
        raise TmuxError(f"tmux {' '.join(args)}: {proc.stderr.strip()}")
    return proc if not check else proc.stdout


def has_session(name: str) -> bool:
    return _run(["has-session", "-t", name], check=False).returncode == 0


def kill_session(name: str) -> None:
    _run(["kill-session", "-t", name], check=False)


def new_session(
    name: str, run: RunPaths, node: str, command: str, cwd: Path
) -> None:
    """Create session whose first window is this node's CLI."""
    window = run.window_name(0, node)
    _run(
        [
            "new-session",
            "-d",
            "-s",
            name,
            "-n",
            window,
            "-x",
            "200",
            "-y",
            "50",
            "-c",
            str(cwd),
            command,
        ]
    )


def new_window(run: RunPaths, index: int, node: str, command: str, cwd: Path) -> None:
    _run(
        [
            "new-window",
            "-t",
            run.tmux_session_name,
            "-n",
            run.window_name(index, node),
            "-c",
            str(cwd),
            command,
        ]
    )


def _list_window_names(session: str) -> list[str]:
    proc = subprocess.run(
        ["tmux", "list-windows", "-t", session, "-F", "#{window_name}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []
    return proc.stdout.splitlines()


list_window_names = _list_window_names


def _resolve_window_name(run: RunPaths, node: str) -> str | None:
    """Windows are named `<idx>-<node>`; resolve bare node name to full name."""
    for w in _list_window_names(run.tmux_session_name):
        if w == node or w.endswith(C.WINDOW_INDEX_SEP + node):
            return w
    return None


resolve_window_name = _resolve_window_name


def kill_window(run: RunPaths, full_window_name: str) -> None:
    _run(["kill-window", "-t", f"{run.tmux_session_name}:={full_window_name}"])


def _pane_target(run: RunPaths, node: str) -> str:
    full = _resolve_window_name(run, node)
    if full is None:
        raise TmuxError(f"no window for node {node} in {run.tmux_session_name}")
    return f"{run.tmux_session_name}:={full}"


def pipe_pane(run: RunPaths, node: str, log_file: Path) -> None:
    _run(["pipe-pane", "-t", _pane_target(run, node), "-o", f"cat >> {log_file}"])


def send_text(run: RunPaths, node: str, text: str) -> None:
    """Send literal text then Enter. Uses bracketed paste for multiline safety."""
    target = _pane_target(run, node)
    _run(["send-keys", "-t", target, "-l", text])
    _run(["send-keys", "-t", target, "Enter"])


def send_keys(run: RunPaths, node: str, keys: str) -> None:
    _run(["send-keys", "-t", _pane_target(run, node), keys])


def capture_pane(run: RunPaths, node: str, lines: int = 30) -> str:
    out = _run(["capture-pane", "-t", _pane_target(run, node), "-p", "-S", f"-{lines}"])
    return out


def window_exists(run: RunPaths, node: str) -> bool:
    return _resolve_window_name(run, node) is not None


def wait_window(run: RunPaths, node: str, timeout: float = 30.0) -> None:
    import time as _time

    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if window_exists(run, node):
            # give the CLI process a moment to start drawing its TUI
            _time.sleep(2.0)
            return
        _time.sleep(0.5)
    raise TmuxError(f"window {node} did not appear within {timeout}s")


def write_tmux_conf(run: RunPaths) -> None:
    run.tmux_conf.write_text(C.TMUX_CONF_CONTENT + "\n")


def session_env(name: str, env: dict[str, str]) -> None:
    for k, v in env.items():
        _run(["set-environment", "-t", name, k, v])


def set_global_env(env: dict[str, str]) -> None:
    """Ensure the tmux server carries auth env; panes inherit from it."""
    current = _run(["show-environment", "-g"], check=False)
    for k, v in env.items():
        if f"{k}=" not in current:
            _run(["set-environment", "-g", k, v])


def list_flow_sessions() -> list[str]:
    proc = _run(["list-sessions", "-F", "#{session_name}"], check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    return [s for s in proc.stdout.splitlines() if s.startswith(C.TMUX_SESSION_PREFIX)]


# -- attach locking -------------------------------------------------------


def _lock_file(run: RunPaths, node: str) -> Path:
    return run.attach_lock.parent / f"{run.attach_lock.stem}.{node}.lock"


def node_locked(run: RunPaths, node: str) -> bool:
    """True while a human is attached to this node's window."""
    f = _lock_file(run, node)
    if not f.exists():
        return False
    fd = None
    try:
        fd = open(f, "r")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False  # acquired -> nobody holds it (stale file)
        except BlockingIOError:
            return True
    finally:
        if fd is not None:
            fd.close()


@contextmanager
def hold_node_lock(run: RunPaths, node: str):
    """Acquire the interactive lock for `flow attach`."""
    f = _lock_file(run, node)
    f.parent.mkdir(parents=True, exist_ok=True)
    fd = open(f, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fd.close()
