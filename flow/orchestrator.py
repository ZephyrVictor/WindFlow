"""Scheduling loop: dependency-ready launch, gate/failed pause, resume, inject queue."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from flow import constants as C
from flow import memory as flow_memory
from flow import session as tmux
from flow.config import PipelineConfig
from flow.constants import NodeStatus
from flow.driver import BackendDriver, DriverError, classify_pane
from flow.paths import ProjectPaths, RunPaths
from flow.state import RunState


class OrchestratorError(Exception):
    pass


@dataclass
class InjectQueue:
    """Persistent per-node message queue (survives across CLI processes)."""
    path: Path
    items: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "InjectQueue":
        import json as _json

        if path.is_file():
            items = _json.loads(path.read_text())
        else:
            items = {}
        return cls(path=path, items=items)

    def save(self) -> None:
        import json as _json

        self.path.write_text(_json.dumps(self.items, ensure_ascii=False))

    def add(self, node: str, message: str) -> None:
        self.items.setdefault(node, []).append(message)
        self.save()

    def take(self, node: str) -> list[str]:
        msgs = self.items.pop(node, [])
        if msgs:
            self.save()
        return msgs


class InjectLog:
    """Append-only jsonl receipt log: one `queued` line per inject, one
    `delivered` line per successful send. Audit aid only — the queue file
    stays the source of truth for pending messages."""

    def __init__(self, path: Path):
        self.path = path

    def append(self, event: str, node: str, message: str) -> None:
        import json as _json
        import time as _time

        rec = {
            "ts": round(_time.time(), 3),
            "event": event,
            "node": node,
            "message": message,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(_json.dumps(rec, ensure_ascii=False) + "\n")

    def replay(self) -> list[dict]:
        import json as _json

        if not self.path.is_file():
            return []
        out: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(_json.loads(line))
            except ValueError:
                continue  # torn tail line from a crashed writer
        return out


class Orchestrator:
    def __init__(
        self,
        project: ProjectPaths,
        run: RunPaths,
        cfg: PipelineConfig,
        state: RunState,
        driver: BackendDriver,
        pipeline_file: Path | None = None,
    ):
        self.project = project
        self.run = run
        self.cfg = cfg
        self.state = state
        self.driver = driver
        self.pipeline_file = pipeline_file or project.pipeline_file
        self.inject_queue = InjectQueue.load(
            run.root / C.INJECT_QUEUE_FILE
        )
        self.inject_log = InjectLog(run.root / C.INJECT_LOG_FILE)
        self._window_index = self._assign_window_indexes()
        # nodes that finished their main task and are now writing summary
        self._summarizing: set[str] = set()
        # per-node monotonic timestamp of the last "inject held" warning
        self._inject_warned_at: dict[str, float] = {}
        self._stop_requested = False

    def _assign_window_indexes(self) -> dict[str, int]:
        return {n: i for i, n in enumerate(self.cfg.topological_order())}

    # -- lifecycle ----------------------------------------------------------

    def initialize(self) -> None:
        """Fresh run: create dirs, shared memory, node files, tmux session."""
        self.run.create()
        # snapshot the effective pipeline so status/approve/retry resolve
        # the same node set even for `-f <file>` runs
        if not self.run.pipeline_file.exists():
            self.run.pipeline_file.write_text(self.pipeline_file.read_text())
        flow_memory.init_shared_memory(self.run, self.cfg)
        for cfg in self.cfg.nodes.values():
            flow_memory.prepare_node_files(self.run, self.project, cfg)
            self.driver.prepare(cfg.name, cfg)
            if self.state.node(cfg.name).status is NodeStatus.PENDING:
                pass  # state defaults are already pending
        tmux.write_tmux_conf(self.run)
        base_index = 1 if self.cfg.control else 0
        if not tmux.has_session(self.run.tmux_session_name):
            first, cfg0 = next(iter(self.cfg.nodes.items()))
            tmux.new_session(
                self.run.tmux_session_name,
                self.run,
                first,
                self.driver.launch_command(first, cfg0),
                self.project.workdir,
            )
            for name, cfg in list(self.cfg.nodes.items())[1:]:
                tmux.new_window(
                    self.run,
                    self._window_index[name] + base_index,
                    name,
                    self.driver.launch_command(name, cfg),
                    self.project.workdir,
                )
        for name in self.cfg.nodes:
            log = self.run.node_tty_log(name)
            log.touch()
            tmux.pipe_pane(self.run, name, log)
        if self.cfg.control:
            from flow import control as flow_control

            flow_control.launch_control(
                self.run, self.project, self.cfg, self.driver
            )
            # control is not a pipeline node; track it as running so that
            # `flow inject control ...` (e.g. from the watchdog) is accepted
            self.state.set_status(C.CONTROL_NODE, NodeStatus.RUNNING)
        self.state.save(self.run.state_file)

    def request_stop(self) -> None:
        self._stop_requested = True

    # -- scheduling ---------------------------------------------------------

    def run_loop(self) -> None:
        """Main poll loop. Returns when all nodes terminal or paused.

        State is reloaded from disk every tick so external commands
        (approve/retry/inject from other processes) take effect.
        """
        while not self._stop_requested:
            self._reload_state()
            self._tick()
            if self.state.paused:
                break
            if self.state.all_terminal():
                break
            time.sleep(C.POLL_INTERVAL_SECONDS)
        self.state.save(self.run.state_file)

    def _reload_state(self) -> None:
        from flow.state import RunState

        if self.run.state_file.is_file():
            self.state.__dict__.update(
                RunState.load(self.run.state_file).__dict__
            )
        # external CLI processes (flow inject) write the queue file directly;
        # merge new entries so they get delivered by _tick
        on_disk = InjectQueue.load(self.run.root / C.INJECT_QUEUE_FILE)
        for node, msgs in on_disk.items.items():
            queued = self.inject_queue.items.setdefault(node, [])
            for m in msgs:
                if m not in queued:
                    queued.append(m)

    def _tick(self) -> None:
        # 1. refresh running nodes
        for name, cfg in self.cfg.nodes.items():
            st = self.state.node(name)
            if st.status is not NodeStatus.RUNNING:
                continue
            if name in self._summarizing:
                if self.driver.done(name):
                    self._finish_summary(name)
                continue
            if self.driver.done(name):
                self._start_summary(name, cfg)
            elif self._timed_out(st, cfg):
                self._fail(name, "timeout")

        # 2. paused? nothing more to do
        if self.state.paused:
            return

        # 3. launch ready pending nodes
        for name, cfg in self.cfg.nodes.items():
            st = self.state.node(name)
            if st.status is not NodeStatus.PENDING:
                continue
            if all(
                self.state.node(d).status.satisfied
                for d in cfg.needs
            ):
                self._launch(name, cfg)

        # 4. deliver inject queue
        self._deliver_injects()

        self.state.save(self.run.state_file)

    def _deliver_injects(self) -> None:
        for name in list(self.inject_queue.items):
            st = self.state.node(name)
            if st.status is not NodeStatus.RUNNING:
                continue
            if name in self._summarizing:
                # never type into an option dialog; hold until the pane
                # shows a rendered input line again
                state = self._classify_node(name)
                if state is not C.DialogState.READY:
                    self._warn_inject_blocked(name, state)
                    continue
            msgs = self.inject_queue.take(name)
            for msg in msgs:
                try:
                    self.driver.send_prompt(name, msg)
                except (DriverError, tmux.TmuxError) as e:
                    # delivery failed — put it back; retried next tick
                    self.inject_queue.add(name, msg)
                    print(
                        f"inject delivery to {name} failed ({e}); "
                        f"message re-queued"
                    )
                else:
                    self.inject_log.append("delivered", name, msg)

    def _classify_node(self, name: str) -> C.DialogState:
        try:
            pane = tmux.capture_pane(self.run, name, lines=40)
        except tmux.TmuxError:
            return C.DialogState.UNKNOWN
        return classify_pane(pane)

    def _warn_inject_blocked(self, name: str, state: C.DialogState) -> None:
        now = time.monotonic()
        if now - self._inject_warned_at.get(name, 0.0) < C.INJECT_WARN_INTERVAL_SECONDS:
            return
        self._inject_warned_at[name] = now
        print(
            f"inject to {name} held (pane state: {state.value}); "
            f"message stays queued — inspect via `flow attach` or "
            f"`flow log {name}`"
        )

    # -- node transitions ----------------------------------------------------

    def _launch(self, name: str, cfg) -> None:
        self.driver.reset_done(name)
        prompt = flow_memory.build_task_prompt(self.run, self.project, cfg)
        # window may not exist (resume path); CLI may already be running fresh
        if not tmux.window_exists(self.run, name):
            cmd = self.driver.launch_command(name, cfg)
            if tmux.has_session(self.run.tmux_session_name):
                tmux.new_window(
                    self.run,
                    self._window_index[name],
                    name,
                    cmd,
                    self.project.workdir,
                )
        try:
            self.driver.send_prompt(name, prompt)
        except (DriverError, tmux.TmuxError) as e:
            # delivery broken (dead window, TUI never ready): fail loudly
            # instead of looping relaunches with attempts==0
            self.state.set_status(name, NodeStatus.FAILED)
            self.state.node(name).error = f"launch failed: {e}"
            self.state.paused = True
            return
        self.state.set_status(name, NodeStatus.RUNNING)

    def _reset_window(self, name: str) -> None:
        """Destroy the node's window so the next launch starts a fresh session."""
        full = tmux.resolve_window_name(self.run, name)
        if full is not None:
            tmux.kill_window(self.run, full)

    def _start_summary(self, name: str, cfg) -> None:
        self.driver.reset_done(name)
        self.driver.send_prompt(
            name, flow_memory.build_summary_prompt(self.run, cfg)
        )
        self._summarizing.add(name)

    def _finish_summary(self, name: str) -> None:
        self._summarizing.discard(name)
        cfg = self.cfg.nodes[name]
        if cfg.gate:
            self.state.set_status(name, NodeStatus.WAITING_HUMAN)
        else:
            self.state.set_status(name, NodeStatus.DONE)

    def _fail(self, name: str, reason: str) -> None:
        cfg = self.cfg.nodes[name]
        st = self.state.node(name)
        if st.attempts <= cfg.retry:
            # retry: relaunch from pending
            st.status = NodeStatus.PENDING
            st.error = reason
            return
        self.state.set_status(name, NodeStatus.FAILED, )
        self.state.node(name).error = reason
        self.state.paused = True

    def _timed_out(self, st, cfg) -> bool:
        if cfg.timeout is None or st.started_at is None:
            return False
        return (time.time() - st.started_at) > cfg.timeout

    # -- human actions ----------------------------------------------------

    def approve(self, node: str) -> None:
        st = self.state.node(node)
        if st.status is not NodeStatus.WAITING_HUMAN:
            raise OrchestratorError(
                f"node {node} is {st.status.value}, not waiting-human"
            )
        self.state.set_status(node, NodeStatus.DONE)
        if self.state.paused:
            self.state.paused = False
        self.state.save(self.run.state_file)

    def skip(self, node: str, reason: str | None = None) -> None:
        """Human gives up on a node; downstream treats it as satisfied."""
        st = self.state.node(node)
        if st.status is not NodeStatus.FAILED and st.status is not NodeStatus.WAITING_HUMAN:
            raise OrchestratorError(
                f"node {node} is {st.status.value}; only failed/waiting-human nodes can be skipped"
            )
        self._reset_window(node)
        self.state.set_status(node, NodeStatus.SKIPPED)
        st.error = reason or st.error
        if self.state.paused:
            self.state.paused = False
        self.state.save(self.run.state_file)

    def retry(self, node: str) -> None:
        st = self.state.node(node)
        if st.status not in (
            NodeStatus.FAILED,
            NodeStatus.DONE,
            NodeStatus.WAITING_HUMAN,
            NodeStatus.RUNNING,
        ):
            raise OrchestratorError(f"node {node} cannot be retried from {st.status.value}")
        st.status = NodeStatus.PENDING
        st.error = None
        self._summarizing.discard(node)
        self._reset_window(node)
        self.state.paused = False
        self.state.save(self.run.state_file)

    def inject(self, node: str, message: str) -> None:
        st = self.state.node(node)
        if st.status is not NodeStatus.RUNNING:
            raise OrchestratorError(f"node {node} is not running ({st.status.value})")
        self.inject_queue.add(node, message)
        self.inject_log.append("queued", node, message)
        self.state.save(self.run.state_file)

    # -- queries -----------------------------------------------------------

    def status_text(self) -> str:
        lines = [f"run {self.run.run_id} (pipeline: {self.cfg.name})"]
        if self.state.paused:
            lines.append("PAUSED — see failed nodes / waiting-human gates")
            lines.append(f"talk to the control agent: tmux attach-session -t {self.run.tmux_session_name}")
            lines.append(f"or intervene directly: flow status/retry/skip/inject {self.run.run_id}")
        for name in self.cfg.topological_order():
            st = self.state.node(name)
            cfg = self.cfg.nodes[name]
            needs = ",".join(cfg.needs) or "-"
            extra = f" error={st.error}" if st.error else ""
            queued = len(self.inject_queue.items.get(name, []))
            if queued:
                extra += f" queued={queued}"
            gate = " [gate]" if cfg.gate else ""
            lines.append(
                f"  {name:<20} {st.status.value:<14} needs={needs}{gate}{extra}"
            )
        return "\n".join(lines)
