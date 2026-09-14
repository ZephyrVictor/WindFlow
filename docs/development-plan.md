# 开发计划

> 状态：已定稿（阶段一未开始）
>
> 最后更新：2026-09-14

## 项目概述

`flow`：一个轻量级多 agent 编排系统。后端 agent 是 Claude Code CLI 与 Codex CLI 原生子进程（不做 LLM API 代理），编排层负责 DAG 调度、markdown 共享记忆、可交互的会话管理。目标是"确定性内核 + 对话式外壳"。

### 已确认的核心决策（详见 decisions.md）

- 后端：`claude` / `codex` CLI，tmux 承载，attach/detach 交互
- 配置：YAML 单文件 DAG + agents 库目录
- 记忆：纯 markdown 文件树（CLI 自身记忆 / agent 私有记忆 / 流水线共享记忆三层），注入采用**路径引用**
- 任务 prompt：短句内联在 flow.yaml，具体任务内容写到 `task.md`
- 失败语义：无默认超时（可显式配置）、重试 0、失败暂停等人
- Control Agent（总控对话窗口）：**阶段一就做**
- 语言：Python；UI 终态为 Web 终端（阶段三），MVP 用 tmux 原生
- 验收用例：论文阅读与审稿流水线

## 阶段一：核心引擎 + Control Agent（MVP）✅ 已完成 2026-09-14

### 目标

在 tmux 中跑通一条完整的多 agent 流水线（含 control agent），全程可 attach 干预，产出 markdown 记忆与产物。

### 范围

- 后端驱动层、编排层、memory 层、tmux 会话管理、`flow` CLI、control agent 会话
- 不含：Web UI、DAG 可视化、并行节点的工作区隔离（共享一个 workdir）

### 任务

**M1 后端驱动层（风险最高，最先做）**
- [x] 真机验证：本机 claude / codex CLI 可用性、tmux 版本确认（claude 2.1.142 / codex 0.153.4 / tmux 3.4）
- [x] 驱动器：tmux 启动 `claude`/`codex`，send-keys 投递 prompt
- [x] 完成检测：Claude Code `Stop` hook 落 `done.flag` 实测可靠（codex notify 机制就绪，网关故障未完成最终验证，待补测）
- [x] `pipe-pane` 全程落盘 `tty.log`
- [x] 验收：单节点手动驱动跑通，done.flag 可靠触发，tty.log 完整（实测：API Error 路径不触发 Stop hook，需人工 retry——已在 ADR-0005 记录）

**M2 编排层 + memory 层**
- [x] flow.yaml 解析与 DAG 校验（`needs` 依赖、环检测、env 字段）
- [x] 调度器：依赖就绪即启动；`state.json` 状态机（pending/running/waiting-human/done/failed）
- [x] 节点执行流程：准备目录 → 注入（路径引用）→ 驱动 → done.flag → 驱动 summary 写入 → 标记完成 → 调度下游
- [x] 超时（显式配置）/ 失败暂停 / `retry` / `gate: true` 人工门
- [x] `flow resume <run-id>`：已完成节点跳过，从断点续跑
- [x] 目录结构落地（实现期修订为 project 自包含，见 ADR-0003 修订）
- [x] 验收：玩具 DAG（两节点）自动流转 + gate→approve 实测通过

**M3 会话管理与 flow CLI**
- [x] session/window 布局：`flow-<run-id>` session，window: control + 每节点一 window（序号前缀）
- [x] attach 状态管理：per-node flock，交互中的 pane 编排器暂缓投递
- [x] CLI 命令：`run / status / attach / log / resume / stop / approve / retry / inject`
- [x] `inject` 持久化队列（inject-queue.json，跨进程；实现期修复内存队列丢失 bug）
- [x] 编排器启动时生成 `.tmux.conf`
- [x] 验收：玩具 DAG 实测 attach/inject/approve 均工作

**M4 Control Agent**
- [x] control agent 定义：常驻节点、无 needs、不结束；agent.md 注入 flow CLI 用法 + flow.yaml + 状态查询方式
- [x] 能力边界：只通过 `flow` 命令与 memory 文件干预，不直接 send-keys 到其他 agent TUI
- [x] 验收：实测 control agent 自我介绍 + 运行 flow status + 汇报状态，等待指令

**M5 验收：论文阅读与审稿流水线**（已完成 2026-09-14）
- [x] 流水线：reader（gate）→ {methodology, experiments}（并行）→ reviewer，产出 artifacts/review.md
- [x] agents 库定义：reader / methodology-reviewer / experiments-reviewer / reviewer / control
- [x] 验收标准：全流程跑通（run 20260914-095424，KernelMemoryAuditor 论文），人工门生效，review.md 质量（Major Revision 意见含 15 条 weakness、10 条 questions、意见溯源标注），memory/findings 35 行、全部 summary 落盘
- 实测记录：第三方网关拒绝 PDF 二进制 content（400），验收改用 pdftotext 转文本（对编排器透明的环境问题）
- 实现期修复：inject 队列持久化（跨进程）、approve/retry 跨进程状态同步（每 tick reload state.json）、retry 时销毁旧窗口强制新会话

### 风险与依赖

- claude Stop hook / codex notify 的可靠性需真机验证（M1 第一项）；不可用则降级为「prompt 要求 agent 结束时 touch flag」
- codex 交互模式的指令投递格式需实测（TUI 与 send-keys 的兼容性）
- 并行节点共享 workdir 的文件竞争：M5 用例中并行节点只读上游产物、写各自目录，可接受

## 阶段二：易用性与健壮性

- [ ] 节点失败原因展示（tty.log 尾部 + summary 缺失检测）
- [ ] 长期记忆：agent 库 `longterm.md` 跨 run 注入
- [ ] rehost（FirmAE→PoC）流水线接入作为第二个真实用例
- [ ] flow.yaml 模板与 `flow init` 脚手架
- [ ] 状态事件流（为 Web UI 铺路）：编排器状态变化输出结构化事件

## 阶段三：Web UI

- [ ] tmux control mode / WebSocket 桥接 + xterm.js 终端
- [ ] DAG 可视化 + 节点状态实时渲染
- [ ] 围观模式（默认只读）与接管模式分离

## 计划维护规则

- 计划项应描述可验证的结果，而不是笼统活动。
- 状态变化时更新复选框，并补充验收证据或阻塞原因。
- 计划发生重大变化时，在 [`discussions.md`](./discussions.md) 记录原因；涉及架构取舍时同时新增决策记录。
