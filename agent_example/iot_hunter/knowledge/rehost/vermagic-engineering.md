# rehost 工艺：内核模块 vermagic 匹配工程

## 适用特征

固件用户态服务依赖**厂商内核模块**（.ko），rehost 换内核后服务起不来（报 click 路径/符号缺失/模块加载失败）。本条目适用于一切"模块加载型"依赖墙，Meraki click 是已验证实例。

## 症状

- `insmod merakiclick.ko` → vermagic 校验失败 / unresolved symbols
- 服务启动报 `/click` 不存在、内核伪文件系统缺失

## 解法

### 第一步：先判结构——sink 在哪决定路线选择

**注入/漏洞 sink 在用户态二进制自身**（如 grpc_server 自己的 `sh -c`）→ click 只卡启动 → 走**依赖替身**（最轻）。
**sink 依赖模块真实功能**（如 capwapd 分片解析、click 防火墙语义）→ 走**匹配内核重建**或**真机**。

### 路线 1：依赖替身（一轮补验 run 的量级）

- tmpfs 静态文件树挂 `/click`（按模块接口的路径面造假）
- `click_read`/`click_write` 类 CLI 工具用 shell 脚本 stub（罐头返回值/参数回显）
- 原则：**stub 依赖，绝不 stub sink**——目标是让目标 handler 跑到 sink
- AP1850 已有 /click 假树与 wcp stub 先例

### 路线 2：匹配内核重建（按天计，解锁整个模块平面）

自建**与固件内核同版本**的内核 + QEMU 支持的平台，让固件自带 .ko 原生加载：

1. 取 GPL 源码（Cisco 按 GPL 发布 Aironet 内核源码；Meraki 私有符号必然在源码里）｜gate：精确分支可得
2. `extract-ikconfig` 从固件 zImage 提内嵌 .config；缺 IKCONFIG 用 GPL 包 config｜gate：精确 config
3. config 手术**只加** QEMU 平台驱动（vexpress：PL011/ttyAMA0、virtio-blk/net、GIC、SMP），vermagic 决定项全不动
4. gcc-13 + 五坑垫片编译（见下）
5. bring-up 新实例（不动在线实例）｜gate：shell+磁盘+网络
6. `insmod` 固件自带 .ko｜gate：伪文件系统真挂载
7. 拉起依赖服务 → 环境契约 → verify 工单全家

### vermagic 逐字节工程

- `modinfo <ko>` 对比两侧 vermagic，**逐字节一致**才算过（不是版本号相同）
- ARM `CONFIG_ARM_PATCH_PHYS_VIRT=y` 给 vermagic 加 `p2v8 ` 后缀——两个方向：① 自建内核要匹配**无** p2v8 的老模块 → 改 `arch/arm/include/asm/module.h` 的 `MODULE_ARCH_VERMAGIC_P2V` 为空串（直接关 config 会被 VEXPRESS_DT 反选回来）；② 固件模块 vermagic **含** p2v8（如 merakiclick.ko `3.14.33 SMP mod_unload ARMv7 p2v8`）→ 自建内核必须保留该 config
- 老 .ko 多数无 MODVERSIONS → 只看 vermagic 字符串；同源码+同 config 编译则符号 CRC 天然一致

### gcc-13 编 3.x 内核五坑垫片（已踩通清单）

1. `compiler-gcc13.h` 垫片（复制 gcc4 版加 version guard）
2. `__asmeq` 中和
3. `.S` 里 `#alloc/#execinstr` 段标记 sed 成 `"a"/"x"`
4. psmouse fsp_detect 加 #ifdef
5. dtc-lexer 的 yylloc 改 extern（_shipped 文件也要改）

## 死路（三重死锁——为什么不能简单强加载）

固件 .ko（内核 A 版本）→ 仿真内核（版本 B）失败是**三层叠加**，patch 一层过不了下一层：

1. **vermagic 字符串**校验（`insmod -f` 可强过）
2. **厂商私有符号**——只有厂商内核导出（如 Meraki 符号），标准内核没有（强过 1 后卡这）
3. **内核内部 ABI**——版本间结构体布局变化（file_operations 等），强加载成功也是一用就崩

直接 boot 固件自带 zImage 也不行：QEMU 无对应 SoC 平台模型（如 Marvell Armada 390）。

## 溯源

- AP1850 轮（gcc-13 五坑、p2v8 双向工程、vermagic 逐字节纪律确立）
- ap3g3 `runs/20260919-091031`（三重死锁实证定性：grpc/capwapd 因 merakiclick vermagic + 私有符号不可运行；final-report §6.1）
- 路线 2 实操记录：（待补——完成后回填）
