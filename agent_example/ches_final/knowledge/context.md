# context — phase2 决赛 campaign(静态事实,注入所有节点)

## 任务
Hack@CHES'26 Phase 2 决赛:在**提供的设计**(=靶树,唯一参考)上挖掘可提交的安全 bug,
以完整攻击者链路验证并成链打包。比赛 2026-10-13 05:00 UTC 关闭;持续工作直到操作者叫停,
**不以时间为由降低任何验收标准**。

只有安全 bug 得分:使不受信代理**绕过已建立的安全特性**或**危害受保护 SoC 资产**的设计/
实现缺陷。功能 bug/lint/风格/推测性报告 = 无效,且每次无效提交在第 2 次之后 -5。

## 对手模型(官方四类,每份提交必须点名其一)
1. **Unprivileged software**——跑在 Ibex 用户态;可尝试提权或绕过反制
2. **Privileged software**——跑在 machine/supervisor 态;可瞄准更高权资产、其他硬件块或反制
3. **Physical attacker**——持有设备,可驱动外部引脚与接口(SPI/UART/USB/GPIO)。
   **能力清单是封闭枚举,不含故障注入**(D-r2-5 判官实战校准 2026-10-12:
   P2-07 FI 前提被裁 invalid——「没有证明指南中的物理攻击者能造成这个精确的
   内部故障」;stuck-at/位翻转/激光/EM/电压毛刺/时钟毛刺均不在授予能力内)
4. **Authorized debug**——可在生产设备上解锁并使用 JTAG 调试,以生命周期态允许的范围为限

## 攻击者链路标准(七门——每包投递前提,全流水线强制)
1. **对手诚实命名**:四类之一;链上每一步都在该类能力集内
2. **起点=交付现实**:初始状态=靶机引导流真实产物(ROM 后状态),或攻击者用自己能力内
   动作逐步造出的状态。**禁止假设性固件**——交付引导流没做的事就是没做
3. **被越过的边界已建立**:
   - 常设边界(硬件/规格级承诺,构造即生效,如「CSRNG 内部状态不可被软件观测」):
     需规格锚点(hjson SEC_CM/spec)+ 违反演示
   - 启用型边界(需固件上锁/使能的保护,如 REGWEN):需交付引导流**实际启用**的
     file:line 证据;没人上过的锁,绕过它不算绕过
4. **攻击侧能力映射显式化**(物理类):攻击流每一步映射到类 3 授予的能力(驱动哪个
   外部接口、什么时序),能力映射表入 README;对照臂显示同一接口刺激在无缺陷路径/
   无前置状态时门保持关闭。**攻击侧 FI 前提=能力集外=invalid**(见对手模型节)
5. **触发=对手可执行**:软件类的触发=设备上运行的攻击者程序本身;物理类=TB 顶替
   攻击者真实拥有的引脚/接口驱动,链内软件步骤归属正确(交付固件的动作用真实引导流
   或 file:line 证明复现);**攻击链从攻击者视角真实触发,无中间 mock/伪造**
6. **观测取完整架构语义**:危害锚必须含真实消费者会据以行动的全部信号(d_error、告警、
   状态位);只捕 d_valid+d_data 不算证明
7. **模型保真度**:决策相关模块(其行为决定安全结果者)必须真实 RTL;非决策模块可建模,
   但必须在 exploit README 保真度表中列明并论证「换真物结论不变」

**判定词契约**:PoC 阶段四值——`CHAIN-CLOSED`(七门全闭,可进 exploit)/
`MECHANISM-ONLY`(机制成立但链断——降级 [minor],不得进链)/ `REFUTED` /
`CONSTRUCTIVE-IMPOSSIBLE`。**reporter 只接 CHAIN-CLOSED 的单**。

## 形态匹配(指南硬规则)
| 攻击者类别 | exploit(50 分)必须形态 |
|---|---|
| 1/2 软件类 | **on-device 测试**:sw/device/tests 风格 .c + Bazel 构建(独立目录进树,不改既有文件) |
| 3 物理类 | 攻击流 + TB(攻击动作只走外部引脚/接口)+ 保真度表 + 能力映射表;FI 前提禁止 |
| 4 授权调试 | on-device 调试会话或忠实建模它的 TB |

「外部 TL-UL TB + 软件类对手」= 形态违规。模块级 TL-UL TB 可作 Q17 机制证据,
永不为软件类的 Q26 exploit。

## 计分与规则事实
- unique bug 60(确认 5+影响与证据 5+exploit 50)/ variant 3 / exploit-variant 15
- **三条核心门(运营方裁定 2026-10-12,投递成败只看这三条,任何一条不过=不投)**:
  ①**漏洞必须从攻击者角度可以触发**——链上每一步都在对手被授予的能力集内
  (见对手模型节),不许中间 mock/伪造;②**前置条件不是不可能的**——攻击者可造
  或交付态固有,递枪句一票否决;③**exploit 必须准确**——精确复现危害链,
  判官 fresh 重放可得 EXPLOIT_SUCCESS。七门是这三条的操作化
- **工具/LLM 披露=模板填写环节(同裁定)**:Q15-25 按既定模板统一措辞照填即可,
  tool/ 证据完备性**不作投递门、不打回、不返工**;加减分由判官裁量,我方不为此
  耗费链上工时
- 自动化:自研工具首用 +100 / 存量工具首用 +50 / 自动检出每 bug +5(判官裁量项)
- **本队工具(统一名)**:firebud_multiagent_bug_hunter——自研多 agent 集群与 harness 系统
  (英文统一口径 our self-developed multi-agent cluster and harness system);
  Q15-25 模板措辞见 delivery-format.md §3.0/§4
- Rule 7:一 bug 一表单;Rule 8:队内重复 -2;≥10 提交且 >50% 无效 → 判官可停审;
  无效第 1/2 次宽容其后每次 -5
- **已投基线**:`workdir/SUBMISSIONS.md`(3 条已投根因一句话——新发现同根因不得重复提交)

## 树与环境(只读红线)
- **靶树(一切证据锚点)**:`/opt/opentitan` = 宿主符号链接 →
  `workdir/p2tree` = 提供设计的逐字节抽取(读树=审计,合规)
- **判官环境容器(三台等价)**:`docker exec hackches|hackches2|hackches3 …`
  (同一镜像,Verilator 4.210 + /opt/opentitan 原树)。**选台用挑闲器**:
  `C=$(bash scripts/docker-pick.sh)`(指标=容器内重活进程数;全挂 exit 1 时停手记录)
- **on-device 轨(软件类 exploit 专用)**:容器内 chip 级 Verilator 仿真已全量预构建于
  bazel 缓存;实测 `bazel test //sw/device/tests:<t>_sim_verilator` ≈200s 跑通
  (含编译+仿真);新测试只需编译自身+链接,30 分钟预算余量巨大。装载方式:exploit/src
  放独立目录 `sw/device/tests/<slug>/{x.c, BUILD}`,Makefile 拷入树内新路径 →
  `cd /opt/opentitan && bazel test ...` → grep 锚点 → 判定词
- 开发迭代用宿主 Verilator 5.020;**验收轨=判官容器**(Verilator 4.210)fresh 目录
  `make && make run` 复跑;Q16 与 environment.txt 同步实测版本;墙钟 ≤30min
- **Rule 4(决赛红线,破规=扣分或取消资格)**:提供的设计是唯一参考。禁与 OpenTitan 或
  任何公开 RTL 对比(diff/哈希/片段检索);禁联网检索公开版本;禁读任何外部 RTL 副本。
  一切主张只以靶树 file:line 锚定

## 靶树形状事实(实测,全 agent 共享)
- top 拆 power-domain 包装:`earlgrey_pd_aon.sv`/`earlgrey_pd_main.sv`——u_rom_ctrl、
  u_entropy_src、u_pwrmgr 等实例从 top_earlgrey.sv 迁入 pd 文件(csrng otp_en 广播在
  pd_main:778/807/2295;u_rom_ctrl pd_main:2498;u_pwrmgr pd_aon:198)。引 top 旧行号
  一律失效,按 pd 文件锚
- autogen 域命名:`Domain0Sel/Domain1Sel` → `DomainAonSel/DomainMainSel`
  (实例 u_d0_*/u_d1_* → u_daon_*/u_dmain_*;cnsty_chk_errs 索引保号、增域维)
- `chip_earlgrey_cw310.sv` 不存在(top 变体仅 asic/cw340/verilator)
- otp:`PartInvDefault` → `RndCnstPartInvDefault`(otp_ctrl.sv:39);part_buf digest 导出
  `data[$high(data)…]`(:855);DAI ZEROIZE 特性在树内(top_earlgrey/ip_autogen 路径);
  AES 顶层参数 AESGCMEnable="0"(top_earlgrey.hjson:832 → earlgrey_pd_main.sv:54/:2059,
  SW 写 MODE.GCM 静默降级 AES_NONE,aes_ctrl_reg_shadowed.sv:93-94)
- flash 密钥种子:`flash_addr_key_seed` → `nvm_addr_key_seed`(otp_ctrl.sv:1501,
  flash_ctrl+rram_ctrl 双 NVM 共用);keymgr 与 keymgr_dpe 并存
- `entropy_complex_init(void)` → `(hardened_bool_t fips)`(sw/device/lib/runtime/entropy.c:1076)
- chip 级 Verilator 仿真**无内部信号暴露**(全树无 --public-flat-rw):内部网不可触,
  任何"内部网故障注入"都只能出现在自建 IP 级 TB 上——而那属于攻击者没有的能力,
  D-r2-5 起一律不投

## 审计方法论(攻击者第一视角)
- **座椅在攻击者一侧**:不是「发现可疑代码→反推谁能利用」,而是「我是交付设备上的对手 X,
  我能走到哪」。每次审计的第一工件=**交付现实基线**:ROM 引导后哪些锁上了/没上
  (rom_start.S/owner 引导流 file:line)、lc/OTP 是什么态、什么在跑
- 猎杀面:SEC_CM 声明(hjson)→ RTL 实现逐条对照;doc/theory_of_operation 承诺与实现
  偏差;状态机复位值/默认放行/锁语义/同步器缺失/常量绑定;高价值 IP 优先
  (Ibex/密码块 AES·OTBN·KMAC·HMAC·CSRNG·EDN·entropy_src/keymgr/lc_ctrl/otp_ctrl/
  flash_ctrl/rom_ctrl/alert_handler/rstmgr/pwrmgr/外设)
- 每个发现必须当场写成完整攻击叙事(七门自述);写不全=[minor] 记录,不进链
- PoC 断言=「密钥可读回/绕过达成/秘密跨界/遏制窗突破」级别的资产后果,
  禁止「行为差异」断言

## 载体工艺(TB 与 on-device 车辆)
- 黄金样例:`knowledge/sim-craft.md`(契约:Verilator TB、TL-UL 真事务、固定数值锚点、
  attack/secure 双臂因果对照、树内固有行 needle 守卫、判定词恒为 stdout 最后一行且
  恒 exit 0)
- **TB 双版本可移植**:新写 TB 一律 classic-scheduling 形态(无 `--timing`,C++ 步进时钟)
  ——宿主 5.020 与容器 4.210 双可编译,容器验收零转换成本
- 细节手册:`knowledge/sim-craft.md`

## 交付契约
- 包结构/口径:`knowledge/delivery-format.md`(硬契约:27 问逐字段要求+两 zip+
  make-package+禁词 §3.1+工具证据结构)
- lint 电池:`scripts/lint_pkg.sh`;容器验收:`scripts/judge-replay.sh`
- 投递台账:`workdir/SUBMISSIONS.md`
- **投递永远人工**(Google Form 一 bug 一表单);agent 只产出包与建议

## 红线
- 靶树只读;容器只读(判官 scratch 除外);禁网络(容器内需网络时经 172.17.0.1:7890,
  仅构建用途)
- 无安全影响的发现不立项;打分存疑显式标 RISK
- API key 绝不进任何产物;台账/判决书绝不进 zip;tool/ 工具证据(工单/合同/会话转录/
  脚本/token)经收集器污染扫描后整体进 zip(见 delivery-format §6),禁止手工拷贝
  任何未扫描材料
- 提交物证据靶内自洽:只引用靶树 file:line,只描述靶内可复现行为

## 路径与容量
- **战役根**:`<project-root>`(仓库中的独立示例目录;运行数据保存在 workdir/runs)
- 战役主 DAG:`flow.yaml`(单 campaign 节点);轮次流水线:`pipelines/`;
  链式子流水线由 bug-planner 写 `runs/<run根>/plan/bug-batch-N/flow.yaml`
- 共享台账:`workdir/FINDINGS.md`(追加制,署名节点;[major]=七门自述完整的攻击叙事,
  [minor]=不完整观察)
- 32 核 / 31GB RAM;模块级构建量级 1–3 min、1–3GB/实例;并发护栏:同时活跃链 ≤6;
  sweep 波次 ≤ env.md 容量(默认 3)
- 机器时间=UTC;比赛 2026-10-13 05:00 UTC 关闭(仅作事实记录,不构成赶工理由)
