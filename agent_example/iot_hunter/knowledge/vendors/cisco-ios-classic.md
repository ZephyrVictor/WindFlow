# 厂商条目：Cisco Catalyst 经典 IOS（MZIP 单体，12.x/15.x）

## 适用特征

- Catalyst 交换机固件：`*.tar` 内含 MZIP bin（header + 内嵌 zip 压缩层）
- httpd/SNMP/CLI 解析器全部编译进同一镜像（无独立服务二进制），IOS 进程调度器以"进程"形态运行
- 架构 PowerPC 大端（ppc-be），stripped 非 ELF；**加载基址按版本两档：12.x = 0x0000300，15.0 = 0x01000000（vaddr = 文件偏移 + 基址）**
- 已验证实例（三代）：c2950 12.0(5)WC1（2001）、c3550 12.1(22)EA1（2004）、c3750 15.0(1)SE（2010）

## 症状（分析时）

- 系统工具全线不可用：`objdump` 无 PPC 支持、radare2 ppc 插件解码错误（`addi` 误判 `stwu`）
- Dynamips 系不支持 3550/3750 PPC 平台 → 无成熟模拟器路由

## 解法

### 解包链

`tar -xf` → MZIP bin → 压缩层解压 → 原始 PPC-BE 镜像 + html/（Web 管理界面，纯客户端静态页）。**压缩层与基址按版本**：12.x = zip 层（python zipfile / unzip），文件偏移 = vaddr − 0x3000；**15.0 = bzip2 层**，文件偏移 = vaddr − 0x01000000。

### 反汇编：capstone 是唯一可用路线

`python capstone 5.0.6`（`Cs(CS_ARCH_PPC, CS_MODE_32|CS_MODE_BIG_ENDIAN)`，skipdata=True）。函数定位 = `strings -n 6 -t x` 锚点 + xref 工具（lis+addi 常量对扫描）：12.x 配方 `runs/20260919-091036/plan/tools/xref.py`；**15.0 配方 `runs/20260919-183124/plan/tools/xref3750.py`（两级解析：IOS 15.0 字符串多经数据段指针表间接引用——串 vaddr → 指针表项 → 引用代码，`-s` 默认做两级）**。

**内存红线（c3750 实战教训，三次 OOM 换来的）**：capstone 脚本**绝不 `md.disasm` 整个镜像 buffer**——56MB 级镜像全量反汇编的 Instruction 对象列表会吃 20-25GB RSS，直接触发内核 OOM 杀进程（连杀 agent 会话与 API 网关）。c3550 的 8.5MB 能扛是运气不是理由。纪律：① 先 `strings -t x` 锚点定位，只对目标函数 ±窗口（≤1-2MB）反汇编；② 流式逐条处理（for ins in md.disasm(...) 内联判断，不收集大列表）；③ 中间产物（锚点表/xref 表）写文件复用，不堆内存或上下文。

### 流水线形态：静态终轮

无模拟器 → 静态证据收尾，reporter 任务声明"**本轮为静态轮，报告即终判**"。置信度措辞忠实转述 correlator 结论（确认(静态)≠动态验证；高度可疑/推测不得升级）。yaml 模板：`flow-c3550.yaml`（unpacker[gate]/planner/correlator/reporter[gate] 四节点）。

## 家族签名清单（新 IOS 固件最高优先 hypotheses）

c3550 12.1(22)EA1 反汇编级确认的同族缺陷，**c3750 15.0(1)SE（2010）已逐条回归，三代命中率见下表**。审计同家族新目标时直接按此清单开 hypotheses 优先验证：

| 签名 | 机制 | c3550 判定（2004） | c3750 15.0(1)SE 终判（2010） |
|---|---|---|---|
| **#2 $-name 展开栈溢出**（跨代确认） | `$` 后 name 收集无界（stb 循环无检查），saved LR 直控 PC；同位函数 `HTML: Built command '%s'` | Critical 确认（LR 偏移 132） | **存留 Critical**（LR @r1+0x9c 偏移 140，≥144B 全控 PC；SSI 侧同循环副本 0x10da7c8 已加界而 Web-CLI 副本 0x10d9838 未加 = 未修复实锤）——**12.x/15.x 全线最高优先** |
| #1 enable 空口令表静默授权 | 两表全空时 `li r3,1` 直接授权特权 15，先于 401 质询 | Critical 确认 | **已修复（fail-closed 三层）**——仅 12.x 目标适用 |
| #3 /wildcard/ $-marker 无界拷贝 | marker 段拷贝退出条件仅"非转义 /"，无 NUL/长度检查 | High 确认 | **已加界（254B 上界 + 专属错误串）**；激活机制换皮为 magic token（GET 专属）——签名匹配跟机制不跟字符串 |
| #4 /LEVEL/ 大小写不敏感预认证重定向器 | 注册于 httpauth 之前的 cluster 重定向 | Low 推测 | 代码存留但漏洞行为不存留（无 grant，认证保留；双 timetag fail-closed） |
| #5 %00 URI 原地截断 | 解码后 memmove 左移，截断串继续下发 | Low | 机制存留，双视图分裂消失（单一 strdup 规范化）——Low 维持 |
| （附）Host 头 off-by-one | malloc(0x80)+strcpy | 确认 | 不存留（15.0 无 Host 解析分支） |

**15.0 代最强组合已换代**：c3550 时代"签名 #1 × #2 = 出厂态预认证 RCE"的根（#1）在 15.0 被关闭；15.0 代的预认证根换成 **Smart Install TCP 4786**（见新签名）。#2 仍是唯一 httpd Critical，同一函数存活 6 年未修（修复只落在输出侧堆缓冲，name 收集栈缓冲未动）。

### 15.0 代新签名（c3750 实证，2010 代码基起最高优先）

| 签名 | 机制 | c3750 判定 |
|---|---|---|
| **Smart Install 4786 头部续读堆溢出** | conn = malloc(0x40) 头体同居；期望长字段被报文声明长 L 覆写后才用于续读 `recv(fd, conn+0xc+rcvd, L−rcvd, 0)`，字段校验在完成时才执行——L>16 受控溢出 ~6.9KB、L<16 无符号回绕无界写；16B 头分两段即触发，无握手无凭据 | Critical（CVE-2018-0171 族补丁前形态；溢出本体确认，出厂态默认监听为唯一待动态确认点——hulc 回调槽 [0x45d4e88]+0x74 运行时注册） |
| Smart Install type-5 无认证配置外传 | word2=5 消息 → `system:/running-config` 发往报文指定 tftp，零凭据 | High 确认（CVE-2017-3881 族） |
| Smart Install 导演器硬编码凭据模板 | `enable password cisco` / `username cisco` / `do telnet %i %d` @file 0x3024538-0x302458a | minor（client 被动接受导演器下发） |
| httpauth 直通 authz 死标志 | state->0x2d8 非零可跳过 granted>=requested 检查；当前全镜像无写入者 = 死代码 | 记录同型守卫缺口——**后续版本若引入 0x2d8 写入者即成认证旁路** |

**跨协议组合链（15.0 代）**：4786 type-5 外传 running-config → 提取凭据 → httpd Basic → $-name 溢出 RCE（level 1 即可）或 Web-CLI 全权（level 15）——"信息泄露 → 已认证 RCE"完整链，预认证根在 4786。

### 代际趋势数据（已完结：c2950 2001 → c3550 2004 → c3750 2010）

修复落点规律：①根缺陷类先修（认证静默授权 fail-closed 重写、Host 分支整体消失）②针对性界带专属错误串（#3 "…during substitution"）③修复按调用面逐个落（SSI 副本加界而 Web-CLI 副本未加）——**同型循环的副本审计法**（一有一无即加固证据）④老签名换皮存留（/wildcard/ → magic token）⑤新代新面接棒（15.0 最高危 = Smart Install，非 httpd 家族签名）。**副本审计法与"跟机制不跟字符串"两条方法论适用于一切后续家族回归。**

## 死路

- Dynamips 不支持 3550/3750 平台；自建 QEMU ppc-be 用户态仿真风险高（inventory rehost 路由结论）——不要尝试动态轮，直接静态终轮
- CVE-2001-0537 同型（/level/16-99 越界 level）在 12.1(22)EA1 **已修复**（level token 严格 1-2 位 digit，fail-closed）——不要重复开此 hypothesis，除非目标版本明显更老
- radare2 ppc / objdump 路线已证不可用，直接上 capstone

## 溯源

- c3550 静态轮 `runs/20260919-091036`（8 VULN 终判报告 `runs/20260919-091036/artifacts/report.md`）
- c2950 首轮（流水线方法学验证，5 候选/2 RCE 链）
- **c3750 静态轮 `runs/20260919-183124`**（7 VULN 终判：Smart Install 4786 堆溢出 Critical + $-name 溢出 Critical 存留；子 run `runs/20260919-193149` 4 工单；报告 `runs/20260919-183124/artifacts/report.md` §3 为本节命中率数据来源）
- c3750 实战增量：15.0 字符串两级指针解析（xref3750.py）、56MB 镜像分窗反汇编内存红线（见上文）、httpd 代码区三簇分布（0x25c-0x261 解析/认证、0x10d9-0x10dc Web-CLI/SSI、0x3379 http_parser）
