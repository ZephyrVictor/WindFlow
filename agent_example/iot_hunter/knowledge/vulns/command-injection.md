# 漏洞类型：命令注入验证方法论

## 适用特征

静态审计指向 shell 拼接 sink：`system()` / `popen()` / `os/exec.Command("sh","-c",...)` / `run_system` 封装。目标 = 把"静态注入主张"升级为执行级实证。

## 症状

- 服务有响应但无法区分"参数被解析"与"命令真执行"
- stub 环境里回显通道不确定（响应体/日志/串口哪个能取证）

## 解法

### 取证档位（从弱到强，报告必须写清用的是哪一档）

1. **计时盲注**：`;`/`|`/`$()` 元字符 sleep vs 空格对照
2. **not found 回显**：串口/日志出现 `/bin/sh: X: not found`（证明拼接发生）
3. **console 回传**：payload 附加 `>/dev/console` 把输出打到串口（`;busybox id >/dev/console`）——比 not found 强一档，能证明"执行成功"
4. **do_execve 串口全文（最强）**：QEMU 内核 `print-fatal-signals=1` + execve 追踪，串口直接出现 `do_execve[PID]: argv: /bin/sh -c <完整命令串>` + 后续 `uid=0(root)` 输出——payload 原样进命令串 + root 真实执行一次到位

### 三判据（执行级实证的完备标准，缺一不可）

1. **payload 原样进命令串**（do_execve 全文或等价证据）
2. **uid=0 + marker 真实执行**（payload 带 `id;echo XnMARK;`，marker 在串口出现且退出码 0）
3. **对照零出现**：纯 benign 参数（`plainvalue` / 正常 MAC）重放，`uid=`/marker 出现次数 = 0——排除"任何请求都跑命令"误判

### 实操技巧

- marker 每工单唯一（V4MARK/V5MARK/V7MARK_A...），多工单同环境时防串号；**开单前先读环境契约的 guest 残留状态节**——旧 marker 回放（如 config.oeap 持久化 delete 循环）≠ 新证据
- URL 编码 payload 用 curl `-G --data-urlencode`，避免手编出错
- GET query 与 POST body 有本质区别（handler 可能只解析 REQUEST_URI），两个方向都试
- 注入值落盘持久化面（config 回写后 delete/read 循环回放）单独记 [chain-dyn]——单次会话回放实证 ≠ 跨重启存活
- 串口文件 grep 必须 `-a`（二进制混杂），`strings -a` 更稳

### 原语复用（工具化）

已实证的注入原语可以当"环境操作原语"用：零凭据注入 = guest 内 root 执行，可逆解锁其他漏洞的运行时前置（案例：ap3g3 verify-3 用 VULN-4 注入原语创建 hostapd socket 替身解锁 VULN-3 的 memcpy 分支，验证后清理回基线）。环境契约必须记录"用过什么原语改了什么、如何恢复"。

## 死路

- WCPW_ARGn 显示"截断"可能是 shell 消化假象：`;` 后内容被 shell 切为独立命令——判据要找 `/bin/sh:` 回显或 do_execve 行，不要纠结参数长度
- "服务有响应" ≠ "漏洞实证"（HTTP 200 只证明 handler 到达，不证明 sink 执行）
- stub 环境里把 stub 回显当执行证据——**sink 本体（system/sh）绝不能 stub**，stub 只造依赖（wcp_read/click_read 这类），uid=0 必须是真实执行

## 溯源

- AP1850 v2/补验轮（档位 1-3 + console 回传技巧确立）
- ap3g3 `runs/20260919-091031` PoC 子 run `20260919-110256`（档位 4 do_execve 全文 + 三判据完备化；final-report §2）
