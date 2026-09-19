"""Backend drivers: launch claude/codex in tmux, deliver prompts, detect completion.

Completion detection is flag-file based (done.flag), written by:
- claude: Stop hook in per-node settings.json
- codex:  notify command in per-node CODEX_HOME/config.toml

Environment: node-level `env` from flow.yaml plus orchestrator-injected auth
variables are passed via `tmux new-session/new-window` command-line env
assignments, so we never depend on stale tmux-server globals.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from flow import constants as C
from flow import session as tmux
from flow.config import NodeConfig
from flow.paths import ProjectPaths, RunPaths

# Env vars the orchestrator transparently forwards to agent processes so they
# share the user's login/gateway configuration.
FORWARDED_ENV_VARS = [
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "PATH",
    "HOME",
]


class DriverError(Exception):
    pass


def classify_pane(pane_text: str) -> C.DialogState:
    """Classify a pane capture for safe prompt delivery.

    Pure function over the captured text. Order matters:
    1. empty capture -> UNKNOWN
    2. paste chip at/after the last input-prompt line -> NOT_SUBMITTED
       (Enter was lost; a *submitted* paste lives above the input box)
    3. explicit option-dialog markers -> DIALOG
    4. rendered input line (❯/›) -> READY
    5. >=2 consecutive numbered-option lines in the bottom region -> DIALOG
    6. anything else -> UNKNOWN (caller holds the message, never drops it)
    """
    content = [l for l in pane_text.splitlines() if l.strip()]
    if not content:
        return C.DialogState.UNKNOWN
    last_prompt = -1
    for i, l in enumerate(content):
        if "❯" in l or "›" in l:
            last_prompt = i
    # chip inside the input box: at/after the prompt line, or in the very
    # bottom lines when no prompt line is rendered at all
    lo = max(last_prompt, len(content) - 3)
    for l in content[lo:]:
        if re.search(C.PASTED_TEXT_PATTERN, l):
            return C.DialogState.NOT_SUBMITTED
    bottom = content[-C.PANE_BOTTOM_LINES:]
    bottom_text = "\n".join(bottom)
    for marker in C.DIALOG_MARKER_STRINGS:
        if marker in bottom_text:
            return C.DialogState.DIALOG
    for l in content[-6:]:
        if "❯" in l or "›" in l:
            return C.DialogState.READY
    consecutive = 0
    for l in bottom:
        if re.match(C.DIALOG_OPTION_PATTERN, l):
            consecutive += 1
            if consecutive >= 2:
                return C.DialogState.DIALOG
        else:
            consecutive = 0
    return C.DialogState.UNKNOWN


class BackendDriver:
    """Prepares per-node runtime files and builds launch commands."""

    def __init__(self, project: ProjectPaths, run: RunPaths, node_env: dict[str, str]):
        self.project = project
        self.run = run
        self.node_env = node_env

    # -- completion ---------------------------------------------------------

    def done(self, node: str) -> bool:
        return self.run.node_done_flag(node).exists()

    def reset_done(self, node: str) -> None:
        flag = self.run.node_done_flag(node)
        flag.unlink(missing_ok=True)

    # -- preparation --------------------------------------------------------

    def prepare(self, node: str, cfg: NodeConfig) -> None:
        self.run.node_dir(node).mkdir(parents=True, exist_ok=True)
        if cfg.backend is C.Backend.CLAUDE:
            self._write_claude_settings(node)
        elif cfg.backend is C.Backend.CODEX:
            self._write_codex_home(node)

    def _write_claude_settings(self, node: str) -> None:
        flag = self.run.node_done_flag(node)
        settings = {
            "hooks": {
                "Stop": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"touch {flag}",
                            }
                        ]
                    }
                ]
            }
        }
        self.run.node_claude_settings(node).write_text(
            json.dumps(settings, indent=2)
        )

    def _write_codex_home(self, node: str) -> None:
        home = self.run.node_codex_home(node)
        home.mkdir(parents=True, exist_ok=True)
        flag = self.run.node_done_flag(node)
        cfg_lines = [
            'notify = ["touch", "' + str(flag) + '"]',
        ]
        # inherit user's model/provider config so login and gateway still work
        user_cfg = Path.home() / ".codex" / "config.toml"
        if user_cfg.is_file():
            cfg_lines.insert(0, user_cfg.read_text().rstrip() + "\n")
        (home / "config.toml").write_text("\n".join(cfg_lines) + "\n")
        auth = Path.home() / ".codex" / "auth.json"
        if auth.is_file():
            target = home / "auth.json"
            if not target.exists():
                target.symlink_to(auth)

    # -- launch ---------------------------------------------------------

    def launch_command(self, node: str, cfg: NodeConfig) -> str:
        env_part = self._env_prefix(cfg)
        if cfg.backend is C.Backend.CLAUDE:
            settings = self.run.node_claude_settings(node)
            trust = self._claude_trust_arg()
            return (
                f"{env_part}claude --settings {settings}{trust}"
            )
        if cfg.backend is C.Backend.CODEX:
            home = self.run.node_codex_home(node)
            return f"{env_part}CODEX_HOME={home} codex"
        raise DriverError(f"unknown backend for node {node}")

    def _claude_trust_arg(self) -> str:
        # Skip the folder-trust dialog so unattended startup never blocks.
        return " --dangerously-skip-permissions"

    def _env_prefix(self, cfg: NodeConfig) -> str:
        env = {}
        for k in FORWARDED_ENV_VARS:
            v = os.environ.get(k)
            if v:
                env[k] = v
        env.update(self.node_env.get(cfg.name, {}))
        # after node_env so a yaml `env:` entry cannot clobber the run id
        env[C.FLOW_RUN_ID_ENV] = self.run.run_id
        return "".join(f"{k}='{v}' " for k, v in env.items())

    # -- prompt delivery ---------------------------------------------------

    def send_prompt(self, node: str, text: str) -> None:
        tmux.wait_window(self.run, node)
        self._wait_tui_ready(node)
        # defer while a human is attached to this node's window
        import time as _time

        waited = 0.0
        while tmux.node_locked(self.run, node):
            if waited >= C.ATTACH_RETRY_SECONDS:
                waited = 0.0  # keep waiting indefinitely; human intervention is expected
            _time.sleep(1.0)
            waited += 1.0
        tmux.send_text(self.run, node, text)
        self._confirm_submitted(node)

    def _confirm_submitted(self, node: str, attempts: int = 3) -> None:
        """Verify the text actually left the input box (Enter took effect).

        Long pastes can end up as a "[Pasted text #N]" chip still sitting in
        the input line with the Enter swallowed — observed as a 3h hang in a
        production run. Re-send Enter and re-check; give up as DriverError so
        the caller can fail the node instead of idling forever.
        """
        import time as _time

        for _ in range(attempts):
            _time.sleep(1.0)
            state = classify_pane(tmux.capture_pane(self.run, node, lines=40))
            if state is not C.DialogState.NOT_SUBMITTED:
                return
            tmux.send_keys(self.run, node, "Enter")
        raise DriverError(
            f"prompt for {node} not submitted after {attempts} Enter retries"
        )

    def _wait_tui_ready(self, node: str, timeout: float = 90.0) -> None:
        """Wait until the CLI input box is interactive.

        claude: welcome box must be gone (only the ❯ prompt line remains).
        codex: the › input line is present.
        """
        import time as _time

        deadline = _time.monotonic() + timeout
        while _time.monotonic() < deadline:
            pane = tmux.capture_pane(self.run, node, lines=40)
            lines = [l for l in pane.splitlines() if l.strip()]
            if not lines:
                _time.sleep(1.0)
                continue
            if "›" in pane:  # codex input line ready
                return
            if any("❯" in l for l in lines[-6:]):  # claude input line rendered
                return
            _time.sleep(1.0)
        raise DriverError(f"TUI for {node} not ready within {timeout}s")
