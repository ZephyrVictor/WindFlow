# 当前架构

> 状态：架构已定稿（阶段一开发前）
>
> 最后更新：2026-09-14

## 1. 目标与范围

- 项目目标：`flow`——轻量级多 agent 编排系统，将 Claude Code CLI 与 Codex CLI 作为后端 agent，按声明式 DAG 编排任意流水线，全程对话可查看、可交互。
- 服务对象：本机单用户（研究者/开发者），本地运行，无多租户/服务化需求。
- 当前阶段：阶段一（核心引擎 + Control Agent）开发前，见 [development-plan.md](./development-plan.md)。
- 本文档范围：只记录已经确认的当前架构，不记录未经验证的设想。

## 2. 架构总览

```
用户 ↔ control agent（tmux window，常驻对话节点，指挥编排）
        │  仅通过 flow CLI 与 memory 文件干预
        ▼
flow 编排器（Python 薄层：DAG 调度 / 状态机 / 超时 / 落盘）
        │ tmux 驱动（send-keys 投递，done.flag 检测完成）
        ▼
tmux session flow-<run-id>（window: control + 每节点一 window，可 attach/detach）
        │
        ├── claude CLI 子进程（后端 agent，带自身记忆/skills/hooks）
        └── codex CLI 子进程（后端 agent，带自身记忆/AGENTS.md）
```

关键原则：**不做 LLM API 代理**——编排器只负责确定性的调度与状态，智能全部在 CLI agent 内。完成检测依赖 hook（`Stop` hook / codex `notify`）落 `done.flag`，不解析终端输出。

## 3. 一级模块

| 模块 | 职责 |
| --- | --- |
| 驱动层 | tmux 生命周期管理、prompt 投递、done.flag 检测、tty.log 落盘（pipe-pane）、session id 记录 |
| 编排层 | flow.yaml 解析与 DAG 校验、依赖调度、state.json 状态机、超时/重试/gate/resume |
| memory 层 | 目录约定（agent 库 / 项目 / run 三层）、注入（路径引用）、summary 驱动 |
| 交互层 | session/window 布局、attach 状态管理（交互中暂缓投递）、`flow` CLI |
| control agent | 常驻节点：人机总对话入口，经 flow CLI 与 memory 文件干预编排 |

## 4. 数据流与状态边界

- 节点状态机：`pending → running → (waiting-human | failed) → done`；失败默认暂停整条流水线等人。
- 上下文传递：节点完成 → 编排器驱动写 `summary.md` → 下游节点 prompt 注入上游 summary 与共享 memory 的**路径**（agent 自行 Read）。
- 持久化全部为文件（markdown + state.json），无数据库；git 可对 runs/ 做版本回溯。

## 5. 目录结构（已确认，2026-09-14 实现期修订：project 自包含）

Project = 任意含 flow.yaml 的目录（无系统根目录）；agent 定义按 project 管理。

```
<project>/                       # 本仓库 develop/ 即一个 flow 项目
├── flow.yaml                    # DAG：节点引用 agents/ 下名字，needs 依赖，节点级覆盖（env/gate/timeout/retry/inject）
├── agents/<name>/               # agent 定义：agent.md（+ longterm.md、skills/，可选）
├── workdir/                     # 共享工作区（跨 run 持久）
└── runs/<run-id>/
    ├── memory/                  # context(只读) / findings(追加式) / decisions
    ├── agents/<node>/           # agent.md 快照、task.md、memory.md、summary.md、tty.log、done.flag、后端配置
    ├── artifacts/
    ├── state.json
    ├── pipeline.yaml                # 生效 pipeline 快照（-f 子流水线时与项目默认不同）
    ├── plan/                        # （子流水线模式）planner 生成的 skills/ 与子 flow.yaml
    └── .tmux.conf
```

代码模块（`flow/` 包）：constants（全部枚举/字面量）、paths（目录约定；find_project_root 跳过 runs/ 内的 flow.yaml）、config（yaml+DAG 校验）、state（状态机）、session（tmux 封装+attach 锁）、driver（claude/codex 启动/投递/完成检测；classify_pane pane 分诊 + 提交确认）、memory（初始化+prompt 组装）、prompts（全部模板，禁止散落硬编码）、orchestrator（调度循环；inject 投递门控与回执）、runs（跨 run 查询：扫描/父子关系/树视图）、control（总控节点）、cli（命令组：run(-f)/status/attach/log(-f)/resume/stop/approve/retry/skip/inject/tree/edit/validate/agent/init/clean；run 作用域命令统一接受 `-r/--run`，status/approve/retry/skip 优先按 run 内 pipeline.yaml 解析）。

节点状态机含 `skipped` 终态（ADR-0008）：上游 failed/waiting-human 时人工 `flow skip` 放弃该节点，下游视同 done 放行（inject 的 summary.md 缺失时按约定跳过）；暂停时 status 输出 control session 的 tmux attach 指令。

动态 fan-out（子流水线模式，ADR-0006）：运行时节点数由 agent 生成的静态子 flow.yaml 表达——`flow run -f <父run>/plan/flow.yaml`，子 run 与父 run 各自独立 tmux session，子节点 inject 绝对路径共享父 run memory。子 run 的 state.json 记录 `parent_run_id`（driver 注入 `FLOW_RUN_ID` env、cmd_run 读取，ADR-0009）；`latest_run_id` 只在根 run 里挑最新，`flow tree` 按 parent 关系渲染树并标记僵尸 run（state 非终态但 tmux 会话已消失）。

## 6. 运行与开发方式

- 语言/运行时：Python 3（tmux 经 libtmux 或直接 CLI 调用）。
- 本地开发，无部署/CI 约束（阶段一）。
- 外部依赖：tmux、claude CLI、codex CLI（可用性在 M1 真机验证）。

## 7. 当前约束与风险

- claude `Stop` hook / codex `notify` 可靠性未真机验证；降级方案：prompt 要求 agent 自行 touch flag。
- codex TUI 与 send-keys 的兼容性需实测。
- 并行节点共享 workdir，无工作区隔离（阶段一验收用例中并行节点只读上游、写各自目录）。

## 8. 待确认问题

- [ ] （阶段二）Web UI 桥接选型：tmux control mode vs 自写 WebSocket 桥
- [ ] （阶段二）agent 库 longterm.md 的注入时机与上限

## 9. 更新规则

架构讨论达成结论后，先在 [`decisions.md`](./decisions.md) 记录取舍，再将“当前有效状态”同步到本文档。若实现发现架构与实际不符，应在同一变更中修订本文档或代码。
