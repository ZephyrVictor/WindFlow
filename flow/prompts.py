"""All prompt templates. No agent-facing text may live anywhere else.

Each template is a function returning the final text; call sites must pass
every parameter explicitly (no hidden defaults) so prompts stay greppable.
"""

from __future__ import annotations


def agent_md_template(agent_name: str) -> str:
    return f"""# {agent_name} — <一句话角色定位>

## 角色
<你是谁、擅长什么、本流水线里承担什么职责。写具体，不写空话。>

## 工作方式
<按步骤写：1. 读什么输入（含路径约定）；2. 怎么处理；3. 产出写到哪（绝对路径）。
产出文件名与路径必须明确到可以直接引用。>

## 共享记忆约定
<追加 `runs/<run-id>/memory/findings.md`（追加式，署名 {agent_name}，不改他人条目）。
如适用，说明条目标记约定（如 [major]/[minor]/[chain]）。不适用则删除本节。>

## 约束
<边界与纪律：只做什么不做什么、证据标准（如"结论必须可复核，写函数名/地址"）、
产出路径一律写绝对路径。>
"""


INIT_FLOW_YAML_TEMPLATE = """# flow.yaml — 两节点串行骨架（编辑后运行 `flow validate` 校验）
# 1. 先 `flow agent new <name>` 创建引用的 agent 定义
# 2. 取消注释并按需修改节点
# 3. `flow validate` 通过后 `flow run` 启动
name: my-pipeline
control: true

# nodes:
#   first:
#     agent: <agent-name>        # 必须存在于 agents/<agent-name>/agent.md
#     backend: claude            # claude | codex
#     task: <一句话任务描述>
#     inject: [memory/context.md]
#     gate: false                # true = 完成后人工放行
#
#   second:
#     agent: <agent-name>
#     backend: claude
#     task: <一句话任务描述>
#     needs: [first]             # 依赖：first 完成后才启动
#     inject: [memory/context.md, memory/findings.md, agents/first/summary.md]
"""

INIT_GITIGNORE = """runs/
workdir/*
!workdir/.gitkeep
"""


def init_next_steps(project_dir: str) -> str:
    return f"""项目骨架已生成：{project_dir}（含 control agent 定义）

下一步：
1. flow agent new <name>       # 创建 agent 定义（四段式模板）
2. 编辑 flow.yaml              # 取消注释、填节点
3. flow validate               # 校验通过再启动
4. flow run                    # 启动（tmux session flow-<run-id>）
"""


CONTROL_AGENT_MD = """# control agent（项目级角色定义）

你是流水线总控 agent。具体的系统提示（流水线定义、运行时目录、可用命令）会追加在本文末尾。
"""


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
