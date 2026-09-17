# rehost backends — 仿真后端矩阵（tag 路由数据）

> rehoster 读本文件做 backend 选择。每个 backend 一段 frontmatter 声明（机器匹配用）+ 正文（命令/判据/排查）。
> 选择逻辑见 rehoster agent.md：`tags 含目标厂商 tag 或 any` 且 `requires` 满足 → 按 priority 降序逐个尝试。

---
id: unicorn
name: Unicorn 函数级仿真
tags: [cisco-ios, vxworks]
requires:
  arch: [mips, mipsel, ppc, arm]     # 有确定加载基址即可
  image: raw-body                     # 需要解出的裸机器码（非 ELF 亦可）
priority: 80
cost: medium                          # 写 harness，无需启动
fidelity: function-level
limits: [不能验证完整 RCE, 依赖静态审计给出的函数地址, MMIO/全局表访问需 stub 或补零页]
---

## 适用
单体固件（无 rootfs、无机器模型可用的目标）。不做整机启动——把镜像映射进内存，从静态审计定位的函数地址直接执行，验证数据流主张。

## 环境 = harness 参数（不是网络可达地址）
成功输出以下参数到 context.md 环境节，供 verifier 构造工单：
- 镜像文件绝对路径（如 `workdir/extracted/<fw>/ios_unpacked/-`）
- 加载基址（如 0x80010000）与架构（如 mips-be）
- 审计 findings 中给出的相关函数地址清单（入口/sink 各一个以上）

## check 步骤（快速定性）
用 capstone 反汇编镜像首 16 字节确认架构判断无误；用 unicorn 只映射 + emu_start 跑入口前 10 条指令观察是否立即跳转未映射地址（正常——函数级仿真不走启动路径，只从目标函数起步）。

## 失败模式
- 函数执行中触碰未映射地址（全局表/MMIO）→ 记录地址，补零页（mem_map 后全零）重试；反复触发则该函数依赖外设状态，标注该数据流"函数级不可达"
- 调用约定误判（参数在 a0-a3 以外的寄存器/栈）→ 换入口或读反汇编重排参数

---
id: firmae
name: FirmAE (qemu-system 全系统仿真)
tags: [any]
requires:
  rootfs: true                        # 必须有 Linux rootfs + init 结构
  arch: [mips, mipsel, arm, armel]
priority: 60
cost: heavy                           # 10-20 分钟级
fidelity: full-system
limits: [x86 不支持, 企业级平台成功率低, 需要宿主 docker --privileged + postgres, 失败时按修复阶梯 L1-L4 尝试后再降级]
---

## 适用
Linux 型固件（消费级路由器/AP/IP 摄像头为主，FirmAE 官测 8 大厂商无线路由与摄像头 79% 成功率）。**Cisco IOS 单体（MZIP，无 Linux rootfs）已实测不可行**——extractor 递归扫完整镜像只找到资源文件，"Extracting root filesystem failed"。

## 环境栈（宿主机已就绪）
- docker 镜像 `firmwell:latest`（内含完整 FirmAE）；宿主 postgres 172.17.0.1（firmadyne/firmware）
- 固件放 `/work/FirmAE/firmwares/`

## check 模式（快速定性）
```bash
docker rm -f firmae-rehost 2>/dev/null
sudo rm -rf /work/FirmAE/scratch/<IID>   # 旧 IID 重跑才有干净的 run.sh
docker run --rm --privileged \
  -v /work/FirmAE/scratch:/work/FirmAE/scratch \
  -v /work/FirmAE/firmwares:/work/firmwares \
  -v /work/FirmAE/images:/work/FirmAE/images \
  -d --name firmae-rehost firmwell:latest \
  bash -c "cd /work/FirmAE && FIRMAE_DOCKER=true ./run.sh -c <brand> /work/firmwares/<固件> > /work/FirmAE/scratch/rehost.log 2>&1"
```
- brand 不确定时先跑 `get_brand`（python3 -c "import sys;sys.path.insert(0,'scripts');import util;print(util.get_brand('/work/firmwares/<固件>','172.17.0.1'))"）
- **已知坑**：run.sh 内 extractor 默认 600s SIGINT 超时，对解包慢的固件会中断——在容器内改用 `timeout 1800` 直接跑 extractor，或预先放宽；`USER` 变量未设会 unbound（设 USER=root）
- 判定：`scratch/<IID>/result` 为 true（Web 可达）且 `ip` 文件有可达 IP

## 起持久实例
check 成功后 QEMU 已被杀掉。保持运行：`sudo /work/FirmAE/scratch/<IID>/run.sh > .../run-live.log 2>&1 &`，等 60s 后 `ping` + `curl` 验证。**不进 QEMU 交互终端。**

## 失败诊断与修复阶梯（check 失败后按级尝试，每级修复后重跑 check）

先定位：读 `scratch/<IID>/` 下的 debug log（extract-debug.log / emulation.log）与 qemu serial log，把失败归入下面某一级。**修复优先于降级**——多数"失败"是环境坑或启动参数问题，不是不可行。

**L1 宿主/容器环境坑**（零风险，直接修）：
- 容器无 udev，`losetup -P` 不生成 /dev/loopXp1 → add_partition 的 `/host/dev/loopXp1` 等待循环死锁。修复：`mknod -m660 /dev/loopXp1 b 259 <minor>`（minor 查 `/sys/block/loopX/loopXp1/dev`）+ chown root:disk + 在 `/host/dev/` 建同名节点。每次 add_partition 新建 loopN 都可能复发，全程盯着补。（已实证，run 20260915-032646）
- `USER: unbound variable` → 设 `USER=root`（已实证）
- run.sh 内 extractor 默认 600s SIGINT 超时会中断慢解包 → 容器内改用 `timeout 1800` 直接跑 extractor（已实证）
- postgres 连不上 → 检查宿主 172.17.0.1:5432 与 firmadyne/firmware 库存活

**L2 qemu 启动参数**（症状：kernel panic / "No working init"，读 serial log 定位）：
- kernel cmdline：不带 initrd 时 `rdinit=` 被忽略，须用 `init=/firmadyne/preInit.sh`（已实证）
- 换 ARM machine model：默认 virt 不行试 vexpress-a9 / vexpress-a15（改 run.sh 的 -M 参数）
- 调大 `-m` 内存（企业级固件 rootfs 大：512M→1G/2G）
- 换 kernel：FirmAE 自带 ARM kernel vs 固件自带 kernel（`scratch/<IID>/image/` 内对比）
- **内核 vermagic 不匹配**（症状：固件内核模块 insmod 失败，如 `vermagic 3.4.103 SMP mod_unload ARMv7` vs FirmAE armel 写死 4.1.17；guest 内关键文件系统/服务因此缺失，如 Cisco 的 /click clickfs → fastcgi handler 层 400）。已实证（run 20260915-095054，merakiclick.ko 加载失败堵死 VULN-1/2 动态验证）。修法——**编译满足条件的 kernel**：
  1. 检查固件 `/lib/modules/*.ko` 的 vermagic（`modinfo -F vermagic`），得出版本/选项要求
  2. 取对应版本 Linux 源码，应用 FirmAE 内核补丁集（firmadyne syscall tracing + nvram 拦截 + autodetect，见 FirmAE 仓库 kernel patch 目录；老内核可能需少量适配）
  3. `.config` 对齐 vermagic 条件：`CONFIG_SMP`、`CONFIG_MODULE_UNLOAD`、ARMv7、`CONFIG_LOCALVERSION=""`——vermagic 字符串必须逐字节一致
  4. 产物放 `binaries/zImage.<arch>.<ver>`，改 run.sh 的 `-kernel` 指向它（get_kernel 对 armel 无版本开关，直接替换或改 firmae.config）
  5. 编译约 30-60 分钟，一次投入对同代固件复用；若补丁集无法移植到目标版本（差 >2 个大版本），降级 unicorn 函数级验证数据流

**L3 rootfs 内容修补**（挂载 image 下的 ext4/cpio 直接改，**改 copy 不改原固件文件**）：
- PID1 问题：改 `/firmadyne/preInit.sh` 或 rcS——去掉硬件相关段（LED/看门狗/ASIC 检查）
- 缺库/缺二进制：从 rootfs 其他位置（如 `/opt/cisco/pkg/*.ipk`）补 symlink 或复制；宿主有 arm 交叉链时可静态编译 busybox 塞入当救援 PID1
- init 卡死：rcS 逐段加 echo 观察执行到哪，注释掉卡死段
- 企业级固件常见：`/etc/init.d/*` 里依赖硬件的服务全部 disable，只留网络 + 目标服务

**L4 网络推断失败**（系统起来了但 check 判定 false / 拿不到 IP）：
- FirmAE 自动网推断对非标准网络栈（Cisco 用 Click/自研栈）常失败
- 手工分析 rootfs 网络配置（/etc/network/interfaces、Click 配置）推静态 IP
- 直接改 run.sh：qemu -netdev 用已知网段，跳过自动推断
- 起机后 nmap 扫 qemu 网段确认

**硬边界（立即降级，不进/退出修复阶梯）**：
- 镜像本身残缺：挂载 rootfs 先查 `/lib/ld-*.so` 与 PID1 是否存在且无处可补（截断/加密段缺失类）——第一时间识别止损，不要烧修复预算
- rootfs 提不出（"Extracting root filesystem failed"，extractor 递归找不到 rootfs）——形态判定错误，该 backend 对此目标不可行

**修复预算**：L2/L3 合计最多 3 轮；穷尽后如实降级，全部尝试记录到 decisions.md。

---
id: qemu-user
name: qemu-user + libnvram 垫片
tags: [tp-link, d-link, netgear, trendnet, tenda, huawei-consumer]
requires:
  rootfs: true
  arch: [mips, mipsel, arm, armel]
  binary: true                       # rootfs 内有可独立启动的目标二进制
priority: 50
cost: medium
fidelity: partial
limits: [单进程仿真, nvram 值靠猜, 环境保真度低于全系统]
---

## 适用
消费级 Linux 固件的轻量路径：不起整个系统，直接 `qemu-<arch> -L <rootfs> ./usr/sbin/httpd` 起单个二进制，配 LD_PRELOAD 的 libnvram 垫片返回合理默认值。适合 PoC 只需打单个服务的场景；启动失败退回 firmae。

## 本批适用性
7 个 target 均非消费级 Linux 型——本 backend 当前不适用，保留矩阵完整性（后续扩展 target 集时启用）。

---
id: dynamips
name: Dynamips (Cisco 路由器仿真)
tags: [cisco]
requires:
  form: elf-ios                       # 镜像必须是 ELF 封装 IOS（路由器）
  platform: [7200, 3600, 3725, 3745, 2600, 1700, 2691]
priority: 40
cost: medium
fidelity: full-system
limits: [只支持路由器平台, 交换机/AP 机型模型不存在]
---

## 适用
ELF 格式的路由器 IOS（c7200/c3745 等经典路由镜像），GNS3 生态主力。

## 本批适用性（已实测证伪）
c3550 的 MZIP 剥壳（解出 13.4MB PPC32 裸码手包 ELF）后 dynamips 0.2.14 执行数条指令即跳未映射地址（`0xffffffff9xxxxxxx`——交换机平台特有 MMIO/ASIC 窗口，C7200 机型模型不存在这些设备）。**本批全部为交换机/AP，此 backend 不可用**；仅当 target 换成路由器 ELF 镜像时启用。

---
id: vendor-vm
name: 厂商官方虚拟镜像
tags: [cisco]
requires:
  platform: [asa, ios-xe, ios-xr]     # 有官方 VM 产品线的平台
priority: 60                          # 同版本 ASAv = 同 lina 代码，优先于 firmae 代际方案
cost: medium
fidelity: same-image-full-system      # 同版本对齐时按 full-system 对待；版本错位时降 generation-match
limits: [需要人工下载镜像(免费 Cisco 账号即可), 版本错位时只能代际验证]
---

## 适用
厂商自己发布的 QEMU/KVM 镜像：ASAv（ASA 5500-X 代）、CSR 1000v/Catalyst 8000V（IOS-XE）。

## 获取（ASAv，免费）
1. 注册免费 Cisco.com 账号（无需服务合同）
2. 下载 **CML-Free** 的 refplat ISO（developer.cisco.com/docs/modeling-labs/cml-free）——内置 asav/IOL/IOL-L2 镜像
3. 从 ISO 中提取 `asav<ver>.qcow2`（无需安装 CML 平台，qcow2 直接喂 KVM）
4. **版本对齐原则**：静态审计的 ASA 固件版本若与 refplat 内 ASAv 版本不一致，优先把审计目标**整体换成 refplat 版本**（从 qcow2 提取 lina 静态审计 + KVM 动态验证，同一镜像闭环），而不是做跨版本代际推断。确需版本错位时，结论标注"代际验证"并降 fidelity 为 generation-match

## 启动（KVM）
```bash
qemu-system-x86_64 -enable-kvm -m 2048 \
  -drive file=asav.qcow2,if=virtio,format=qcow2 \
  -netdev user,id=n0,hostfwd=tcp::443-:443 -device virtio-net-pci,netdev=n0 \
  -nographic
# 管理口起在 mgmt (GigabitEthernet0/0)，Day0 后可 SSH/ASDM
```

## 本批适用性
asa9-19-1-9 的动态验证路径。若按版本对齐原则改用 refplat 内 ASAv（当前 9.22.1），静态审计也重定向到该版本的 lina。Cisco 交换机无官方 VM（虚拟化产品线都是 IOS-XE/ASA 时代）。IOL/IOL-L2 是源码级 x86 重编译，无法从 MZIP 转换，不在此列。

---
id: bare-metal
name: 真机
tags: [any]
requires: {}
priority: 10
cost: manual                          # 需人工提供设备
fidelity: full-system
limits: [需人工采购/提供设备, 完整保真]
---

## 适用
一切仿真路径断供时的最终兜底：二手设备通常极便宜（老 Catalyst 交换机几十元级）。agent 只负责产出"需真机验证清单 + 每条的复现命令"，设备对接由人完成。

## 本批建议
c2950/c3550/c3750/ap3g3 若需要字节级完整实证（超出 unicorn function-level 能力），走此路径。
