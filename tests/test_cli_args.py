"""CLI argument surface: every run-scoped subcommand accepts -p/-r/positional
in any order; skip's trailing run_id positional is gone (reason swallows it)."""

from __future__ import annotations

import pytest

from flow import cli as flow_cli


def parse(argv: list[str]):
    return flow_cli.build_parser().parse_args(argv)


class TestApprovePermutations:
    def test_positional_before_option(self):
        a = parse(["approve", "n1", "run-1", "-p", "/x"])
        assert a.run_id == "run-1"
        assert a.project == "/x"

    def test_run_flag_before_option(self):
        a = parse(["approve", "n1", "-r", "run-1", "-p", "/x"])
        assert a.run == "run-1"
        assert a.run_id is None

    def test_run_flag_after_option(self):
        # the universal form: -r works wherever options may appear
        a = parse(["approve", "n1", "-p", "/x", "-r", "run-1"])
        assert a.run == "run-1"
        assert a.project == "/x"

    def test_positional_after_option_unsupported(self):
        # argparse limitation: a trailing run_id positional cannot follow an
        # option when the command already consumed a leading positional.
        # -r above is the workaround; this pins the known behavior.
        with pytest.raises(SystemExit):
            parse(["approve", "n1", "-p", "/x", "run-1"])


class TestSkipShape:
    def test_reason_greedy_no_run_positional(self):
        # run_id positional removed: everything after node is reason
        a = parse(["skip", "n1", "bad", "env", "-r", "run-1", "-p", "/x"])
        assert a.reason == ["bad", "env"]
        assert a.run == "run-1"

    def test_plain_reason(self):
        a = parse(["skip", "n1", "not", "in", "scope"])
        assert a.reason == ["not", "in", "scope"]
        assert getattr(a, "run", None) is None

    def test_no_reason(self):
        a = parse(["skip", "n1"])
        assert a.reason == []


class TestOtherRunScopedCommands:
    # lone-positional commands accept the run id on either side of options
    @pytest.mark.parametrize("prefix", [["status"], ["resume"], ["stop"]])
    def test_single_positional_any_order(self, prefix):
        a = parse([*prefix, "-p", "/x", "run-1"])
        assert a.run_id == "run-1"
        a = parse([*prefix, "run-1", "-p", "/x"])
        assert a.run_id == "run-1"

    # node-prefixed commands: positional run id must precede options;
    # -r is the universal form
    @pytest.mark.parametrize(
        "prefix",
        [
            ["log", "n1"],
            ["retry", "n1"],
            ["inject", "n1", "msg"],
            ["edit", "n1"],
            ["attach", "n1"],
        ],
    )
    def test_node_commands(self, prefix):
        a = parse([*prefix, "run-1", "-p", "/x"])
        assert a.run_id == "run-1"
        a = parse([*prefix, "-p", "/x", "-r", "run-1"])
        assert a.run == "run-1"
        a = parse([*prefix, "-r", "run-1", "-p", "/x"])
        assert a.run == "run-1"

    def test_log_follow(self):
        a = parse(["log", "n1", "-f"])
        assert a.follow is True
        a = parse(["log", "n1"])
        assert a.follow is False

    def test_edit_agent_flag(self):
        a = parse(["edit", "n1", "--agent", "-r", "run-1"])
        assert a.agent is True

    def test_tree(self):
        a = parse(["tree", "-p", "/x"])
        assert a.run is None
        a = parse(["tree", "-p", "/x", "-r", "run-1"])
        assert a.run == "run-1"


class TestRunResolution:
    def _args(self, argv, run_id=None, run=None):
        a = parse(argv)
        if run_id is not None:
            a.run_id = run_id
        if run is not None:
            a.run = run
        return a

    def test_conflicting_ids_exit(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        a = self._args(["approve", "n1"], run_id="run-1", run="run-2")
        with pytest.raises(SystemExit):
            flow_cli._run(a)

    def test_agreeing_ids_ok(self, tmp_path):
        from flow import constants as C

        (tmp_path / C.PIPELINE_FILE).write_text("name: t\nnodes: {}\n")
        (tmp_path / C.RUNS_DIR / "run-1").mkdir(parents=True)
        a = self._args(
            ["approve", "n1", "-p", str(tmp_path)], run_id="run-1", run="run-1"
        )
        run = flow_cli._run(a)
        assert run.run_id == "run-1"
