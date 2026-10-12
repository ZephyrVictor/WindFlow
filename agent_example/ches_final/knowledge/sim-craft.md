# sim-craft — 仿真与 on-device 测试配方(verifier/exploiter/env-setup/poc-runner 共用)

**双轨**:开发迭代=宿主 Verilator 5.020(fresh 目录,可并行多实例);**验收轨=判官环境
容器**(三台等价 hackches/hackches2/hackches3,选台 `bash scripts/docker-pick.sh`;
Verilator 4.210 + /opt/opentitan 靶树)——PoC 判定词、exploit 验收、终态 evidence 一律以
容器 fresh 目录 `make && make run` 复跑为准。**新写 TB 一律 classic-scheduling 形态**
(无 `--timing`,C++ 步进时钟):5.020/4.210 双版本可编译,容器验收零转换成本。

**on-device 轨(软件类 exploit)**:容器内 chip 级 Verilator 仿真全量预构建于 bazel 缓存;
`bazel test //sw/device/tests:<t>_sim_verilator` 实测 ≈200s(含测试自身编译+仿真)。
新测试只编译自身+链接,30 分钟预算余量巨大(配方见 delivery-format §2.2)。

## 干净源纪律(一切会话与产物的出生约束)
- 只读靶树;一切主张以靶树 file:line 锚定。
- 不提及、不引用、不暗示任何其他 RTL 副本或公开版本;不做任何对比操作(Rule 4 红线)。
- 会话与产物从第一行起就是可提交字节:无内部编号、无内部路径、无过程叙事。

## 基本调用(IP 级 TB)
```bash
verilator -sv --cc --exe --build \
  -Wno-fatal -Wno-WIDTH \
  --Mdir <构建目录(全新,不复用)> \
  -I<模块 rtl 目录> [-I<prim 目录> ...] \
  --top-module tb \
  <tb.sv> <sim_main.cpp> [stub_pkgs.sv] \
  -G<参数>=<值>
```
- 快速冒烟(auditor 用):`verilator --lint-only -sv -I<rtl 目录> <模块文件>` 秒级
- 成本实测:`/usr/bin/time -v <命令>` 取 Elapsed / Maximum resident set size

## classic-scheduling 模板要点(免 --timing)
- sim_main.cpp 主循环显式步进时钟(toggle clk_i + eval),时钟周期由 C++ 计数控制;
  复位序列 = 驱动 rst_ni 若干拍后释放;
- TB 内不依赖 SystemVerilog 定时结构(fork/wait/#delay);所有时序由 C++ 驱动;
  `$finish` 由 C++ 在判定行打印后调用,保证判定词是 stdout 最后一行;
- 物理动作(复位毛刺/单点故障)的仿真等价 = C++ 在指定拍直接驱动目标网若干拍,
  属于物理 FI 的 testbench 建模,须在 TB 头注释与 README 如实申报。

## 四行协议(PoC 会话日志)
```
attacker_action:         <攻击者做了什么>
expected_secure_behavior:<安全设计下应发生什么>
observed_behavior:       <实际观察到什么>
RESULT: PASS|FAIL
```
- PASS 语义 = **安全性质被破坏被实证**(observed 偏离 expected_secure 且偏向攻击者)
- 判 PASS 用日志行匹配(`grep -q 'RESULT: PASS'`),不解析中间输出

## 靶源守卫(每次运行必带)
tb 内 `source_is_target()` 函数:grep 靶树中该模块的特征行(如某信号声明的精确文本),
守卫未命中 → 直接出 FAIL 判定词正常退出。防止跑错树/文件被误改;守卫命中要在日志打印
一行证据。

## -G 双参数(causality 证明的标准手法)
- tb 顶层参数化双臂(`-GTARGET_<NAME>=1/0`):**attack 臂**(原样被测树,缺陷在)/
  **secure 臂**(缺陷屏蔽参照),两臂各跑一次
- attack 臂=缺陷行为、secure 臂=安全行为 → 证明「是这个缺陷导致这个行为」
- 不适用(如结构级删除)时:开关改为旁路注入/force,或在 verify.md 说明为何不适用
- **措辞红线**:提交物内绝不出现 植入/implant 字样——双臂就叫 attack 臂/secure 臂,
  不带任何补丁指涉

## IP 级 TB + TL-UL 真事务
- 载体为总线接口的 IP,激励一律走靶内 `tlul_adapter_host`(或等价真总线路径)发真
  TL-UL 事务(含 cmd_intg/data_intg),不直接 force 寄存器 internals
- **观测语义完整**:危害断言必须检查完整架构响应(d_valid **且 d_error=0**、告警状态、
  ERR_CODE/状态位),只捕数据不查错误位不算证明
- **固定数值锚点**:断言=具体数值(密文块/tag/计数器读回/相位驻留拍数),不写「行为与
  参考模型一致」类模糊断言;锚点值从 published 向量或独立软件模型校准

## make-package 契约要点(详见 delivery-format §2)
- 判定词 = stdout 最后一行、独立成行、逐字匹配;`make run` 恒 exit 0;无 token 退出 =
  最严重事故,所有异常路径必须 trap 后打 FAIL 判定词再退出
- 树内固有行 needle 守卫 fail-fast(见上)
- prim_shim 自包含内嵌于 src/;零新依赖(纯 verilator + bash + coreutils)
- stub 控构建半径:只拉目标模块 rtl + 直接依赖;构建半径失控时补 stub,不是加 -I;
  stub 顶部注释「只服务 tb 编译,非靶源」
- 墙钟门:make 起到 make run 止 ≤30min,本地 fresh 目录实测计时

## on-device 测试配方(软件类 exploit 车辆)
- 测试 .c 用树内 DIF 库(dif_<ip>.h)写攻击者动作:配置寄存器→触发→经 DIF/CSR 读回
  观测资产危害;测试即攻击者(跑在 M 态=privileged software 类,或自行降 U 态=
  unprivileged 类)
- BUILD 仿 `sw/device/tests/BUILD` 既有 sim_verilator target 形态(on_device_test +
  sim_verilator suite);独立目录 `sw/device/tests/<slug>/`,不改任何既有文件
- Makefile:`make` 拷入树内 → `make run` = `cd /opt/opentitan && bazel test
  //sw/device/tests/<slug>:<t>_sim_verilator --test_output=streamed`,grep 关键锚点行
  (PASS/FAIL 判定锚)后打 EXPLOIT_SUCCESS/FAIL,恒 exit 0
- 引导后状态=交付现实:测试从 ROM 引导完成后起步,若攻击需要的状态引导流没给,
  测试必须自己用能力内动作造出(这正是环2/环3 的运行中实证)

## 产物规范(提交物的一部分)
每次运行保留三件:完整命令行 / stdout 日志 / exit code。全新目录重跑通过才算验收。

## 本地执行纪律(poc-runner/verifier/exploiter)
- 构建目录用 fresh 短路径(/tmp/poc/<id>-<attempt>),不复用旧构建产物
- 长任务 setsid nohup 后台 + 周期看日志,别阻塞交互
- 成本量级参考:模块级构建 1–3 min、1–3GB/实例;on-device bazel 测试 ≈3–5 min
- Verilator 5.020 已知坑:force 后线程退出→静默丢失(须挂起);prim_assert 走 dummy
  (tb 显式重算断言属性);--timing 下 $finish 不中断其余线程(故用 classic-scheduling);
  重复 case 标签完全静默

## 提交物措辞与路径纪律(verifier/exploiter 每次交付自查)
- needle/守卫注释只写「needle 为靶内固有行/端口名」
- 因果对照、tb 注释、README、verify.md 一律用 attack 臂/secure 臂术语
- 提交物内不出现本机绝对路径:靶树路径以 `$TARGET_ROOT` 变量书写,交付物内文件用包内
  相对路径
- 禁词全集见 knowledge/delivery-format.md §3.1;lint 电池 =
  `bash scripts/lint_pkg.sh <staged/<bug-id>>`(phase2 战役根)
