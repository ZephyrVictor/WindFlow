# 厂商条目：Cisco Aironet Mobility Express / Meraki 架构

## 适用特征

固件解包后命中任一标志即为本家族：

- `ramfs_cisco/` 根文件系统 + `bootsh` 切根脚本（双层 initramfs）
- `merakiclick.ko` / `proclikefs.ko` 内核模块（Click 配置平面，见 [rehost/vermagic-engineering](../rehost/vermagic-engineering.md)）
- `wcp_read`/`wcp_write` CLI 工具族（WCP 配置协议）
- lighttpd + fastcgi 单后端承载全部 Web UI（`/oeap/*`、webauth 门户、`/configure/`）
- 已验证实例：AIR-AP1850（ME 8.10.130）、ap3g3/Aironet 3700（ME 15.3(3)JK = 8.10.105）

## 家族事实（跨代成立的攻击面/结构）

### 双代注入面族（8.10.130 与 15.3(3)JK 均执行级实证）

同款注入面跨硬件代共存——审计新 ME 固件时**这些面直接列为最高优先 hypotheses**：

| 面 | 端点 | 参数 |
|---|---|---|
| webauth clientid 注入 | `/webauth/webauth.json` | `clientid`（passthrough，零过滤） |
| location 注入+监管域篡改 | `/set_universal_ap_reg_domain.shtml` | `location`/`regDomain24`/`regDomain5` |
| wl_maclist 注入 | `/oeap/config_set_ssid.cgi` | `wl_maclist0`（认证路径） |
| 未授权调用面 | `/testfastcgi.cgi` | 把用户参数传给本应认证的 /oeap/ handler（CH-2 未认证 RCE 的关键） |

修复建议对两代通用。ap1g4 轮证伪项（tar 穿越、/configure/ 归一化绕过、wl_unit 溢出）在 ap3g3 静态已分别证伪在案——同族负结果也可跨代参考。

### 真机模式前置（rehost gate 补丁语境必读）

fastcgi dispatch gate 补丁（`bne→b`）消解 B/C/D 模式字节后，动态实证**不能**外推为"任意模式预认证"。真机前置：webauth 面（clientid/webauth.json）需 webauth 模式；location 需 UX-Priming；testfastcgi 需 OEAP。

## 症状（rehost 时）

- FirmAE in-flow check 失败或 extractor 提取出 busybox bootstrap 而非真正根文件系统 → 双层 initramfs 选错层
- 服务起不来 + 串口报 click 路径/内核符号缺失 → click 墙（详见 vermagic-engineering）
- lighttpd 周期性死循环互杀 → daemonize 与看门狗冲突

## 解法

### rehost 路由：FirmAE L3 手工镜像（不走 in-flow check）

FirmAE extractor 对 bootsh 切根型双层 initramfs 选错层——按手工配方构镜像（build 脚本：解出 ramfs_cisco → 构 ext2 整盘 → vexpress-a9/QEMU 8.2.2 直启；launch 脚本：启动 + 就绪探测）。配方实例：`/tmp/build_ap3g3_image.sh`、`/tmp/launch_ap3g3.sh`（会话级，run decisions.md [rehoster] 有全程记录）。

### stub 哲学：伪造而非仿真

目标 = 让目标 handler 跑到 sink，不是复现整机：

- `wcp_read` stub 恒空输出 / `wcp_write` stub 参数回显 `/dev/console`（`WCPW_ARGn` = 串口证据通道，**sink 本体 system() 不 stub**）
- 内核伪文件系统用 tmpfs 静态文件树替代（/click 案例）
- handler 调度层 flags gate 可 4 字节 in-place 改跳转（`bne→b`），改前 dump 原始字节留档

### L3 轻量化修复实录（ap3g3 三坑）

1. 缺 `/run` → 创建即可
2. lighttpd daemonize 与看门狗互杀 → 改 monitor-loop 模式
3. 宿主 zsh word-splitting 导致认证探测误判 → 探测脚本显式引号/数组

## 死路

- FirmAE in-flow check 对 bootsh 切根型固件不可用（选错 initramfs 层）
- 3.4.103 仿真内核下 capwapd/wcpd/grpc_server 不可运行（click vermagic 墙——三重死锁见 vermagic-engineering，解法=依赖替身/匹配内核/真机）
- Cisco IOS（MZIP 单体）不可 FirmAE 仿真（本家族经验不适用，走 `vendors/cisco-ios-classic.md` 静态轮）

## 溯源

- AP1850 v2 轮 `runs/20260917-041115` + 补验轮 `runs/20260918-005656`（6+12 条执行级实证，注入面族确立）
- ap3g3 轮 `runs/20260919-091031`（5/5 Critical 实证 + CH-2 闭环 + 注入面跨代确认；final-report §2/§6）
