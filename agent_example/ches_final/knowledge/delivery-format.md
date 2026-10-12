# delivery-format — Phase 2 提交物格式(唯一真源)

适用:Hack@CHES'26 Phase 2(27 问表单,exploit=make-package)。
读者:reporter / verifier / exploiter / packager。

## 0. 环境事实(指南口径)

- 判官流程:把 `src/` 拷入全新未修改镜像的 `/opt/opentitan/exploit/`,只跑 `make && make run`;≤30min;不得需要额外安装的包;不得需要任何手工步骤。
- 镜像:OpenTitan 树 + Verilator 4.210 + Bazel;user=player;树根=`/opt/opentitan`;chip 级 Verilator 仿真与 bazel 缓存全量预构建(on-device 测试实测 ≈200s)。
- 判分词:`EXPLOIT_SUCCESS` / `EXPLOIT_FAIL` 逐字匹配,是 exploit 的判分依据。
- 表单:https://forms.gle/42NQ2q8ZXVEpJKkb6,一 bug 一表单,27 问,附件直传。
- **exploit 形态(指南硬规则)**:"User-level software, or a testbench for physical attacks, that triggers the bug in the provided image"。软件类对手 ⇒ on-device 测试(sw/device/tests 风格,Bazel 构建运行);物理类对手 ⇒ 攻击流+仿真 TB("an attack flow plus a simulation testbench that demonstrates feasibility counts as the exploit")。
- 工具计分:自研工具首用 100 / 现有工具 50 / 自动检出每 bug 5;**列了工具无证据 = 没收加分且 -5**;LLM 类工具证据 = 确切模型与版本、在线/本地、**全部 prompts 与 responses**、所用脚本、input/output token 数;判官可用自己的 key 复跑脚本。

## 1. 交付单元(每 bug,全程目录态)

```
workdir/staged/<bug-id>/
├── report.md      # 27 问答案文档(paste-ready)
├── evidence/      # Q17 的目录态
│   ├── README.md
│   ├── poc/               # PoC make-package(README.md + src/)
│   ├── logs/              # 我方运行副本(cmd/build/run 三件套 + 判定行)
│   ├── TEST-SUMMARY.md    # 断言 + 证据链
│   └── tool/              # 工具主张证据(§6 结构,收集器组装)
└── exploit/       # Q26 的目录态
    ├── README.md          # 五要素 + 保真度表+能力映射表(物理类);FI 禁止
    └── src/               # 全部源码 + Makefile
```

- staged/ 树内每一字节都是可提交字节;内部材料(台账/判决书/决策记录)绝不进 staged。
- zip 只在 packager 一步导出:`<bug-id>_{evidence,exploit}.zip`;exploit.zip 解开与目录态逐字节一致。
- Q26 无 exploit 的 bug:exploit/ 目录缺席,报告 Q26 答 `None`。

## 2. make-package 契约(exploit 包与 PoC 包同构)

### 2.1 硬规则
- **恰好两个可调用 target**:`all`(默认=构建全部)+ `run`(运行+判定);文件级内部 target 允许。
- **判定词**:exploit 包 = `EXPLOIT_SUCCESS` / `EXPLOIT_FAIL`;PoC 包 = `POC_SUCCESS` / `POC_FAIL`。
- **判定词必须是 stdout 最后一行、独立成行、逐字匹配**;`make run` 恒 exit 0。
- **无 token 退出按最严重事故处理**:任何异常路径必须捕获后打 FAIL 判定词再正常退出。
- `TREE ?= /opt/opentitan`、`VERILATOR ?= verilator`(判官零感知;本机测试可 override)。
- **零环境变量、零参数、零手工步骤**。
- 因果对照机器可读:attack 臂呈现缺陷行为,control/secure 臂呈现基线("fails because of the bug, not for another reason" 的机器可读形式)。
- `make run` 写 `./logs/`;我方归档副本进 evidence/logs/。
- **预算**:`make` 起到 `make run` 止 wall ≤30min;验收=fresh 目录实测计时,不估算。
- **零新依赖**:纯 verilator + bash + coreutils(software 类 on-device 包:bazel,镜像内置)。

### 2.2 on-device 包(软件类 exploit 专用形态)
- src/ 内放独立目录 `sw/device/tests/<slug>/`:测试 .c(用树内 DIF 库)+ BUILD(仿树内既有
  `sw/device/tests/BUILD` 的 sim_verilator target 形态)+ 需要的辅助文件。
- Makefile:`make` = 把 `<slug>/` 拷入 `/opt/opentitan/sw/device/tests/`(新路径,不改任何既有文件)
  → `make run` = `cd /opt/opentitan && bazel test //sw/device/tests/<slug>:<t>_sim_verilator
  --test_output=streamed`,grep 关键锚点行后打判定词,恒 exit 0。
- 测试即攻击者:测试程序=设备上运行的攻击者软件(软件类对手的本体);从真实 ROM 引导后的
  状态起步,配置/触发/观测全在设备上(引导后状态=交付现实,环2/环3 每次运行实证闭环)。
- 判定锚=设备上可观测的资产危害(CSR 读回/存储器读数/DIF API 返回),不是 TB 内部探针。

### 2.3 README 五要素(两包同构)
1. **演示什么**:资产 + 攻击者 + 一句话后果(与 Q5/Q6 口径一致)。
2. **构建**:一句 `make`(判官环境 /opt/opentitan/exploit/)。
3. **运行**:`make run` + 预期时长。
4. **预期输出**:判定词逐字 + 关键 ANCHOR/RESULT 行摘录(数行)。
5. 臂说明:attack=缺陷行为,control/secure=基线或修正后的安全行为。

### 2.4 保真度表(物理类 TB exploit 的 README 必含)
| 环节 | 真物/建模 | 若建模:为何换真物结论不变 |
|---|---|---|
| 目标 IP RTL | 真物(靶树) | — |
| 决策相关消费者 | 必须真物 | — |
| 非决策模块(如上游熵响应器) | 可建模 | 一句论证 |
| 攻击者接口驱动 | 仿真等价(TB 顶替引脚/接口驱动——攻击者真实拥有的物理动作) | 能力映射表(见下) |
| 受害方正常操作(设备自身软件按文档序列运行) | 可建模 | 非攻击者动作,如实申报 |

**能力映射表模板**(物理类必含):攻击流每一步 → 指南类 3 授予的能力(驱动哪个
外部接口 SPI/UART/USB/GPIO、什么时序/线序);刺激从真实接口边界进入,经真实
外设 RTL 传播;对照臂:同一接口刺激在无缺陷路径/无前置状态时<告警/拒绝行为>,
证明链完整才越界。

**FI 前提禁止(D-r2-5,2026-10-12 判官实战校准)**:stuck-at/位翻转/激光/EM/
电压毛刺/时钟毛刺等内部故障注入不在指南第 7 页类 3 能力清单内("Has the device
and can drive its external pins and interfaces (SPI, UART, USB, GPIO)")——
攻击侧任何 FI 步骤 = no security impact under the adversary model = invalid;
「单点 FI=激光类注入的标准物理前提」的文献论证不算证明攻击者能造成该内部故障。
TB 里对 DUT 内部网/寄存器的 force/deposit 出现在攻击侧=捏造攻击者能力,禁止。

### 2.5 判定语义
- exploit 包:`EXPLOIT_SUCCESS` 当且仅当战役锚点全中。
- PoC 包:`POC_SUCCESS` 当且仅当 attack 臂缺陷行为 **且** control/secure 臂基线成立。

## 3. report.md = 27 问答案文档

形态:`## Q<n>. <官方题名>` 逐节(1-27);题名与官方表单逐字一致(lint 机械比对);
答案=纯文本 paste-ready;代码引用 `hw/ip/.../x.sv:行号`(镜像内路径,无 `./` 前缀)。

### 3.0 逐字段内容要求(判官按此检查;终审以官方指南 PDF 为准)

| 问 | 必须包含 | 保证机制 |
|---|---|---|
| Q1 Team name | `firebud` | — |
| Q2 Bug title | 英文陈述句 ≤15 词,不带内部代号 | lint 词数机械检查 |
| Q3 Affected IP block | IP 名 | — |
| Q4 Bug location | 镜像内路径+行号,指向 faulty lines | run-time 树内核验(needle 守卫) |
| Q5 Description | **Expected vs Actual 对照**(预期引规格/文档出处,实际引 RTL file:line)+ **完整触发条件** | 三段式模板;触发条件与 Q10 逐条对齐 |
| Q6 Security impact | **受保护资产叫什么名、具体受什么损害**(给谁、什么前置) | 每句影响对应演示中的固定数值锚点;资产在指南 scope 内;禁推测语气 |
| Q7 Security property | C/I/A 中实际违反的项+被违反的安全属性名 | 与 Q6、演示观测三方一致 |
| Q8 CWE | 编号+名称(§5 速查起点,逐 bug 复核官方定义) | — |
| Q9 Attacker | 四类官方措辞之一 | 形态匹配门:软件类⇒on-device exploit;物理类⇒TB(攻击动作只走外部引脚/接口);能力集=指南第7页封闭枚举,FI 前提=invalid(D-r2-5) |
| Q10 Preconditions & steps | **攻击者真实能力范围内的完整触发步骤** | 七门;步骤与 exploit 动作 1:1;前置=交付现实(file:line)或攻击者自造(步骤在场);递枪句 lint |
| Q11 Proposed fix | 修复+定向测试/断言 | — |
| Q12 CVSS vector | 向量串+逐维推理(8 维全覆盖,每维标注对应演示事实) | — |
| Q13 CVSS base score | **必须等于 Q12 的机械复算**(引擎:`python3 scripts/cvss_calc.py --report report.md`,Roundup=向上取整;PR 权重随 Scope 变化是最常见错因) | lint 检查强制 Q13==复算值 |
| Q14 Detection method | §4 系统叙事+per-bug 细节(哪个环节检出、agent 做了什么、如何确认) | — |
| Q15 Tools used | `Simulation; custom in-house tool; LLM` | — |
| Q16 Tool names | `firebud_multiagent_bug_hunter (our self-developed multi-agent cluster and harness system built around an LLM); Verilator <实测版本>` | 版本与 evidence/logs/environment.txt 逐字一致 |
| Q17 Tool evidence | `<bug-id>_evidence.zip: ...` 文件名+一句话 | judge-replay 容器绿 |
| Q18 Did you use an LLM? | `Yes` | — |
| Q19-Q25 | 模型名版本/访问方式/endpoint/参数/token 三元组(input/output/total)/prompts+responses+scripts/**指向 tool/ 目录完整归档**/LLM 如何导向 bug | tool/ 由收集器组装(§6);Q23 口径:input 含 prompt-cache 读数+合计口径 |
| Q26 Exploit ZIP | `<bug-id>_exploit.zip: ...` 一句话;无则 `None` | judge-replay:fresh scratch+`make && make run`+EXPLOIT_SUCCESS 末行+exit 0+≤30min |
| Q27 Declaration | Ticked | — |

### 3.1 禁词与代号 lint(全提交物;evidence/tool/ 例外见 §6)
- 禁词:upstream / pristine / 植入 / implant / 上游 / diff / patch;内部树代号与
  历史结构标记一律不出现(清单由 lint 内部维护:workdir/lint-codenames.txt,
  不随任何提交物分发)。
- 内部代号类:`N\d+` 内部编号、site-id、master 等树别名、campaign / sweep / wave /
  台账 / 战役 等内部术语。
- 本机绝对路径(`/home/<user>/`)禁止;因果对照措辞 = attack 臂 / secure 臂;needle 注释只写「靶内固有行」。
- **evidence/tool/ 豁免**:会话原文为中文、引用项目绝对路径属会话本性——tool/ 不适用
  本节的路径/CJK/内部术语项,由 §6 污染扫描门的校准电池替代(API key/其他树词汇/
  树代号/历史材料引用为致命)。
- frozen `.log` 永不编辑(证据完整性)。
- **递枪句电池**(Q5/Q6/Q10 重点):to have (skipped|set|run|loaded) / bounded to out-of-tree / only if firmware / requires the platform / requires custom|modified firmware / if the operator / outside this finding 等把前置归因于攻击者以外角色的措辞——命中即 FAIL。前置要么是交付现实(引 file:line),要么是攻击者自己的动作(写成正向步骤);两者都不是 = 包未闭合,不投。

### 3.2 防御性措辞(涉树版本表述)
- 只许用既定句式:跨代特性在场披露("Line numbers refer to the current development
  generation of the design tree, where this feature set is present; the exploit package
  guards on the characteristic content lines cited above and fails fast on any tree that
  does not contain them.");本代机制限定("on this tree generation …")。
- 绝对禁止:树代号、版本对比暗示(newer / older / compared to / differs from)、
  任何暗示第二棵树存在的措辞——"generation" 一词是唯一允许的抽象层。

## 4. 系统叙事(Q14-16 固定模板)

- **工具名(统一)**:firebud_multiagent_bug_hunter。统一口径:our self-developed
  multi-agent cluster and harness system;Q14 开篇句、Q16 括注、Q24/Q25 提及处一致。
- **架构一句话**:自研多 agent 集群与 harness 系统——LLM agent 在挖掘侧高自主决策
  (选靶/假设/测试编写),harness 在验证侧完全确定性(固定断言、双臂因果对照、
  全新目录复跑);**LLM 从不判定 pass/fail,判定权在确定性测试**;人工审阅后才投递。
- **工具主张(完整证据口径)**:自研工具首用 +100;逐 bug 自动检出 +5。每包 tool/ 目录
  含 §6 全套证据;Q24 明确指向 tool/ 完整归档(全部 prompts 与 responses 在彼处)。
- 纪律:工具列了必须给全证据,否则没收加分且 -5。

## 5. CWE 速查表(reporter 起点,逐 bug 复核官方定义)

| 缺陷类 | 起点 CWE |
|---|---|
| 寄存器/存储残留、清除失效 | CWE-1239 (Improper Zeroization of Hardware Register) |
| 锁/REGWEN 语义被绕过 | CWE-1233 / CWE-1234 (Hardware Internal or Debug Modes Allow Override of Locks) |
| 竞态/TOCTOU | CWE-362 (Race Condition) |
| 加密实现结构性缺陷 | CWE-1240 (Use of a Cryptographic Primitive with a Risky Implementation) |
| 物理侧信道/掩码失效 | CWE-1300 (Improper Protection of Physical Side Channels) |
| 硬件状态机逃逸 | CWE-1232 (Improper Locking) 或按资产改 I/C/A 类 |
| 复位/跨域不当时序 | CWE-1231 (Improper Handling of Undefined or Uninitialized Registers) |

(不确定时保守选通用类 CWE-284/CWE-200 系;判官查的是「合理 CWE」不是唯一解。)

## 6. tool/ 工具证据结构(收集器组装,禁止手工拷贝)

> **优先级裁定(运营方 2026-10-12)**:本节降级为可选参考。工具/LLM 披露=
> 模板填写环节——Q15-25 按 §3.0/§4 既定模板照填即可;tool/ 有则按本节结构,
> 无则不强求。**证据完备性不作投递门、不触发 REWORK/打回**(lint 检查 12 的
> 完备性项已降为 WARN)。投递成败只由三条核心门决定:攻击者角度可触发 /
> 前置非不可能 / exploit 准确(见 context.md「三条核心门」)。收集器与污染
> 扫描保留为可选工具;唯一仍硬性的例外=tool/ 内泄密(API key/树代号)=FAIL。

```
evidence/tool/
├── README.md          # 本 bug 的发现会话地图:哪个会话形成假设、哪个链验证、判据指针
├── architecture.md    # 系统架构+方法论(七门/双臂/判定权在确定性测试)+ 自带 key 复跑指南
├── prompts/           # 工单(task.md)+ agent 角色合同(agent.md 快照)+ 注入知识(knowledge/)
├── responses/         # 会话代表性节录 response-sample.jsonl(投递的提示
│                      # +首尾 assistant 记录,含 usage;全量会话只做 token
│                      # 计量与门扫描,不入包)
├── scripts/           # 战役编排 yaml + lint/judge-replay + PoC/exploit 脚本
└── tokens.txt         # 逐会话 input/output/cache 三元组,合计=Q23 数字
```

- **两阶段组装**(收集器 = `scripts/tool-evidence-collect.sh`):
  - `--phase discovery`:bug-planner 排链前运行——归集发现链会话
    (auditor/poc-runner),tokens.txt 即刻稳定,reporter 的 Q23 数字取自此处
  - `--phase full`:packager 导出前运行——追加验证链会话
    (report/verify/exploit/check);discovery 节数字不变
- **组装纪律**:只收与该 bug 的发现+验证直接相关的链路会话;由收集器从 run 目录与会话
  存储自动归集,经**污染扫描**后整体进 zip;禁止手工拷贝任何未扫描材料。
- **污染扫描门**(`scripts/tool-evidence-gate.sh`,lint 检查 12 自动调用):对 tool/ 内
  将打包材料做两档校准扫描——**致命项**:①API key/私钥材料与内部标记(树代号、
  历史结构标记、姊妹路径;标记清单存 workdir/lint-codenames.txt,不随包分发),
  逐文件原文扫描;②对比词汇(upstream/上游/独立词 diff/public repo/仓库 URL),
  只扫会话转录中 agent 生成文本与用户正文(工具结果回显、首条任务提示、
  compaction 摘要、prompts/ 与 scripts/ 的规则书原文按本性豁免)。命中 = **该 bug
  弃工具分主张**(bug 本身照投,Q15 降为 Simulation),绝不编辑会话原文、绝不手工
  修补。**豁免**:会话原文为中文、引用项目绝对路径(runs/工单路径)属会话本性,
  合法——tool/ 不适用 §3.1 的路径/CJK 项,以本门替代。
- 判官复跑口径:scripts/ 内含战役编排与运行说明;端点配置与自带 key 指南写在
  architecture.md。

## 7. 形态匹配与保真度(七门的证据侧,全流水线强制)

- **形态由 Q9 对手类别强制推导**(表见 context.md);reporter 写 Q26 描述时必须与
  exploit 实际形态一致;终审核对以官方指南 PDF 为准。
- **软件类 exploit = on-device 测试**(§2.2);模块级 TL-UL TB 可作 Q17 机制证据。
- **物理类 exploit = 攻击流+TB**:决策相关消费者真物例化;保真度表+能力映射表(§2.4);攻击动作只走外部引脚/接口,FI 前提禁止
  论文必含;TB 预置审计(reach-auditor 执)。
- **观测语义**:危害锚含完整架构响应(d_error、告警、状态位),与真实消费者决策依据一致。

## 8. 投递前提(七门;reporter 接单门槛)

- reporter **只接 PoC 判定词 = CHAIN-CLOSED 的单**(七门自述齐备、exploit 形态已定)。
- Q6 影响段以正向主张给出完整链;链上有洞 = 包未闭合,退回,不投。
- availability-only 影响(仅挂死)且无检测面被击败的独立论证 → 排队降级。
- **危害论证是核心**:危害=演示出的受保护资产损失,不是「机制存在」的换述。

## 9. zip 导出与提交前序(packager 职责)

1. lint 门:禁词+27 节完整性+判定词行+递枪句电池;FAIL→退回,不代改。
2. 导出:`<bug-id>_evidence.zip`(evidence/ 全量,含 tool/)、`<bug-id>_exploit.zip`
   (只含 README.md + src/)。
3. MANIFEST.txt sha256 纪律(每 zip 根一份);抽验 unzip -l 与目录态一致。
4. 提交前序:Q4 路径+行号+needle 树内核验 → 判官容器 fresh 目录 `make && make run`
   实测计时(judge-replay.sh)→ evidence/logs/ 换容器运行副本 → Q16 版本同步实测值 →
   lint 复跑 → 导出 → **人工投递**(表单一 bug 一份,投递永远人工)。
5. Rule 4:只读靶树;不引用外部 RTL 副本;不联网检索/对比公开版本;提交物证据靶内自洽。
