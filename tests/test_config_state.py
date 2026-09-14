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
