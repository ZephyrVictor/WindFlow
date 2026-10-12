# spec-map — 规范一致性假设源(attack-ledger 源②底料)

一致性审计 = **实现 vs 权威材料**。实现与自家规范文档/寄存器权威定义的
错位是最锋利的杠杆之一。本文件枚举权威材料与检查类型;poc-planner 轮首
按「模块×检查类型」登记进 workdir/attack-ledger.md 的 UNTRIED 行。

## 合规口径(先读)
- 权威材料仅限:①靶内自带文档/规范数据 ②公开 ISA 标准(RISC-V 手册)
  ——**不与任何外部 RTL 副本对比**(Rule 4);一切主张以靶树 file:line
  锚定,报告措辞靶内自洽
- 内部假设源登记与工单流转带 INTERNAL ONLY 标注

## 权威材料清单(靶内实存路径)
| 类 | 路径 | 内容 |
|---|---|---|
| IP 自描述 | `hw/ip/<mod>/doc/{theory_of_operation.md, registers.md, interfaces.md, programmers_guide.md, checklist.md}` | FSM 状态图/行为契约/接口语义 |
| **寄存器权威定义** | `hw/ip/<mod>/data/<mod>.hjson` | 字段权限(RW/RO/W1C)、复位值(resval)、shadow、宽度——autogen reg_top 的生成源 |
| **对策声明** | `hw/ip/<mod>/data/<mod>_sec_cm_testplan.hjson` + hjson SEC_CM 列表 | 每个 IP 声明的 security countermeasure 清单 |
| ibex 手册 | `hw/vendor/lowrisc_ibex/doc/`(02_user CSR 文档、03_reference/security.rst 等 .rst) | 核内文档;CSR/PMP/异常另对照公开 RISC-V 特权规范 |
| prim 手册 | `hw/ip/prim/doc/prim_*.md` | 共享基元契约 |
| 顶层规范 | `hw/top_earlgrey/doc/{datasheet.md, design/}`、`hw/top_earlgrey/ip/xbar_main\|xbar_peri` | 集成/互联契约 |

## 检查类型(登记粒度)
| 型 | 检查什么 |
|---|---|
| A reg-spec conformance | hjson 字段定义 ↔ reg_top/reg_pkg 实际行为(权限位/复位/shadow 语义/越界回卷);模板与 autogen 错位 |
| B CSR/ISA conformance | ibex CSR 编码、PMP 字段布局、异常/特权语义 vs 公开 ISA 规范与 02_user 文档 |
| C FSM conformance | doc 状态图 ↔ RTL FSM:未文档化转移、default 臂行为、未达态 |
| D countermeasure conformance | SEC_CM 声明的对策 ↔ RTL 实装:声明未接、接错信号、参数空转 |
| E 参数 conformance | doc/模板参数语义 ↔ top 实际传参 SecXxx(默认值/覆盖链) |
| F 接口 conformance | interfaces.md 握手语义(ready/valid/credit)↔ RTL;跨域校验缺失 |

## 登记与耗尽
- 每行 = 模块 × 检查型(可再细到寄存器组/状态机/对策条目);轮首登记
  UNTRIED,波次消耗后标 EXHAUSTED(产出位点或阴性,带指针)
- 优先级:ibex ISA 面(B)> lc_ctrl/otp/keymgr 高资产 A+C+D > 全 scope
  D(sec_cm 逐条核对,机械但覆盖广)> 其余
- 阴性结果也是产出(耗尽记录防止下轮重扫)——这正是 attack-ledger 的意义
