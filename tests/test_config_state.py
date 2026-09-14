from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from flow import constants as C
from flow.config import ConfigError, load_config
from flow.constants import NodeStatus
from flow.state import RunState


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / C.AGENTS_DIR / "a1").mkdir(parents=True)
    (tmp_path / C.AGENTS_DIR / "a1" / C.AGENT_MD).write_text("role a1")
    (tmp_path / C.AGENTS_DIR / "a2").mkdir(parents=True)
    (tmp_path / C.AGENTS_DIR / "a2" / C.AGENT_MD).write_text("role a2")
    (tmp_path / C.WORKDIR_NAME).mkdir()
    return tmp_path


def write_pipeline(project: Path, body: str) -> Path:
    f = project / C.PIPELINE_FILE
    f.write_text(textwrap.dedent(body))
    return f


class TestLoadConfig:
    def test_minimal_valid(self, project: Path):
        f = write_pipeline(
            project,
            """
            name: t
            nodes:
              n1:
                agent: a1
                backend: claude
                task: do it
            """,
        )
        cfg = load_config(f)
        assert cfg.name == "t"
        assert list(cfg.nodes) == ["n1"]
        assert cfg.nodes["n1"].needs == []
        assert cfg.nodes["n1"].gate is False
        assert cfg.nodes["n1"].timeout is None
        assert cfg.nodes["n1"].retry == 0

    def test_defaults_and_overrides(self, project: Path):
        f = write_pipeline(
            project,
            """
            name: t
            nodes:
              n1:
                agent: a1
                backend: claude
                task: first
              n2:
                agent: a2
                backend: codex
                task: second
                needs: [n1]
                gate: true
                timeout: 600
                retry: 2
                inject: [memory/context.md]
            """,
        )
        cfg = load_config(f)
        assert cfg.nodes["n2"].needs == ["n1"]
        assert cfg.nodes["n2"].gate is True
        assert cfg.nodes["n2"].timeout == 600
        assert cfg.nodes["n2"].retry == 2
        assert cfg.nodes["n2"].inject == ["memory/context.md"]

    def test_unknown_agent(self, project: Path):
        f = write_pipeline(
            project,
            """
            name: t
            nodes:
              n1:
                agent: ghost
                backend: claude
                task: x
            """,
        )
        with pytest.raises(ConfigError, match="agent `ghost` not found"):
            load_config(f)

    def test_bad_backend(self, project: Path):
        f = write_pipeline(
            project,
            """
            name: t
            nodes:
              n1:
                agent: a1
                backend: gemini
                task: x
            """,
        )
        with pytest.raises(ConfigError, match="invalid backend"):
            load_config(f)

    def test_unknown_need(self, project: Path):
        f = write_pipeline(
            project,
            """
            name: t
            nodes:
              n1:
                agent: a1
                backend: claude
                task: x
                needs: [missing]
            """,
        )
        with pytest.raises(ConfigError, match="unknown node `missing`"):
            load_config(f)

    def test_cycle_detected(self, project: Path):
        f = write_pipeline(
            project,
            """
            name: t
            nodes:
              n1: {agent: a1, backend: claude, task: x, needs: [n2]}
              n2: {agent: a2, backend: claude, task: y, needs: [n1]}
            """,
        )
        with pytest.raises(ConfigError, match="cycle"):
            load_config(f)

    def test_reserved_node_name(self, project: Path):
        f = write_pipeline(
            project,
            f"""
            name: t
            nodes:
              {C.CONTROL_NODE}:
                agent: a1
                backend: claude
                task: x
            """,
        )
        with pytest.raises(ConfigError, match="reserved"):
            load_config(f)

    def test_topological_order(self, project: Path):
        f = write_pipeline(
            project,
            """
            name: t
            nodes:
              final: {agent: a2, backend: claude, task: f, needs: [mid1, mid2]}
              mid1: {agent: a1, backend: claude, task: m1, needs: [first]}
              mid2: {agent: a1, backend: claude, task: m2, needs: [first]}
              first: {agent: a1, backend: claude, task: s}
            """,
        )
        cfg = load_config(f)
        order = cfg.topological_order()
        assert order.index("first") < order.index("mid1")
        assert order.index("first") < order.index("mid2")
        assert order.index("mid1") < order.index("final")
        assert order.index("mid2") < order.index("final")


class TestRunState:
    def test_roundtrip(self, tmp_path: Path):
        st = RunState(pipeline="t", run_id="r1")
        st.set_status("n1", NodeStatus.RUNNING)
        st.set_status("n1", NodeStatus.DONE)
        f = tmp_path / "state.json"
        st.save(f)
        loaded = RunState.load(f)
        assert loaded.pipeline == "t"
        assert loaded.node("n1").status is NodeStatus.DONE
        assert loaded.node("n1").attempts == 1
        assert loaded.node("n1").finished_at is not None

    def test_reset_on_running(self, tmp_path: Path):
        st = RunState(pipeline="t", run_id="r1")
        st.node("n1").error = "boom"
        st.set_status("n1", NodeStatus.RUNNING)
        assert st.node("n1").error is None
        assert st.node("n1").attempts == 1
        st.set_status("n1", NodeStatus.RUNNING)
        assert st.node("n1").attempts == 2


class TestPipelineFileResolution:
    def test_run_local_snapshot_preferred(self, tmp_path: Path):
        from flow.cli import _pipeline_file
        from flow.paths import ProjectPaths, RunPaths

        project = ProjectPaths(tmp_path)
        run = RunPaths(project, "r1")
        run.create()
        assert _pipeline_file(run) == project.pipeline_file
        run.pipeline_file.write_text("snapshot")
        assert _pipeline_file(run) == run.pipeline_file
        override = tmp_path / "other.yaml"
        assert _pipeline_file(run, override) == override

    def test_load_config_from_sub_run_dir_finds_project_root(
        self, project: Path
    ):
        write_pipeline(project, "name: root\nnodes: {}")
        sub = project / C.RUNS_DIR / "r1" / "plan"
        sub.mkdir(parents=True)
        f = sub / C.PIPELINE_FILE
        f.write_text(
            textwrap.dedent(
                """
                name: sub
                nodes:
                  s1:
                    agent: a1
                    backend: claude
                    task: sub task
                """
            )
        )
        cfg = load_config(f)
        assert cfg.name == "sub"
        assert list(cfg.nodes) == ["s1"]


class TestScaffoldCommands:
    def test_init_creates_skeleton(self, tmp_path: Path, capsys):
        from flow import cli as flow_cli

        target = tmp_path / "proj"
        args = flow_cli.build_parser().parse_args(["init", str(target)])
        args.func(args)
        assert (target / C.PIPELINE_FILE).is_file()
        assert (target / C.AGENTS_DIR).is_dir()
        assert (target / C.WORKDIR_NAME / ".gitkeep").is_file()
        assert "runs/" in (target / ".gitignore").read_text()
        # init twice refuses to overwrite
        import pytest as _pytest

        with _pytest.raises(SystemExit):
            args.func(args)

    def test_agent_new_and_list(self, tmp_path: Path, capsys):
        from flow import cli as flow_cli

        proj = tmp_path / "proj"
        flow_cli.build_parser().parse_args(["init", str(proj)]).func(
            flow_cli.build_parser().parse_args(["init", str(proj)])
        )
        a = flow_cli.build_parser().parse_args(
            ["agent", "new", "worker", "-p", str(proj)]
        )
        a.func(a)
        md = proj / C.AGENTS_DIR / "worker" / C.AGENT_MD
        assert md.is_file()
        assert "## 角色" in md.read_text()
        # duplicate new refuses
        with pytest.raises(SystemExit):
            a.func(a)

    def test_validate_reports_nodes(self, project: Path, capsys):
        from flow import cli as flow_cli

        write_pipeline(
            project,
            """
            name: t
            nodes:
              n1: {agent: a1, backend: claude, task: x}
              n2: {agent: a2, backend: claude, task: y, needs: [n1], gate: true}
            """,
        )
        args = flow_cli.build_parser().parse_args(["validate", str(project / C.PIPELINE_FILE)])
        args.func(args)
        out = capsys.readouterr().out
        assert "valid: t (2 nodes)" in out
        assert "needs=n1 [gate]" in out
