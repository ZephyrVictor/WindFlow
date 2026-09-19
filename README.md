# flow — 轻量多 agent 编排系统

把 `claude` / `codex` CLI 子进程编排成声明式 DAG 流水线。每个 agent 是一个原生 CLI 会话，住在自己的 tmux window 里——随时 attach 进去对话、干预、纠偏。编排器不代理 API、不藏状态：它只管调度、审批、投递消息和持久化记忆。

## 核心特性

- **声明式 DAG**：一个 `flow.yaml` 描述节点、依赖（`needs`）、并行、人工审批（`gate`）、重试上限（`retry`）
- **原生 CLI agent**：节点 = tmux window 中的 claude/codex 子进程；完成检测靠 CLI hook 写 `done.flag`，不刮终端输出
- **人始终在环**：`gate` 节点完成后暂停等人 `flow approve`；节点失败默认暂停整个 run——无默认超时、重试 0，编排器不做静默自愈，决策留给人或 control agent
- **运行中干预**：`flow inject` 跨进程给运行中节点投递消息（持久化队列，编排进程重启不丢）；`flow attach` 直接进入节点对话
- **记忆系统**：run 私有 memory（context / findings / decisions / surface，按路径引用注入）+ 项目级 `agents/<name>/longterm.md` 作为跨 run 经验种子，随每个 run 快照进私有 memory
- **子流水线与动态 fan-out**：`flow run -f <yaml>` 从节点内拉起子 run（解析 run 内 pipeline.yaml 快照）；planner 类节点可按需 spawn 并行子流水线
- **自编排生态**：写侧命令（`flow validate` / `flow agent` / `flow init` / `flow clean`）+ 标准 flow skill——外层 agent 可以不经人手自主搭建、调整、干预流水线
- **control 常驻节点**：`control: true` 时拉起总控 agent，负责巡检与故障分析；配合项目侧 watchdog 脚本实现故障自愈（示例：[agent_example/iot_hunter/scripts/watchdog.sh](agent_example/iot_hunter/scripts/watchdog.sh)）

## 安装与启用

```bash
cd develop
python3 -m venv .venv && .venv/bin/pip install -e .   # flow CLI
cp -r skills/flow ~/.claude/skills/                   # 让任意 claude 会话学会编排 flow（agent 自编排，ADR-0007）
```

装好 skill 后，在任意 claude 会话里说"帮我编排一个 XX 流水线"，agent 会自主走 init → agent new → 写 yaml → validate → run。

## 快速开始

```bash
flow init demo && cd demo    # 脚手架：flow.yaml + agents/ 骨架
# 编辑 flow.yaml（DAG）与 agents/<name>/agent.md（角色契约）
flow validate                # yaml 校验
flow run                     # 起 run；tmux 会话名为 flow-<run-id>
flow status                  # 看节点状态机
flow attach                  # attach 进 tmux，一个节点一个 window
```

自定义 API 网关：启动前 export，driver 会转发给 agent 子进程（token 只进 shell env，不落文件）：

```bash
export ANTHROPIC_BASE_URL=... ANTHROPIC_AUTH_TOKEN=... ANTHROPIC_MODEL=...
flow run -p /path/to/project
```

## 命令一览

| 命令 | 作用 |
|---|---|
| `flow init` | 脚手架新项目 |
| `flow validate` | 校验 pipeline yaml |
| `flow run [-f YAML]` | 起 run（`-f` 指定非默认 yaml；子流水线模式） |
| `flow status [RUN_ID]` | 查看 run / 节点状态（多 run 并存时列出全部非终态候选） |
| `flow tree [-r RUN_ID]` | run 树视图：父子关系、tmux 会话探测、僵尸标记（ADR-0009） |
| `flow attach` | attach 到 run 的 tmux 会话 |
| `flow log [-f]` | 查看节点 tty.log（`-f` 持续跟随） |
| `flow approve` | 批准 waiting-human 的 gate 节点 |
| `flow inject` | 给运行中节点投递消息（queued/delivered 回执见 run 内 inject-log.jsonl） |
| `flow retry` / `flow skip` | 重置节点 / 放弃节点（下游 satisfied 放行，ADR-0008） |
| `flow edit <node> [--agent]` | 编辑节点 agent.md（run 内副本优先；`--agent` 编辑项目定义），改后 retry |
| `flow stop` / `flow resume` | 停止（杀 tmux、run 暂停）/ 恢复 |
| `flow agent` | 管理 agent 定义（new / list / show） |
| `flow clean` | 清理终态 run 的 tmux 会话（可选删旧 run） |

run 作用域子命令（status/approve/skip/retry/inject/log/edit/tree/attach/resume/stop）统一接受 `-r/--run RUN_ID` 与位置参数两种指定方式（二者冲突报错）。注意 argparse 限制：前导位置参数存在时，位置 run_id 须在选项之前（`flow approve n1 run-1 -p /x` 可以，`flow approve n1 -p /x run-1` 报错）——`-r` 任何位置都合法。`flow skip` 无 run_id 位置参数（reason 贪婪吞尾），指定 run 一律 `-r`。

## flow.yaml 示例

```yaml
name: my-pipeline
control: true            # 可选：拉起常驻 control agent

nodes:
  unpacker:
    agent: unpacker      # 引用 agents/unpacker/agent.md
    backend: claude      # 或 codex
    task: 解包固件并产出攻击面盘点
    gate: true           # 完成后暂停，等人 flow approve
    inject: [memory/context.md]

  auditor:
    agent: auditor
    needs: [unpacker]    # 依赖；无依赖关系的节点自动并行
    retry: 1
    inject:
      - memory/findings.md
      - agents/unpacker/summary.md
```

- `inject` 是路径引用清单（pull 模型）：prompt 只告诉 agent 去读哪些文件，不内联内容
- 节点状态机：`pending → running → (waiting-human | failed) → done`，另有 `skipped` 终态

## 目录布局

```
develop/
├── flow/                      引擎（orchestrator / driver / state / memory / cli / prompts / constants）
├── skills/flow/SKILL.md       标准 flow skill（改动后需重新拷贝到 ~/.claude/skills/flow/）
├── docs/                      architecture · development-plan · decisions（ADR）· discussions
├── agent_example/iot_hunter/  实战示例项目（固件审计流水线，三轮真机验收）
└── tests/                     pytest 单测
```

## 设计决策摘要

- 后端为 CLI 子进程（tmux 承载），不做 API 代理——会话可 attach、上下文可人工接管
- 失败暂停等人；gate 进 MVP；无默认超时；记忆注入用路径引用
- prompt 模板集中在 `prompts.py`，枚举集中在 `constants.py`，禁止散落硬编码
- agent 按 project 管理（`agents/<name>/`），无全局库；跨 run 经验走 `longterm.md` 人工晋升
- 完整决策记录与背景见 [docs/decisions.md](docs/decisions.md)、[docs/architecture.md](docs/architecture.md)

## 实战验证

引擎已通过 [agent_example/iot_hunter](agent_example/iot_hunter)（固件漏洞审计流水线）三轮真机验收：最新补验轮 13 节点（含并行子流水线）全链完成，累计产出 12 条执行级实证漏洞（含 sshd 认证绕过、dlopen root RCE 链闭环）+ 5 条静态重大发现；并行 DAG、gate 审批、inject 干预、watchdog 故障自愈（`--loop` 自守护）、longterm 经验复用均在生产 run 中生效。详见该示例的 README。

## 已知限制

- 对话框/粘贴片检测（classify_pane）是对 claude/codex TUI 渲染的启发式，CLI 版本升级可能失效——采取保守策略：识别不了就挂起消息并告警，绝不向对话框盲发，消息永不丢弃
- 历史子 run 的 state.json 无 `parent_run_id` 字段，`flow tree` 中显示为根 run（纯展示瑕疵，新 run 均已记录）
- inject-log.jsonl 回执是审计记录（queued/delivered 事件流），不是送达保证；投递失败靠队列重入队兜底
- CLI 进程与 orchestrator 并发读写 inject-queue.json 存在竞态（极端情况双发），flock 留待后续（ADR-0009 记录）
- `flow skip` 无 run_id 位置参数；argparse 限制前导位置参数后不能跟选项式位置参数（用 `-r` 规避，见命令一览）

## 开发

```bash
.venv/bin/python -m pytest    # 单测
```

开始开发前，请先阅读 [`.codex/agent.md`](./.codex/agent.md) 和 [`docs/README.md`](./docs/README.md)。项目架构、开发计划、决策和讨论记录统一维护在 [`docs/`](./docs/) 目录中。
