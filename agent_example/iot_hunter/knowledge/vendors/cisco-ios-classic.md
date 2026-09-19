# 厂商条目：Cisco Catalyst 经典 IOS（MZIP 单体，12.x/15.x）

## 适用特征

- Catalyst 交换机固件：`*.tar` 内含 MZIP bin（header + 内嵌 zip 压缩层）
- httpd/SNMP/CLI 解析器全部编译进同一镜像（无独立服务二进制），IOS 进程调度器以"进程"形态运行
- 架构 PowerPC 大端（ppc-be），stripped 非 ELF，加载基址 0x00003000
- 已验证实例：c2950 12.0(5)WC1、c3550 12.1(22)EA1；待验证：c3750 15.0(1)SE

## 症状（分析时）

- 系统工具全线不可用：`objdump` 无 PPC 支持、radare2 ppc 插件解码错误（`addi` 误判 `stwu`）
- Dynamips 系不支持 3550/3750 PPC 平台 → 无成熟模拟器路由

## 解法

### 解包链

`tar -xf` → MZIP bin → zip 层解压（python zipfile / unzip）→ 原始 PPC-BE 镜像 + html/（Web 管理界面，纯客户端静态页）。**地址约定：文件偏移 = vaddr − 0x3000**。

### 反汇编：capstone 是唯一可用路线

`python capstone 5.0.6`（`Cs(CS_ARCH_PPC, CS_MODE_32|CS_MODE_BIG_ENDIAN)`，skipdata=True）。函数定位 = `strings -n 6 -t x` 锚点 + xref 工具（lis+addi 常量对扫描，配方在 `runs/20260919-091036/plan/tools/xref.py`，用法 `python3 xref.py -s '<子串>'`）。

### 流水线形态：静态终轮

无模拟器 → 静态证据收尾，reporter 任务声明"**本轮为静态轮，报告即终判**"。置信度措辞忠实转述 correlator 结论（确认(静态)≠动态验证；高度可疑/推测不得升级）。yaml 模板：`flow-c3550.yaml`（unpacker[gate]/planner/correlator/reporter[gate] 四节点）。

## 家族签名清单（新 IOS 固件最高优先 hypotheses）

c3550 12.1(22)EA1 反汇编级确认的同族缺陷，审计同家族新目标时**直接按此清单开 hypotheses 优先验证**：

| 签名 | 机制 | c3550 判定 |
|---|---|---|
| enable 空口令表静默授权 | 未配置认证方式默认 enable + 两张口令表 [level..15] 全空 → `li r3,1` 直接授权特权 15，**先于** Authorization 头检查与 401 质询 | Critical 确认 |
| $-name 展开栈溢出 | `$` 后 name 收集无界（stbx 循环无检查），saved LR @ 偏移 132，≥136B 全控 PC；多 token 以 `.` 拼接绕过单 token 128 上限 | Critical 确认 |
| /wildcard/ $-marker 无界拷贝 | marker 段拷贝退出条件仅"非转义 /"，无 NUL/长度检查，越过 URL 尾继续读堆 | High 确认 |
| /LEVEL/ 大小写不敏感预认证重定向器 | 注册于 httpauth 之前的 cluster 重定向 | Low 推测（组合未验） |
| %00 URI 原地截断 | 解码后 memmove 左移，截断串继续下发 | Low（路径分裂未验） |

最强组合：**enable 空口令 × $-name 溢出 = 出厂态设备等效预认证 RCE**。enable 空口令是整棵攻击树的根——它把全部 post-auth 面在出厂态整体转预认证。

家族趋势数据：c2950(2001)→c3550(2004)→c3750(2010)，逐代验证签名存活情况，命中率回写本条目。

## 死路

- Dynamips 不支持 3550/3750 平台；自建 QEMU ppc-be 用户态仿真风险高（inventory rehost 路由结论）——不要尝试动态轮，直接静态终轮
- CVE-2001-0537 同型（/level/16-99 越界 level）在 12.1(22)EA1 **已修复**（level token 严格 1-2 位 digit，fail-closed）——不要重复开此 hypothesis，除非目标版本明显更老
- radare2 ppc / objdump 路线已证不可用，直接上 capstone

## 溯源

- c3550 静态轮 `runs/20260919-091036`（8 VULN 终判报告 `runs/20260919-091036/artifacts/report.md`）
- c2950 首轮（流水线方法学验证，5 候选/2 RCE 链）
