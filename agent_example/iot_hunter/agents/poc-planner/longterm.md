# poc-planner 跨 run 经验（longterm 种子 — 人工从各 run memory.md 晋升维护）

> 来源：AP1850 PoC 规划与复测（runs/20260915-095054 / 20260916-114743）

## 工单裁剪

- 严格按环境契约的 fidelity 定工单类型：full-system → network 工单；function-level → unicorn-harness（验证数据流，表述写"函数级仿真证实 X 未经滤到达 Y"，不写完整 RCE）
- 需认证的条目先确认环境有可用凭据（环境节"认证尝试结果"），否则降级或裁剪并记 decisions.md
- 一条 curl 能定性的问题优先（成链关键缺环：免认证可达性/参数是否被解析）

## 复测轮设计（环境修复后）

- 环境修复后要把此前 blocked 的全部重开一轮：blocked 的根因（dispatch gate、模块未加载）修掉后端点行为会变，旧结论全部要刷新
- 静态与动态分工：静态先定界（哪个参数可注入/截断边界），动态按界测试——AP1850 location 参数案例：静态发现 regDomain 被 strncpy(3) 截断但 location 不截断，动态一枪证实完整向量
- "参数向量复核"型遗留（上游发现某参数更优但未测）要开成独立复测工单，不要并进别的工单顺手做

## 证据移交

- 每个工单的 evidence 落 run 目录下独立文件，findings 条目引用文件路径
- 移交给 finalizer 时明确：哪些结论是终态（实证/证伪）、哪些 blocked 及 blocked 的根因是环境还是漏洞本身——影响报告分级
