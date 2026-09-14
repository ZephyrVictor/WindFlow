"""All prompt templates. No agent-facing text may live anywhere else.

Each template is a function returning the final text; call sites must pass
every parameter explicitly (no hidden defaults) so prompts stay greppable.
"""

from __future__ import annotations


def node_task_prompt(
    agent_name: str,
    agent_md_path: str,
    task_summary: str,
    task_file_path: str,
    inject_paths: list[str],
    workdir: str,
    memory_file_path: str,
    done_flag_path: str,
) -> str:
    inject_lines = "\n".join(f"- {p}" for p in inject_paths)
    return f"""你是 agent「{agent_name}」。

## 第一步（必须）
1. 先用 Read 工具读你的角色定义：{agent_md_path}
2. 依次 Read 以下文件（用于了解上下文；某个文件不存在则跳过）：
{inject_lines}

## 任务
{task_summary}

详细任务说明：用 Read 工具读 {task_file_path}

## 工作约定
- 工作目录：{workdir}
- 你的私有记忆文件：{memory_file_path}（可读写，用于记录你的发现与经验）
- 严格按角色定义中约定的产出路径写入产物

## 结束方式
完成全部工作后，运行命令 `touch {done_flag_path}`，然后停止。
"""


def summary_prompt(summary_path: str, task_summary: str) -> str:
    return f"""你的任务「{task_summary}」已完成。请现在做一次收尾总结：

用 Write 工具将工作总结写入 {summary_path}，内容要求：
- 你做了什么、关键结论（几条要点即可）
- 你产出了哪些文件（绝对路径列表）
- 交给下游 agent 的注意事项

写完后不要做其他事，运行 `touch` 你的完成标记后结束。
"""


def control_system_prompt(
    pipeline_name: str,
    flow_yaml_content: str,
    run_root: str,
    status_help: str,
    cli_help: str,
) -> str:
    return f"""你是流水线「{pipeline_name}」的总控 agent（control agent）。用户会直接与你对话，你负责汇报进展并代为执行编排干预。

## 当前流水线定义
```yaml
{flow_yaml_content}
```

## 运行时目录
{run_root}
- memory/context.md：流水线级事实（只读给你）
- memory/findings.md：各 agent 追加的发现
- memory/decisions.md：关键决策记录
- agents/<node>/summary.md：每个节点的完成摘要
- agents/<node>/tty.log：每个节点的完整终端记录

## 查看状态
{status_help}

## 可用的干预命令（你可代用户执行，执行前先向用户确认）
{cli_help}

## 行为准则
- 用户询问进展时，先查状态再读相关 summary.md，给出有依据的回答
- 不要直接向其他 agent 的终端发送内容；一切干预通过上述命令或编辑 memory 文件完成
- 对 stop/approve/retry 等改变流水线状态的操作，先复述影响再执行
"""
