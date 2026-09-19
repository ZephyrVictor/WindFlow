"""parent_run_id tracking, latest_run_id root preference, run tree rendering."""

from __future__ import annotations

from pathlib import Path

from flow import constants as C
from flow.constants import NodeStatus
from flow.paths import ProjectPaths, latest_run_id
from flow.runs import RunSummary, children_map, non_terminal_run_ids, render_run_tree, scan_runs
from flow.state import RunState


def make_run(project: Path, run_id: str, statuses: dict[str, NodeStatus], parent=None, paused=False):
    st = RunState(pipeline=f"pipe-{run_id}", run_id=run_id, parent_run_id=parent, paused=paused)
    for n, s in statuses.items():
        st.set_status(n, s)
    d = project / C.RUNS_DIR / run_id
    d.mkdir(parents=True)
    st.save(d / C.STATE_FILE)
    return d


class TestParentRunIdRoundtrip:
    def test_default_none(self, tmp_path: Path):
        st = RunState(pipeline="t", run_id="r1")
        f = tmp_path / "state.json"
        st.save(f)
        assert RunState.load(f).parent_run_id is None

    def test_set_and_load(self, tmp_path: Path):
        st = RunState(pipeline="t", run_id="r2", parent_run_id="r1")
        f = tmp_path / "state.json"
        st.save(f)
        loaded = RunState.load(f)
        assert loaded.parent_run_id == "r1"

    def test_old_state_without_field(self, tmp_path: Path):
        import json

        f = tmp_path / "state.json"
        f.write_text(json.dumps({"pipeline": "t", "run_id": "r1", "paused": False, "nodes": {}}))
        assert RunState.load(f).parent_run_id is None


class TestLatestRunIdRootPreference:
    def test_sub_run_does_not_steal(self, tmp_path: Path):
        make_run(tmp_path, "20260918-010000", {"n1": NodeStatus.DONE})
        # sub-run spawned later: sorts after the root
        make_run(tmp_path, "20260918-020000", {"s1": NodeStatus.RUNNING}, parent="20260918-010000")
        project = ProjectPaths(tmp_path)
        assert latest_run_id(project) == "20260918-010000"

    def test_two_roots_picks_newest(self, tmp_path: Path):
        make_run(tmp_path, "a-1", {"n1": NodeStatus.DONE})
        make_run(tmp_path, "b-2", {"n1": NodeStatus.RUNNING})
        assert latest_run_id(ProjectPaths(tmp_path)) == "b-2"

    def test_only_sub_runs_falls_back_to_newest(self, tmp_path: Path):
        make_run(tmp_path, "s-2", {"s1": NodeStatus.DONE}, parent="deleted-run")
        assert latest_run_id(ProjectPaths(tmp_path)) == "s-2"

    def test_no_runs(self, tmp_path: Path):
        assert latest_run_id(ProjectPaths(tmp_path)) is None

    def test_pre_parent_field_runs_count_as_roots(self, tmp_path: Path):
        import json

        # old-format state without parent_run_id
        d = tmp_path / C.RUNS_DIR / "legacy-1"
        d.mkdir(parents=True)
        (d / C.STATE_FILE).write_text(json.dumps({
            "pipeline": "t", "run_id": "legacy-1", "paused": False, "nodes": {}
        }))
        make_run(tmp_path, "new-sub", {"s1": NodeStatus.DONE}, parent="legacy-1")
        assert latest_run_id(ProjectPaths(tmp_path)) == "legacy-1"


def summary(run_id, parent=None, statuses=None, paused=False) -> RunSummary:
    return RunSummary(
        run_id=run_id,
        project=None,  # not used by children_map/non_terminal
        pipeline_name=f"pipe-{run_id}",
        paused=paused,
        parent_run_id=parent,
        node_statuses=statuses or {},
    )


class TestChildrenMap:
    def test_roots_and_children(self):
        root = summary("root")
        kid = summary("kid", parent="root")
        grandkid = summary("gk", parent="kid")
        cm = children_map([root, kid, grandkid])
        assert cm[None] == [root]
        assert cm["root"] == [kid]
        assert cm["kid"] == [grandkid]

    def test_dangling_parent_surfaces_as_root(self):
        orphan = summary("orphan", parent="gone")
        cm = children_map([orphan])
        assert cm[None] == [orphan]


class TestScanRuns:
    def test_scan_and_terminal(self, tmp_path: Path):
        make_run(tmp_path, "r-done", {"n1": NodeStatus.DONE})
        make_run(tmp_path, "r-live", {"n1": NodeStatus.RUNNING})
        make_run(tmp_path, "r-child", {"s1": NodeStatus.DONE}, parent="r-live")
        # dir without state.json ignored
        (tmp_path / C.RUNS_DIR / "junk").mkdir()
        runs = scan_runs(ProjectPaths(tmp_path))
        assert [r.run_id for r in runs] == ["r-child", "r-done", "r-live"]
        by_id = {r.run_id: r for r in runs}
        assert by_id["r-done"].terminal is True
        assert by_id["r-live"].terminal is False
        assert by_id["r-live"].running_count == 1
        assert by_id["r-child"].parent_run_id == "r-live"
        assert non_terminal_run_ids(runs) == ["r-live"]


class TestRenderTree:
    def test_tree_shape_and_marks(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("flow.runs.tmux.has_session", lambda name: False)
        make_run(tmp_path, "main", {"n1": NodeStatus.RUNNING})
        make_run(tmp_path, "sub", {"s1": NodeStatus.DONE}, parent="main")
        runs = scan_runs(ProjectPaths(tmp_path))
        text = render_run_tree(runs)
        assert "main" in text and "sub" in text
        assert "└─" in text
        # non-terminal + session gone + not paused -> MISSING zombie mark
        assert "MISSING(zombie)" in text
        # terminal + session gone -> plain gone
        assert "tmux=gone" in text

    def test_alive_session_windows(self, tmp_path: Path, monkeypatch):
        make_run(tmp_path, "main", {"n1": NodeStatus.RUNNING})
        monkeypatch.setattr("flow.runs.tmux.has_session", lambda name: True)
        monkeypatch.setattr(
            "flow.runs.tmux.list_window_names",
            lambda session: ["00-n1", "01-n2"],
        )
        runs = scan_runs(ProjectPaths(tmp_path))
        text = render_run_tree(runs)
        assert "tmux=alive" in text
        assert "00-n1" in text
        assert "running=1" in text

    def test_no_runs(self):
        assert render_run_tree([]) == "no runs found"
