# iot_hunter — 固件漏洞审计流水线（flow 实战示例）

用 flow 编排的多 agent 固件安全审计系统：输入一个固件包，产出带证据分级的漏洞审计报告——静态反汇编审计 → FirmAE 全系统仿真动态验证 → 动静结论合并终判。本目录是实战项目的结构快照（角色定义即核心资产），已在真实固件上完整跑通三轮，见下方[实战成绩](#实战成绩)。

> 用途限定：自有 / 授权固件的安全研究。

## 流水线

```
unpacker(gate) ─┬─→ planner ─→ correlator ─→ reporter(gate) ─┐
                │      └→ 4× audit 子流水线（并行）            ├─→ poc-planner ─→ finalizer
                └─→ rehoster（FirmAE 仿真，与审计链并行）──────┘       └→ 4× verify 子流水线（并行）
```

- **双 gate**：unpacker 后人工确认审计目标；reporter 后人工确认静态报告再进复现阶段
- **并行化**：rehoster 只依赖 unpacker（真依赖只有 inventory.md 的仿真路由信息），与整条审计链并行——仿真耗时小时级，不占审计关键路径
- **动态 fan-out**：planner / poc-planner 在 run 内 `flow run -f` 拉起子流水线并同步等待完成（工单以 skill 形式下发）
- 另有两个变体 yaml：`flow-rehost.yaml`（续跑模式：接已完成审计的 run，只跑 rehost→PoC→终判，inject 旧 run 产物绝对路径避免重跑）、`flow-retest.yaml`（复测模式：环境修复后全量复测 + 补审）

## agent 角色（10 个）

| agent | 职责 |
|---|---|
| control | 常驻总控：巡检节点、区分基础设施故障与 agent 问题、给人提处置建议 |
| unpacker | 解包固件、识别设备与版本、产出攻击面盘点 `inventory.md` |
| planner | 制定审计计划：选目标 binary × 审计角度（≤4 工单），写 audit skills，spawn 审计子流水线并等完成 |
| auditor | 按工单做反汇编级静态审计（objdump + 字符串交叉引用，不凭 strings 猜测），发现追加 findings.md |
| correlator | 汇总发现、拼装跨组件利用链、去重定级，产出候选清单 `artifacts/vulns.md` |
| reporter | 撰写静态审计报告 `artifacts/report.md`（置信度忠实转述上游，不升级不淡化） |
| rehoster | 按 `backends.md` 路由选择仿真后端（FirmAE 全系统 / unicorn 函数级 / 静态结论），搭建环境并把环境契约写入 context.md |
| poc-planner | 按环境能力裁剪 PoC 工单（服务未启动 / 缺审计环节的项明确标 blocked 而不是硬验），spawn 验证子流水线并等完成 |
| verifier | 在仿真环境执行 PoC，以 serial log 命令执行痕迹取证，判定 实证 / 证伪 / blocked |
| finalizer | 动静结论合并（冲突以动态为准、置信度不升级），产出 `artifacts/final-report.md` |

## 方法论要点

- **证据分级**：静态（反汇编级、地址可复核）→ 动态（执行级实证 / 证伪）；未验证项维持静态置信度，禁止升级
- **追加式发现协议**：findings.md 按 `[agent名]` 标记来源逐条追加；summary.md + done.flag 声明节点完成
- **跨 run 经验沉淀**：`agents/<name>/longterm.md` 种子随每个 run 快照进私有 memory（FirmAE 踩坑清单、serial log 取证法、按 fidelity 裁剪工单），run 内新教训写在"晋升候选"节、人工定期晋升
- **故障自愈**：`scripts/watchdog.sh` 检测 API 网关故障（tty.log 尾部 API Error）自动 inject 恢复提示（30min 节流）；运行超时巡检提醒 control 分析（2h 过期重报）。`--loop` 自守护（pidfile 防双启，60s 间隔），`--stop` 停止；默认单次执行向后兼容
- **运行中干预**：gate `flow approve`、卡死 `flow inject`、必要时 tmux attach 直接进对话

## 实战成绩

| 目标固件 | 轮次 | 结果 |
|---|---|---|
| Cisco Catalyst 2950 · IOS 12.0(5.4)WC1 | 2026-09-14 静态轮 | 5 候选漏洞、2 条 RCE 链（字节级证据）；IOS MZIP 单体架构性不可仿真，纯静态收尾 |
| Cisco Aironet 1850 ME · 8.10.130.0 | 2026-09-15/16 首轮 + retest | 8 候选 → 2 条 pre-auth root RCE 执行级实证、1 条执行级证伪；本轮暴露的串行浪费与网关长故障直接催生 v2 |
| Cisco Aironet 1850 ME · 8.10.130.0 | 2026-09-17 v2 并行轮 | **20 候选 → 6 条执行级实证**（3 条互相独立的单请求 pre-auth root RCE、通用认证绕过原语、无认证凭据重置、凭据哈希泄露）、1 条执行级证伪（tar 穿越）、13 条维持静态结论。13 节点全链 4h42m，16 个 agent 会话，2,944 次 API 调用，名义 2.28 亿 token（96% 为缓存读） |
| Cisco Aironet 1850 ME · 8.10.130.0 | 2026-09-18 补验轮 | 13 条未验证项动态补验 + 补审：**累计 12 条执行级实证**（新增 sshd 认证层完全绕过、dlopen root RCE 链闭环、CVE-2019-11587 单包 DoS 实证等 6 条）、3 条证伪、**5 条新静态重大发现**（capwapd pre-auth VSP 堆溢出 ~49.5KB、codec 栈溢出、chpasswd root 注入 + 硬编码 UID 0 凭据）；终判报告 28 漏洞全表。两批并行子流水线（planner 动态 fan-out） |

`workdir/artifacts/` 下是补验轮的真实产出示例：`final-report.md`（终判报告，28 漏洞全表）、`report.md`（静态审计报告）、`vulns.md`（候选清单）。

## 目录说明

```
├── flow.yaml              主流水线（并行 DAG）
├── flow-rehost.yaml       续跑模式（接已完成审计的 run）
├── flow-retest.yaml       复测模式（环境修复后全量复测 + 补审）
├── flow-ap3g3.yaml        完整轮模板（静态+rehost+PoC 七节点，2026-09-19 实战）
├── flow-c3550.yaml        静态终轮模板（无模拟器目标，报告即终判）
├── agents/                10 个 agent 的角色定义；rehoster/backends.md（仿真后端路由表）
│                          与 {rehoster,verifier,poc-planner}/longterm.md（角色程序性经验）
├── knowledge/             跨 run 知识库（INDEX 命中表 + vendors 厂商家族 /
│                          vulns 漏洞类型方法论 / rehost 工艺；五要素字段含"死路"）
├── scripts/watchdog.sh    巡检与故障自愈
└── workdir/artifacts/     真实产出示例（v2 轮三份报告）
```

不纳入版本库的运行时内容：`workdir/`（固件包与解包产物，GB 级）、`runs/`（run 历史：每 run 的 memory、agent 工作目录与 tty 日志、子流水线）。

## 复用到新目标

1. 固件包放进 `workdir/`
2. 配置 CLI 后端环境（token 只进 shell env）：
   ```bash
   export ANTHROPIC_BASE_URL=... ANTHROPIC_AUTH_TOKEN=... ANTHROPIC_MODEL=...
   ```
3. `flow run -p <项目根>`；gate 处 `flow approve <node> <run_id> -p <项目根>`
4. 换设备家族时主要调整：`agents/unpacker`（解包与盘点逻辑）、`agents/rehoster/backends.md`（仿真路由）、planner 的工单模板
