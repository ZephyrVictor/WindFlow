# verifier 跨 run 经验（longterm 种子 — 人工从各 run memory.md 晋升维护）

> 来源：AP1850 动态验证与复测（runs/20260915-095054 / 20260916-114743）

## 注入取证（serial log 是主通道）

- QEMU `-serial file:xxx.log` 的串口日志 = firmadyne syscall trace + guest stderr：`/bin/sh: X: not found`、`syntax error`、WCPW/命令参数 dump 都在这里；grep 必须 `-a`（二进制混杂），用 `strings -a` 更稳
- **命令输出回传技巧**：payload 附加 `>/dev/console` 把命令输出打到串口（如 `;busybox id >/dev/console`）——比 `not found` 回显强一档，能证明"执行成功"而非仅"被执行"
- **成功性反馈技巧**：`(CMD >/dev/console && echo DONE-OK >/dev/console)`——DONE-OK 出现 = CMD 退出码 0，副作用真实落地
- WCPW_ARGn 显示"截断"可能是 shell 消化假象：`;` 后内容被 shell 当独立命令切走，判据要找 `/bin/sh:` 回显而不是参数长度

## 端点验证方法

- 命令注入三档证据：计时盲注（`;`/`|`/`$()` 元字符延时 vs 空格对照）→ `not found` 回显 → console 回传/成功性反馈；报告里写清是哪一档
- curl 000/超时 ≠ 环境死：fastcgi/lighttpd 被 run_service 周期重拉有 respawn 窗口，重试 ≤10 次每次 sleep 6-7s；连续 000 先查 URL 是否有未编码空格（curl 报 "Malformed input" 不是 000 的常规含义）
- URL 编码 payload 用 curl `-G --data-urlencode`，避免手编出错
- GET query vs POST body 有本质区别：handler 可能只解析 REQUEST_URI（GET query 有效、POST body 无效），两个方向都要试

## 认证异常排查链（仿真 guest 里 401 全拒时）

1. sha1 比对 guest 内运行的二进制/配置/htpasswd 与镜像原件是否逐字节一致（debugfs 挂 image.raw 只读侧读）
2. 同套文件搬到宿主 qemu-user（qemu-arm-static）复跑认证——过了 = 二进制没问题，差异在插桩内核
3. URI 绕过枚举（大小写/%2f/双斜杠/../）排除绕过误判
4. 结论定性写"环境异常，非目标漏洞相关"，静态主张标"未被推翻"

## 记录纪律

- 判定只认 skill 成功判据；"服务有响应"≠"漏洞实证"
- 证伪也是重要结论，写清排除依据（对审计质量同样有价值）
