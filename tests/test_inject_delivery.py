"""classify_pane heuristics, summarize-phase delivery gating, inject receipts,
re-queue on delivery failure, summary-prompt hardening."""

from __future__ import annotations

from pathlib import Path

import pytest

from flow import constants as C
from flow.constants import DialogState, NodeStatus
from flow.driver import classify_pane
from flow.orchestrator import InjectLog, InjectQueue, Orchestrator
from flow.prompts import summary_prompt
from flow.state import RunState


class TestClassifyPane:
    def test_empty(self):
        assert classify_pane("") is DialogState.UNKNOWN
        assert classify_pane("\n\n  \n") is DialogState.UNKNOWN

    def test_ready_claude(self):
        pane = "some output line\n\n❯"
        assert classify_pane(pane) is DialogState.READY

    def test_ready_codex(self):
        pane = "working...\n\n›"
        assert classify_pane(pane) is DialogState.READY

    def test_paste_chip_not_submitted(self):
        # chip sitting on the input line — the run-20260918-011428 incident
        pane = "output\n\n❯ [Pasted text #1 +23 lines]"
        assert classify_pane(pane) is DialogState.NOT_SUBMITTED

    def test_paste_chip_in_transcript_is_ready(self):
        # a *submitted* paste lives higher up; input line below is empty
        pane = "[Pasted text #1 +23 lines]\nassistant reply...\n\n❯"
        assert classify_pane(pane) is DialogState.READY

    def test_dialog_marker(self):
        pane = "question?\n\n  Choose an option:\n  ❯ 1. yes\n    2. no"
        assert classify_pane(pane) is DialogState.DIALOG

    def test_dialog_numbered_options_without_marker(self):
        pane = "Which backend?\n\n  1. claude\n  2. codex\n  3. other"
        assert classify_pane(pane) is DialogState.DIALOG

    def test_numbered_options_with_input_line_is_ready(self):
        # agent printed a numbered list but the input box is rendered
        pane = "steps:\n  1. do this\n  2. then that\n\ndone.\n\n❯"
        assert classify_pane(pane) is DialogState.READY

    def test_ambiguous_is_unknown(self):
        assert classify_pane("busy streaming output...\nstill going") is DialogState.UNKNOWN


def summary_lines(pane):
    return pane


class TestSummaryPromptHardening:
    def test_no_questions_directive(self):
        p = summary_prompt("/tmp/summary.md", "audit things")
        assert "不要提问" in p
        assert "合理假设" in p


class TestInjectLog:
    def test_append_and_replay_fifo(self, tmp_path: Path):
        log = InjectLog(tmp_path / "inject-log.jsonl")
        log.append("queued", "n1", "hello")
        log.append("delivered", "n1", "hello")
        log.append("queued", "n2", "second")
        recs = log.replay()
        assert [r["event"] for r in recs] == ["queued", "delivered", "queued"]
        assert recs[0]["node"] == "n1"
        assert recs[0]["message"] == "hello"
        assert recs[1]["message"] == "hello"

    def test_replay_empty_or_missing(self, tmp_path: Path):
        assert InjectLog(tmp_path / "nope.jsonl").replay() == []
        f = tmp_path / "log.jsonl"
        f.write_text('{"event": "queued"}\n{"event": "deliv')  # torn tail
        recs = InjectLog(f).replay()
        assert [r["event"] for r in recs] == ["queued"]

    def test_unicode_message(self, tmp_path: Path):
        log = InjectLog(tmp_path / "log.jsonl")
        log.append("queued", "n1", "巡检提示：继续任务")
        assert log.replay()[0]["message"] == "巡检提示：继续任务"


@pytest.fixture
def orch(tmp_path: Path, monkeypatch) -> Orchestrator:
    """A minimal orchestrator around a single-node pipeline, with the
    driver and tmux fully stubbed."""
    from flow.config import NodeConfig, PipelineConfig
    from flow.driver import BackendDriver
    from flow.paths import ProjectPaths, RunPaths

    (tmp_path / C.AGENTS_DIR / "a1").mkdir(parents=True)
    (tmp_path / C.AGENTS_DIR / "a1" / C.AGENT_MD).write_text("role")
    (tmp_path / C.WORKDIR_NAME).mkdir()
    cfg = PipelineConfig(
        name="t",
        control=False,
        nodes={"n1": NodeConfig(name="n1", agent="a1", backend=C.Backend.CLAUDE, task="x")},
    )
    project = ProjectPaths(tmp_path)
    run = RunPaths(project, "r1")
    run.create()
    state = RunState(pipeline="t", run_id="r1")
    state.set_status("n1", NodeStatus.RUNNING)
    state.save(run.state_file)

    sent: list[tuple[str, str]] = []
    fail_next = {"flag": False, "error": None}

    class FakeDriver(BackendDriver):
        def send_prompt(self, node, text):
            if fail_next["flag"]:
                raise fail_next["error"]
            sent.append((node, text))

    driver = FakeDriver(project, run, {})
    o = Orchestrator(project, run, cfg, state, driver)
    o._sent = sent
    o._fail_next = fail_next
    return o


class TestDeliveryGating:
    def test_summarizing_ready_delivers(self, orch: Orchestrator, monkeypatch):
        orch._summarizing.add("n1")
        monkeypatch.setattr(
            Orchestrator, "_classify_node",
            lambda self, name: DialogState.READY,
        )
        orch.inject("n1", "wake up")
        orch._deliver_injects()
        assert orch._sent == [("n1", "wake up")]
        assert orch.inject_queue.items.get("n1", []) == []
        assert orch.inject_log.replay()[-1]["event"] == "delivered"

    def test_summarizing_dialog_holds(self, orch: Orchestrator, monkeypatch):
        orch._summarizing.add("n1")
        monkeypatch.setattr(
            Orchestrator, "_classify_node",
            lambda self, name: DialogState.DIALOG,
        )
        orch.inject("n1", "wake up")
        orch._deliver_injects()
        assert orch._sent == []
        assert orch.inject_queue.items["n1"] == ["wake up"]  # held, not dropped

    def test_summarizing_unknown_holds(self, orch: Orchestrator, monkeypatch):
        orch._summarizing.add("n1")
        monkeypatch.setattr(
            Orchestrator, "_classify_node",
            lambda self, name: DialogState.UNKNOWN,
        )
        orch.inject("n1", "m")
        orch._deliver_injects()
        assert orch._sent == []

    def test_non_summarizing_not_gated(self, orch: Orchestrator, monkeypatch):
        called = {"n": 0}

        def _classify(self, name):
            called["n"] += 1
            return DialogState.DIALOG

        monkeypatch.setattr(Orchestrator, "_classify_node", _classify)
        orch.inject("n1", "go")
        orch._deliver_injects()
        assert orch._sent == [("n1", "go")]
        assert called["n"] == 0  # classification never consulted

    def test_held_warning_rate_limited(self, orch: Orchestrator, monkeypatch, capsys):
        from flow import orchestrator as orch_mod

        orch._summarizing.add("n1")
        monkeypatch.setattr(
            Orchestrator, "_classify_node",
            lambda self, name: DialogState.DIALOG,
        )
        orch.inject("n1", "m")
        for _ in range(3):
            orch._deliver_injects()
        out = capsys.readouterr().out
        assert out.count("held") == 1  # repeated ticks stay quiet
        # force the rate limit window to expire
        monkeypatch.setattr(orch_mod.time, "monotonic", lambda: 1e12)
        orch._deliver_injects()
        assert capsys.readouterr().out.count("held") == 1

    def test_delivery_failure_requeues(self, orch: Orchestrator, capsys):
        from flow.driver import DriverError

        orch._fail_next["flag"] = True
        orch._fail_next["error"] = DriverError("boom")
        orch.inject("n1", "first")
        orch.inject("n1", "second")
        orch._deliver_injects()
        assert orch._sent == []  # first send raised; nothing left the queue
        assert orch.inject_queue.items["n1"] == ["first", "second"]
        assert "re-queued" in capsys.readouterr().out
        # driver recovers -> everything goes out in order
        orch._fail_next["flag"] = False
        orch._deliver_injects()
        assert orch._sent == [("n1", "first"), ("n1", "second")]
        assert orch.inject_queue.items.get("n1", []) == []

    def test_status_shows_queued(self, orch: Orchestrator):
        orch.inject("n1", "pending msg")
        text = orch.status_text()
        assert "queued=1" in text
        orch._deliver_injects()
        assert "queued=" not in orch.status_text()


class TestInjectQueueCompat:
    def test_queue_file_format_unchanged(self, tmp_path: Path):
        q = InjectQueue(tmp_path / "inject-queue.json")
        q.add("n1", "a")
        q.add("n1", "b")
        import json

        on_disk = json.loads((tmp_path / "inject-queue.json").read_text())
        assert on_disk == {"n1": ["a", "b"]}
