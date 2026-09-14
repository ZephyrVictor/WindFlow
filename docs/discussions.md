# 讨论记录

这里记录会影响项目方向的讨论，而不是逐字保存所有聊天内容。每条记录应提炼背景、结论、未决问题和行动项；形成正式取舍后，另写入 [`decisions.md`](./decisions.md)。

## 讨论模板

```markdown
## YYYY-MM-DD：<议题>

### 背景

### 讨论要点

### 结论

### 未决问题

- [ ] <问题>（负责人：<姓名/角色，截止：YYYY-MM-DD）

### 行动项

- [ ] <行动>（负责人：<姓名/角色，截止：YYYY-MM-DD）

### 关联

- 架构：`architecture.md` / <章节>
- 计划：`development-plan.md` / <阶段或任务>
- 决策：`decisions.md` / ADR-XXXX（如适用）
```

## 2026-09-14：agent 自编排生态（形态 A）

### 背景

iot_hunter 验收通过后讨论终态方向：flow 要发展成"用户与一个主 agent 对话，该 agent 创建/调整/编排其他 agent"。需确定操控形态与 skill 载体。

### 讨论要点

- 形态 A（外层 agent 操控 flow + run 内 control 收尾）vs B（control 唯一入口、可改自身 DAG）
- skill 必须是标准 Anthropic 格式（skill-creator 规范），方便维护与生态兼容；与 flow 项目内 agent.md（prompt 约定）严格区分
- 写侧缺口：agent 能 run/干预但不能建 agent/起项目/校验 yaml

### 结论

选形态 A（ADR-0007）。skill 源文件 `skills/flow/SKILL.md` 手动拷贝分发；新增 validate/agent/init/clean 四组写侧命令。TUI 暂缓（tmux attach 即 TUI，Web 面板归阶段三）。

### 未决问题

- [ ] SKILL.md 真机验收："无知会话"实测自主编排，预期 1-2 轮修订
- [ ] skill 分发自动化（若手动拷贝成为负担再做 install）

### 关联

- 决策：`decisions.md` / ADR-0007
- 计划：`development-plan.md` / 阶段二

## 2026-09-14：子流水线模式（动态 fan-out 的引擎设计）

### 背景

运行时才知道节点数量的编排场景（如按固件内容决定审计工单数）需要动态 fan-out，但 flow.yaml 是静态 DAG。以固件漏洞挖掘流水线为首个需求来源。

### 讨论要点

- 动态节点三种方案：固定节点池 / 子流水线（agent 生成子 yaml 再 `flow run -f`）/ 引擎原生动态节点
- 多角度审计（逻辑/命令注入/内存破坏/认证绕过）进 skill 的 checklist，不做独立 DAG 节点（避免 DAG 爆炸、同目标多角度共享上下文）——这是应用层约定，不进引擎
- 拼链记忆是否单独文件：维持 context/findings/decisions 三文件简洁性，链线索以 `[chain]` 标记条目并入 findings.md

### 结论

引擎采用子流水线模式（ADR-0006）：上游 agent 生成子 flow.yaml 并自行同步执行 `flow run -f`；子 run 经 inject 绝对路径共享父 run memory。首个使用方为 iot_hunter 固件审计流水线（独立于本仓库的应用项目）。

### 未决问题

- [ ] 生成方 agent 产出非法子 yaml 的自修复能力（真机验收观察）

### 关联

- 架构：`architecture.md` / 目录结构、动态 fan-out
- 决策：`decisions.md` / ADR-0006

## 2026-09-14：阶段一（MVP）实现完成

### 结论

M1–M5 全部完成并通过真机验收。玩具 DAG 自动流转/gate/approve 通过；论文审稿流水线端到端跑通（run 20260914-095424），产出高质量 review.md。

### 实现期发现与修复

1. tmux server 全局环境不继承认证变量 → 驱动命令内联 env（FORWARDED_ENV_VARS + 节点 env 字段）
2. TUI 就绪判据：claude 最后 6 行出现 ❯（欢迎框不消失）、codex ›；投递过早静默丢失
3. window 名为 `<idx>-<node>`，pane 定位需后缀解析
4. inject 队列最初为内存态，跨进程丢失 → 持久化 inject-queue.json
5. approve/retry 与编排器进程的状态竞争 → run_loop 每 tick 从磁盘 reload state
6. retry 需销毁旧 tmux window，否则在污染会话上继续投递（PDF 非法 content 污染上下文的案例）
7. API Error 路径不触发 Stop hook，CLI 卡死需人工 attach 发现 + retry（已允许 running 态 retry）
8. 第三方网关（cherr.cc）拒绝 PDF 二进制 content → 文本化 workaround，非编排器问题

### 未决问题

- [ ] codex notify → done.flag 最终验证（网关恢复后补测，机制已就绪）
- [ ] 阶段二：失败原因展示、longterm.md 注入、rehost 流水线接入、flow init、状态事件流

### 关联

- 计划：`development-plan.md` / 阶段一（全部勾选）
- 决策：`decisions.md` / ADR-0003 修订、ADR-0005


### 背景

需要将 rehost_agent（固定编排的 FirmAE→PoC 流水线）泛化为任意 DAG 的多 agent 编排系统，后端为 claude/codex CLI。先做了开源调研（claude-flow、Spec Kit、Claude Squad、Vibe Kanban、CrewAI/LangGraph 等），确认目标组合为市场空白。

### 讨论要点

- 驱动方式：tmux 承载（attach/detach 交互）+ hook 完成检测，否决纯 headless 与 API 代理。
- 记忆：三层 markdown（CLI 自身/agent 私有/流水线共享），注入用路径引用；summary 作为节点间窄接口。
- 目录：agent 库 / 项目 / run 三层分离；workdir 共享且跨 run 持久。
- 交互：一个 run 一个 tmux session，每 agent 一个 window；attach 中暂缓投递；围观/接管分离（Web UI 阶段）。
- Control Agent：总控常驻对话节点，阶段一交付；只经 flow CLI 与 memory 干预。
- 失败语义：无默认超时、重试 0、失败暂停等人；gate 人工门进 MVP。
- 验收用例：论文阅读与审稿流水线（原拟 rehost 流水线后移至阶段二第二用例）。

### 结论

架构与阶段计划定稿，见 ADR-0002/0003/0004 与 development-plan.md 阶段一（M1–M5）。

### 未决问题

- [ ] M1 真机验证 claude Stop hook / codex notify 可靠性（阶段一开工首项）
- [ ] Web UI 桥接选型（阶段二/三）
- [ ] agent 库 longterm.md 注入策略（阶段二）

### 行动项

- [ ] 开工阶段一 M1：后端驱动层真机验证

### 关联

- 架构：`architecture.md` / 全文
- 计划：`development-plan.md` / 阶段一
- 决策：`decisions.md` / ADR-0002、ADR-0003、ADR-0004


### 背景

项目目录为空，需要建立可持续维护的架构讨论和开发记录入口。

### 结论

采用 `.codex/agent.md` 作为总领规则，并用四份核心文档分别维护架构、计划、决策和讨论。

### 未决问题

- [ ] 补充项目业务目标、技术栈和第一阶段范围

### 行动项

- [ ] 开展第一次架构讨论并更新 `architecture.md`、`development-plan.md`
