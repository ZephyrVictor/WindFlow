# CHES 2026 Phase 2 决赛编排

这是 Hack@CHES'26 Phase 2 决赛 campaign 的编排快照。入口是 [flow.yaml](flow.yaml)，每轮执行 [dig-sweep.yaml](pipelines/dig-sweep.yaml)。原始战役在仓库外的 `phase2/` 运行；这里保留编排、15 个 agent 的角色契约、知识文件和确定性检查脚本，不包含运行记录、目标设计树、漏洞报告或提交包。

## 设计

```text
campaign(controller)
  └─ 每轮 dig-sweep
       env-setup ─┬─→ poc-planner ────────────────┐
                  └─→ bug-planner ────────────────┼─→ finalizer
       adjudicator ────────────────────────────────┘

poc-planner → 动态 poc-wave / audit-wave → 波次票据
adjudicator → 逐票裁决与收据 → FILED bug-unit
bug-planner → 动态 bug-batch: report → verify → exploit → check
controller → checker 放行后触发 packager → 人工投递
```

`flow.yaml` 只放一个常驻 campaign 节点。Controller 读取跨轮状态和覆盖台账，确定下一轮焦点，启动轮次流水线，处理失败节点，并决定继续还是收敛。轮次 DAG 让环境准备、候选规划、资格裁决和成链规划在真实依赖允许时并行；`finalizer` 等三个核心角色全部结束后才收账。

动态工作量由 planner 写入父 run 的 `plan/`，再用 `flow run -f` 启动子流水线。这样每个子 run 都有自己的 YAML 快照、agent 会话、状态和证据目录；父节点负责监督和收账。候选通过 `plan/waves/*.ticket.md` 交给 adjudicator；裁决写 `*.receipt.md`，只有符合攻击链标准的 `FILED` 单元进入 bug-planner。票据和收据是异步角色之间的交接协议，也是故障恢复时的断点。

证据标准由 [context.md](knowledge/context.md) 和 [delivery-format.md](knowledge/delivery-format.md) 定义。PoC 区分完整攻击链、仅机制成立、证伪和构造不可行；报告、验证、利用与终审各有独立角色。利用必须由确定性断言给出判定词，并在接近评委的干净环境中重放。`checker` 以评委视角复核可达性、报告和复现；`packager` 只处理放行的包。自动化负责形成投递就绪材料，表单提交保留给人。

跨轮状态放在 `workdir/`：`FINDINGS.md` 保存候选，`attack-ledger.md` 保存待检假设，`SUBMISSIONS.md` 保存已投基线，`coverage.md` 和 `campaign-state.md` 保存覆盖与下一轮焦点。每个 `runs/<id>/` 保存单次执行状态、agent 摘要和子流水线计划。`knowledge/` 只接收验证过、可复用的方法；controller 在轮间晋升，避免把未证实发现写成长期事实。

## 目录

| 路径 | 内容 |
| --- | --- |
| `flow.yaml` | Campaign 总控入口 |
| `pipelines/dig-sweep.yaml` | 单轮 DAG |
| `agents/` | Controller、规划、审计、PoC、报告、验证、终审和打包角色契约 |
| `knowledge/` | 比赛规则、攻击链标准、审计清单、仿真和交付格式 |
| `scripts/` | 容器选择、CVSS、lint、证据归集和评委流程重放辅助脚本 |
| `workdir/`, `runs/` | 运行时目录，已忽略，不随示例发布 |

## 运行前提

该快照保留了决赛环境约束，不能对任意 OpenTitan 树直接运行。运行者需要有授权的比赛设计树 `/opt/opentitan`、等价评委容器、Verilator/Bazel 工具链和官方指南；指南放在 `workdir/participant-guide.pdf`。所有角色文件中的 `<project-root>` 代表本目录的绝对路径，生成子 YAML 时必须展开成真实路径。`flow.yaml` 和轮次 YAML 的 `../../knowledge`、`../../workdir` 注入路径从 `runs/<id>/` 解析到项目根。

```bash
PROJECT_ROOT="$(pwd)/agent_example/ches_final"
flow validate -p "$PROJECT_ROOT"
flow validate -p "$PROJECT_ROOT" "$PROJECT_ROOT/pipelines/dig-sweep.yaml"
# 确认上述环境和指南齐备后：flow run -p "$PROJECT_ROOT"
```

这是编排与方法的公开快照，不是比赛提交物。`workdir/` 的台账、运行日志、靶树及漏洞材料需要在实际环境中单独管理；脚本中的容器名称和比赛时间等参数按部署环境核对。
