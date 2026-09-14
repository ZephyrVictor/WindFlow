"""Shared memory initialization, task files, and prompt assembly."""

from __future__ import annotations

from pathlib import Path

from flow import constants as C
from flow import prompts
from flow.config import NodeConfig, PipelineConfig
from flow.paths import ProjectPaths, RunPaths

CONTEXT_HEADER = """# 流水线上下文（只读）

> 此文件描述本次 run 的整体目标，由编排器生成。各 agent 只读。

"""
FINDINGS_HEADER = """# 发现记录（追加式）

> 规则：各 agent 只允许在文件末尾**追加**自己的条目，格式如下，不允许修改或删除他人条目：

## [节点名] YYYY-MM-DD HH:MM
- 发现/结论

"""
DECISIONS_HEADER = """# 决策记录

> 记录关键决策及其原因。人工干预后的决策也记在这里。

"""


def init_shared_memory(run: RunPaths, cfg: PipelineConfig) -> None:
    run.memory_dir.mkdir(parents=True, exist_ok=True)
    (run.memory_dir / C.MEM_CONTEXT).write_text(
        CONTEXT_HEADER
        + f"- 流水线：{cfg.name}\n- run：{run.run_id}\n\n## 节点概览\n"
        + "\n".join(f"- {n}: {c.task}" for n, c in cfg.nodes.items())
        + "\n"
    )
    (run.memory_dir / C.MEM_FINDINGS).write_text(FINDINGS_HEADER)
    (run.memory_dir / C.MEM_DECISIONS).write_text(DECISIONS_HEADER)


def prepare_node_files(
    run: RunPaths, project: ProjectPaths, cfg: NodeConfig
) -> None:
    """Snapshot agent.md, write task.md and private memory.md for a node."""
    ndir = run.node_dir(cfg.name)
    ndir.mkdir(parents=True, exist_ok=True)
    src = project.agent_def_dir(cfg.agent) / C.AGENT_MD
    dst = run.node_agent_md(cfg.name)
    if not dst.exists():
        dst.write_text(src.read_text())
    task = run.node_task_file(cfg.name)
    if not task.exists():
        task.write_text(f"# 任务：{cfg.name}\n\n{cfg.task}\n")
    mem = run.node_memory_file(cfg.name)
    if not mem.exists():
        longterm = project.agent_def_dir(cfg.agent) / "longterm.md"
        base = longterm.read_text() if longterm.is_file() else ""
        mem.write_text(f"# {cfg.name} 私有记忆\n\n{base}")


def build_task_prompt(
    run: RunPaths, project: ProjectPaths, cfg: NodeConfig
) -> str:
    inject_paths = [
        str(run.root / p) if not Path(p).is_absolute() else p for p in cfg.inject
    ]
    return prompts.node_task_prompt(
        agent_name=cfg.agent,
        agent_md_path=str(run.node_agent_md(cfg.name)),
        task_summary=cfg.task,
        task_file_path=str(run.node_task_file(cfg.name)),
        inject_paths=inject_paths,
        workdir=str(project.workdir),
        memory_file_path=str(run.node_memory_file(cfg.name)),
        done_flag_path=str(run.node_done_flag(cfg.name)),
    )


def build_summary_prompt(run: RunPaths, cfg: NodeConfig) -> str:
    return prompts.summary_prompt(
        summary_path=str(run.node_summary_file(cfg.name)),
        task_summary=cfg.task,
    )
