# rehoster 跨 run 经验（longterm 种子 — 人工从各 run memory.md 晋升维护）

> 来源：AP1850（AIR-AP1852I-K9 8.10.130.0）三轮 rehost 实战（runs/20260915-095054 等）

## FirmAE / qemu 宿主环境坑（L1 级，每轮必查）

- 容器无 udev：`losetup -P` 不生成 /dev/loopXp1 → add_partition 死循环。修：按 `/sys/block/loopX/loopXp1/dev` 的 major:minor `mknod -m660 /dev/loopXp1 b <major> <minor>` + chown root:disk，`/host/dev/` 也要同名节点；loopN 递增不回收，每次 add_partition 都可能复发，全程盯着补
- run.sh 报 `USER: unbound variable` → 容器内 export USER=root
- extractor 默认 600s SIGINT 超时中断慢解包 → 容器内 `timeout 1800` 直接跑 extractor
- tap 设备残留 IP：重跑 run.sh 前 `ip addr flush dev tap300_0`，否则 "Address already assigned" 且 set -e 直接退出
- run.sh 必须从 /work/FirmAE 目录起跑（相对路径 losetup）
- 容器内 `pkill qemu-system` 会连容器进程树一起杀——容器用 `docker rm -f` 停

## QEMU 启动参数（L2 级）

- Linux 3.4 无 mach-virt：ARM 用 vexpress-a9；console 是 **ttyAMA0**（PL011），不是 ttyS0
- QEMU 不向用户 -dtb 注入 virtio-mmio 节点：带 `-dtb` 时块设备/网卡要 DTB 里有节点才出现；宿主 QEMU 8.x 起 `-machine dumpdtb` 行为有变，拿不到就自己编内核树 dtb
- 网络不通时的优先序：换 QEMU 版本（4.2→8.2 实测解决 vexpress virtio 注入）> 改 dts 加 virtio-mmio 节点（基址 0x20000000、步进 0x200）> 换 smsc911x/lan9118
- 换新内核后 guest IP 段可能变（FirmAE 网络推断），先 nmap/串口确认再写契约

## 内核模块匹配（vermagic 工程）

- 固件 .ko 与仿真内核 vermagic 必须逐字节一致：`modinfo` 对比。ARM 上 `CONFIG_ARM_PATCH_PHYS_VIRT=y` 会给 vermagic 加 "p2v8 " 后缀——改 `arch/arm/include/asm/module.h` 的 `MODULE_ARCH_VERMAGIC_P2V` 为空串（关 config 会被 VEXPRESS_DT 反选回来）
- 老 .ko 多数无 MODVERSIONS，只看 vermagic 字符串即可
- gcc-13 编译 3.x 内核的五连坑：compiler-gcc13.h 垫片（复制 gcc4 版加 guard）、`__asmeq` 中和、`.S` 里 `#alloc/#execinstr` 段标记 sed 成 `"a"/"x"`、psmouse fsp_detect 加 #ifdef、dtc-lexer 的 yylloc 改 extern（_shipped 文件也要改）

## rootfs 修补套路（L3 级）

- web 栈自愈：写 start_web.sh（fastcgi + lighttpd -f 配置 + pkill 重拉），交 run_service 周期执行——仿真里服务被 watchdog 重拉是常态，curl 000 撞 respawn 窗口重试即可（≤10 次 sleep 6-7s）
- 缺运行态依赖时优先"伪造"而非"仿真"：静态文件树替代内核伪文件系统（/click 案例）、shell 脚本 stub 替代 CLI 工具（wcp_read/wcp_write 案例）——目标是让目标 handler 跑到 sink，不是复现整机
- 二进制级补丁定位：handler 调度层的 flags gate 可以 4 字节 in-place 改跳转（bne→b），改前 dump 原始字节留 decisions.md
- 自签证书 + htpasswd 按镜像内原格式补（Cisco {SHA} 即 base64(sha1(pwd))）

## 工作方式

- 修复每一步（改了什么/为什么/结果）当场追加 decisions.md，不要攒到最后
- 契约（context.md 环境节）写终态 + 已知限制（哪些是 stub、哪些路径异常），下游裁剪工单全靠它
