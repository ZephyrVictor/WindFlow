# 架构与技术决策记录（ADR）

本文件记录会影响后续实现的关键取舍。已废弃的决策保留在历史中，但必须标注替代它的新决策。

## ADR-0001：建立项目文档治理流程

- **状态**：已接受
- **日期**：2026-09-14
- **背景**：项目需要在持续开发中保持架构上下文、讨论结论和计划可追踪。
- **决策**：使用 `.codex/agent.md` 作为协作总领；使用 `docs/architecture.md`、`docs/development-plan.md`、`docs/decisions.md` 和 `docs/discussions.md` 分别维护当前架构、计划、取舍和讨论结论。开发前阅读相关文档，架构变化后在同一变更中回写文档。
- **原因**：降低聊天上下文丢失和架构漂移风险，同时让新参与者能从固定入口了解项目。
- **影响**：每个影响架构的变更都包含相应文档更新；纯实现细节可不新增 ADR，但仍应更新计划或讨论记录（如有必要）。

## ADR-0002：flow 总体架构——CLI 后端 + 薄编排层 + tmux 承载

- **状态**：已接受
- **日期**：2026-09-14
- **背景**：需要一个可编排 Claude Code 与 Codex 的多 agent 流水线系统。调研结论（claude-flow、Spec Kit、Claude Squad、Vibe Kanban、CrewAI/LangGraph 等）显示市面上没有同时具备声明式 DAG、双 CLI 后端、可 attach 的交互、轻量 markdown 记忆的项目。
- **决策**：不做 LLM API 代理，agent 本体永远是 `claude` / `codex` 原生 CLI 子进程；编排器为 Python 薄层（调度/状态/落盘），agent 会话跑在 tmux（session=run，window=agent），完成检测用 Claude Code `Stop` hook / codex `notify` 落 `done.flag`，不解析终端输出。
- **备选方案**：Agent SDK headless 驱动（无法 attach 交互）；Claude Squad 式纯 tmux 管理（无编排）；claude-flow（过重）。
- **原因**：复用 CLI 的订阅计费、本地 skills/hooks 生态与会话可恢复性；确定性内核 + 对话式外壳。
- **影响**：MVP 交互靠 tmux 原生（mouse on、history-limit 100000），Web UI（xterm.js + tmux 桥接）为阶段三。

## ADR-0003：三层 markdown 记忆 + 路径引用注入

- **状态**：已接受
- **日期**：2026-09-14
- **背景**：多 agent 间需要上下文传递与共享记忆，同时保留各 CLI 自身记忆。
- **决策**：①CLI 自身记忆（不碰）；②agent 私有记忆 `runs/<id>/agents/<name>/memory.md`；③流水线共享记忆 `runs/<id>/memory/`（context 只读、findings 追加式、decisions）。节点可配置 `inject`，注入方式为**路径引用**（prompt 给路径+「先读这些」），不拼全文。每个节点完成后由编排器追加一轮驱动，令其写 `summary.md` 作为下游注入的窄接口。目录三层：`~/flow/agents`（agent 库，含跨 run 的 longterm.md）→ `projects/<p>/`（flow.yaml + 共享 workdir）→ `runs/<id>/`。
- **备选方案**：全文注入（上下文成本高、易过时）；向量库记忆（重，违背轻量目标）。
- **原因**：文件即真相，人可直接查看/修改（本身是干预手段），git 即版本。
- **影响**：依赖 agent 有可靠 Read 工具（claude/codex 均满足）。

## ADR-0004：编排语义——无默认超时、失败暂停、人工门、Control Agent 阶段一交付

- **状态**：已接受
- **日期**：2026-09-14
- **决策**：
  1. 节点无默认超时（必须显式配置）、失败重试 0、失败后暂停整条流水线等人（可 attach 修复后 `flow resume`），不自动跳过。
  2. `gate: true` 节点跑完进入 waiting-human，`flow approve` 放行。
  3. 任务 prompt：短句内联在 flow.yaml，具体任务内容写在节点 `task.md`。
  4. Control Agent（常驻对话节点，总领编排）纳入阶段一：只通过 `flow` CLI 与 memory 文件干预，不直接 send-keys 其他 agent TUI；编排器对交互中的 pane 暂缓投递。
  5. 验收用例为论文阅读与审稿流水线（reader → gate → 并行双审查 → reviewer）。
- **原因**：安全类/审稿类流水线跳过失败节点易产生误导性结果；control agent 采用结构化干预通道避免双驱动者冲突。
- **影响**：开发计划见 development-plan.md 阶段一 M1–M5。

## ADR-0003（修订）：三层 markdown 记忆 + 路径引用注入；agent 按 project 管理

- **状态**：已接受（2026-09-14 修订，同日实现期确认）
- **日期**：2026-09-14
- **背景**：多 agent 间需要上下文传递与共享记忆，同时保留各 CLI 自身记忆。
- **决策**：①CLI 自身记忆（不碰）；②agent 私有记忆 `runs/<id>/agents/<name>/memory.md`；③流水线共享记忆 `runs/<id>/memory/`（context 只读、findings 追加式、decisions）。节点可配置 `inject`，注入方式为**路径引用**（prompt 给路径+「先读这些」），不拼全文。每个节点完成后由编排器追加一轮驱动，令其写 `summary.md` 作为下游注入的窄接口。
- **修订内容**（原方案 agent 库为全局 `~/flow/agents/`）：**agent 定义按 project 管理**——project = 任意含 flow.yaml 的目录，agent 定义在 `<project>/agents/<name>/agent.md`，无系统根目录。原 `longterm.md` 跨 run 记忆随之放在项目 agent 目录下。
- **备选方案**：全文注入（上下文成本高、易过时）；向量库记忆（重，违背轻量目标）；全局 agent 库（跨项目复用是伪需求，角色定义与流水线强耦合，真需复用时复制目录即可；未来可加 `~/.flow/agents/` 全局 fallback）。
- **原因**：文件即真相，人可直接查看/修改（本身是干预手段），git 即版本；project 自包含、可整体迁移。
- **影响**：依赖 agent 有可靠 Read 工具（claude/codex 均满足）。

## ADR-0005：驱动层实测结论与固化方案

- **状态**：已接受
- **日期**：2026-09-14
- **背景**：M1 真机验证 send-keys 驱动、完成检测、tty.log 落盘。
- **决策与实测结论**：
  1. **环境继承是第一坑**：tmux server 全局环境早于认证变量设置时不继承，导致 claude "Not logged in"。方案：驱动命令内联环境赋值（FORWARDED_ENV_VARS 透传编排器环境 + 节点 `env` 字段覆盖），不依赖 tmux server 全局环境。
  2. **claude Stop hook 可靠**：per-node settings.json 的 Stop hook → touch done.flag 实测触发；prompt 投递用 `send-keys -l` + Enter。
  3. **TUI 就绪判据**：claude 欢迎框不消失，判据为最后 6 行内出现 `❯`；codex 为 `›`。投递过早会静默丢失。
  4. **codex**：per-node CODEX_HOME（config.toml 含 notify + 继承用户 model/provider 配置 + auth.json 符号链接）可用；网关故障未完成 notify→flag 最终验证，机制待补测（见 development-plan 风险项）。
  5. **claude trust 对话框**：用 `--dangerously-skip-permissions` 跳过。
- **影响**：flow/driver.py、flow/session.py 的实现直接来自以上结论。

## ADR-0006：子流水线模式（动态 fan-out 由 agent 生成静态 DAG 实现）

- **状态**：已接受
- **日期**：2026-09-14
- **背景**：iot_hunter 等流水线需要在运行时根据上游产出动态决定审计节点数量（planner 按 binary × 角度 fan-out），但 flow.yaml 是静态 DAG，引擎不支持运行时加节点。
- **决策**：
  1. 采用**子流水线**模式：planner agent 生成子 flow.yaml（audit 节点 ≤4，超限按优先级裁剪）放在父 run 的 `plan/` 下，然后用 `flow run -f <file>` 同步执行到完成，子节点通过 inject 绝对路径共享父 run 的 memory，产物（findings 追加）直接落父 run。
  2. 引擎配套：`flow run` 增加 `-f/--pipeline`；`initialize()` 把生效 yaml 快照到 run 内 `pipeline.yaml`，status/approve/retry 优先按 run 内副本解析（否则子 run 会按项目默认 yaml 解析出错误节点集）；`find_project_root` 跳过 `runs/` 内的 flow.yaml（planner 生成的子 yaml 不是项目根）。
  3. 拼链不新增 memory 文件：维持 context/findings/decisions 三文件，链线索以 `[chain]` 标记条目追加进 findings.md（格式：入口可控性 → 数据流 → sink → 前置条件 → 置信度）。
- **备选方案**：固定审计池（并行度锁死、工单与窗口对应不直观）；引擎支持动态节点（阶段二以后的过度设计）。
- **原因**：节点=工单一一对应，attach/retry/inject 全部自然复用；引擎改动最小（两处）；DAG 大小随目标伸缩。
- **影响**：flow/cli.py、flow/orchestrator.py、flow/paths.py；planner 的 agent.md 内嵌子 yaml 模板与 skill schema；首个用例 iot_hunter（独立项目目录）。

## ADR-0007：agent 自编排生态——形态 A + 标准 skill + 写侧命令面

- **状态**：已接受
- **日期**：2026-09-14
- **背景**：flow 终态是"agent 编排 agent"：用户与任意 agent 对话即可创建/调整/编排流水线并总控。两种形态：A（外层 agent 操控 flow，run 内 control 收尾）与 B（control 反向成为唯一入口、可改自身 DAG）。选 A：职责清晰（编排/运行分离），skill 可复用给任意会话/CI；B 会让 control 能力边界膨胀且绕回运行时动态节点问题。
- **决策**：
  1. 形态 A。外层 agent 经标准 **Anthropic skill 格式**（SKILL.md + frontmatter，skill-creator 规范）习得 flow 用法；skill 源文件在本仓库 `skills/flow/`，手动拷贝到 `~/.claude/skills/` 分发（不做 install 命令，保持简单）。
  2. 补齐写侧命令面：`flow validate`（改完必验）、`flow agent new/list/show`、`flow init`（骨架模板）、`flow clean`（清终态 run 的 session；`--runs N` 交互删旧 run）。
  3. skill 与引擎代码分离：skill 是"说明书"（命令/schema/编排模式/行为准则），不内嵌引擎实现细节；模板文本仍集中在 prompts.py（init 骨架、agent.md 四段式模板）。
- **备选方案**：flow skill install 自动分发（版本随包，但多一条命令维护面）；B 形态（见背景）。
- **原因**：标准 skill 格式可被任意 claude 会话自动发现加载、生态兼容；手动拷贝符合个人工具现状。
- **影响**：cli.py 命令面 9→13 组；SKILL.md 是"agent 能否正确编排"的单点，须真机用"无知会话"验收并迭代。

## ADR 模板

复制以下模板，使用递增编号：

```markdown
## ADR-XXXX：<简短标题>

- **状态**：提议 / 已接受 / 已废弃
- **日期**：YYYY-MM-DD
- **背景**：为什么需要做这个决定？
- **决策**：决定采用什么方案？
- **备选方案**：考虑过哪些方案，为什么不选？
- **原因**：关键取舍和约束是什么？
- **影响**：对代码、数据、运维、团队和后续演进有什么影响？
- **相关文档/变更**：链接到实现或其他文档
```
