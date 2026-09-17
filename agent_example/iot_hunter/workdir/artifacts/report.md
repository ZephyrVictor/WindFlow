# 漏洞审计报告 — Cisco AIR-AP1850-K9 Mobility Express 8.10.130.0

> Run：iot-hunter / 20260917-041115 ｜ reporter
> 本报告基于 correlator 候选清单（`workdir/artifacts/vulns.md`）与 `memory/findings.md` 中 [unpacker]/[audit-0]/[audit-1]/[audit-2]/[audit-3] 全部条目整理。置信度忠实转述上游结论，未做升级或淡化；所有函数/地址证据可按 findings 原始条目复核。

---

## 1. 执行摘要

### 1.1 目标固件

| 项 | 值 |
|---|---|
| 型号 | Cisco Aironet 1850 Wave2（AIR-AP1850-K9，板卡 corsica，SoC ipq806x，Meraki 血统，OpenWrt 15.05 衍生） |
| 版本 | **Mobility Express 8.10.130.0**（2020-07-29 构建） |
| 架构 | **arm-el**（Linux 3.4.103 内核，zImage 加载 0x41508000，uClibc） |
| 主审计目标 | ap1g4 主 rootfs（rootfs + 9 个运行时 ipk 全部解出） |
| 附带镜像 | ap1g1（Cisco 1700/2700/3700，IOS 15.3(3)JK3，MZIP 单体，**mips-be**——inventory §9.2 原判 ppc-be 已勘误）；本轮裁剪未审 |
| 固件来源 | `air-ap1850-k9-me-8-10-130-0.zip` 下载截断（EOCD 缺失），ap1g4 完整副本取自 `workdir/archive/` 经 SHA-512 清单 + 43.6MB 前缀逐字节比对双重验证，解包全部成功 |

ROOTFS = `/home/fjw/workspace/flow/iot_hunter/workdir/extracted/air-ap1850-k9-me-8-10-130-0/ap1g4/_part.bin.extracted/rootfs`（下称 `$R`）。

### 1.2 审计范围

3 个 binary × 4 个静态审计工单（planner 按"暴露面 × 输入复杂度"选单，子 run 20260917-045450 四节点并行全部完成）：

| binary | 大小/形态 | 工单（角度） | auditor |
|---|---|---|---|
| `$R/usr/bin/fastcgi` | 138KB ARM PIE stripped，lighttpd :80/:443/:1233/:1234 唯一 FastCGI 后端，承载全部 OEAP Web 管理 | fastcgi-cmdi-authbypass（命令注入+认证绕过） | audit-0 |
| 同上 | 同上 | fastcgi-memcorrupt（内存破坏） | audit-1 |
| `$R/opt/cisco/capwapd/8.10.130.0/bin/capwapd` | 2MB ARM PIE stripped，UDP 5246/5247 CAPWAP 协议面 | capwapd-cmdi-memcorrupt（命令注入+内存破坏） | audit-2 |
| `$R/usr/bin/stilecpd` | 1MB ARM **未 strip**（带 debug_info），TCP 0.0.0.0:4040 JSON-RPC（nbar.service） | stilecpd-authbypass-memcorrupt（认证绕过+内存破坏/逻辑） | audit-3 |

辅证：unpacker 攻击面盘点（inventory.md）、planner 侦察（lighttpd 认证边界/cgi.assign/capwapd system×157/stilecpd 零认证）、correlator 对四处 load-bearing 事实的原文复核（lighttpd.conf auth.require、cgi.assign、capwap-upgrade.sh:93、capwap-upgrade-func.sh:1291）、rehost 全系统仿真（FirmAE 改造形态，192.168.100.1）对端点可达性与认证边界的实测。

### 1.3 结论一览

**20 条候选漏洞**（三梯队：确认完整链 9 / 疑似与依赖缺环 6 / 孤立发现与配置级 5），另撤销上轮 2 条（VULN-7 capwapd 内存破坏推测——本轮 audit-2 已审出相反结论；VULN-8 登录枚举 oracle——上轮 finalizer 执行级证伪 + 本轮 rehost 复测 + audit-0 复核三重一致）。

按置信度（忠实转述 correlator 判定）：

| 置信度 | 数量 | 编号 |
|---|---|---|
| 完整确认 | 5 | VULN-1/2/3（pre-auth root RCE）、VULN-4（通用认证绕过原语）、VULN-12（零认证 RPC 面） |
| 限定确认（写入/sink/配置事实反汇编级或配置级确认，附带待动态注记） | 8 | VULN-9（写入动作确认，登录效果待动态）、VULN-10（sink 确认，下载内容待 PoC）、VULN-14（crash 确认）、VULN-17（sink 确认，可达性缺环）、VULN-18（代码确认，运行态策略位未验证）、VULN-20/21/22（配置/版本事实确认） |
| 高度可疑（代码路径反汇编级确认，组合语义待 PoC） | 4 | VULN-5、VULN-13、VULN-15、VULN-16 |
| sink 确认但远程可达性推测 | 1 | VULN-11（依赖 wcpd 缺环） |
| 推测 | 2 | VULN-6、VULN-19 |

按严重度：**Critical 5**（VULN-1/2/3/4/13）、High 6（VULN-5/6/9/10/11/12）、Medium 8（VULN-14/15/16/17/18/19/20/22）、Low 1（VULN-21）。

**8 条跨组件利用链**（§3）：确认 4（W1/W2/S1/反取证，其中 W2、S1 分别带"登录效果待动态""需拉起服务"注记）、高度可疑 2（W3/W4）、待验证缺环 2（C1/R1）。

### 1.4 最高风险一句话

**四条互相独立、单请求、无认证的 root RCE 入口**——VULN-1（webauth.json clientid）、VULN-2（set_universal location）、VULN-3（testfastcgi→wl_maclist）仅需 80/443/1233/1234 任一端口网络可达，VULN-13（stilecpd dlopen）需 4040+69 可达——其共同根因是 lighttpd `auth.require` 仅保护 `/configure/`+`/oeap/` 两前缀、fastcgi 全部命令 sink 无元字符过滤、stilecpd 完全无认证。

### 1.5 与上轮（20260915-095054，同版本固件）的差异

| 上轮 | 本轮变化 |
|---|---|
| VULN-1 webauth.json clientid | 复确认（同地址 0x10ab0/0x10b98）；rehost 实测端点无认证 200 |
| VULN-2 set_universal 注入 | 复确认；主向量修正为 `location`（无截断），regDomain5/24 经 strncpy(3) 仅 ≤2 字符元字符（辅助） |
| VULN-3 认证后注入族 | wl_maclist 分支指令级确认 + 经 testfastcgi **升级为 pre-auth**；postlogin.cgi topage 分支本轮证伪 |
| VULN-4 testfastcgi 信息泄露 | **大幅升级**：全分发表遍历 = 通用认证绕过原语（22 个 handler 无认证执行） |
| VULN-5 tar 穿越 | 复确认 + 升级 pre-auth + 新增时间转移注入路径（W4） |
| VULN-6 webauth 异步自授权 | 未再审计；新增 redirect.cgi → click webauth_helper 线索 |
| VULN-7 capwapd 内存破坏（推测） | **撤销**——本轮已审：分片重组/sscanf/wire 解码器证伪；新发现转入 VULN-11/17/18 |
| VULN-8 登录枚举 oracle | **撤销**（三重证伪） |

---

## 2. 漏洞详情

> 每条含：类型/严重度、利用链、证据（保留 auditor 出处）、复现路径、修复建议。全部地址基于 arm-linux-gnueabi-objdump 反汇编（rodata vaddr=文件偏移；.data.rel.ro vaddr=文件偏移+0x10000）。

### 第一梯队：确认的完整利用链（无认证可达）

#### VULN-1 — /webauth/webauth.json `clientid` 无认证命令注入【Critical / 确认】

- **类型**：OS 命令注入 → RCE（fastcgi 以 root 运行）
- **利用链**：无前置（pre-auth）→ `GET /webauth/webauth.json?clientid=;PAYLOAD;&redirecturl=x`（无需 username）→ `sbuild` %s 拼接 → `run_system` → root 任意命令
- **证据**（[audit-0] major④）：handler 0x10ab0（分发表 /webauth/webauth.json，flag=0x11）。clientid 读取 @0x10ad0；username 为空（[sp+48]==0 判空 @0x10b44）走 passthru 分支；0x10b6c–0x10b84 `sbuild(sp+164, "wcp_write wcp/wcp_db.set_webauth_done_to_fcgi %s 1"@0x1d328, clientid.c_str())` → `run_system(sp+164,1,0,0)`@0x10b98，前导 syslog(7)@0x10b68。**clientid 无过滤直入 shell**。webauth 为强制门户流程端点（:80/:443/:1233/:1234 设计上须登录前可达），lighttpd auth.require 仅覆盖 `/configure/`+`/oeap/`（correlator 复核 lighttpd.conf L87-96 原文）。同族 webauth_result.json(0x10738) 已核实安全。
- **置信度**：确认。反汇编级全数据流；rehost 实测该端点无认证 200 可达。
- **复现路径**：`arm-linux-gnueabi-objdump -d --start-address=0x10ab0 --stop-address=0x10c00 $R/usr/bin/fastcgi` 核对 0x10ad0/0x10b44/0x10b84/0x10b98；动态：curl 带 URL 编码 payload（query parser 0xa1c8 先 cp_urlunescape），serial log `/tmp/ser34.log` 看 wcp_write stub 参数回显与 /bin/sh "not found" 痕迹取证。
- **修复建议**：
  1. `clientid` 语义为客户端表索引（wcp_db 键），合法字符集封闭：在 0x10ad0 取值后立即做白名单校验（如 `^[0-9A-Za-z:-]{1,32}$`），含 shell 元字符（`` ` `` `;` `|` `&` `$` 空格）即拒绝该请求；
  2. 根因修复：0x10b98 的 `run_system` 改为不经 `/bin/sh` 的接口（`wcp_write` 的 argv 型 IPC / 直接写 wcp unix socket），消除整类拼接注入；
  3. 该端点为强制门户流程设计上 pre-auth，不能以 lighttpd Basic auth 兜底——校验必须落在 handler 内（1/2 条）。

#### VULN-2 — /set_universal_ap_reg_domain.shtml `location` 无认证命令注入【Critical / 确认】

- **类型**：OS 命令注入 → RCE
- **利用链**：无前置（pre-auth）→ `GET /set_universal_ap_reg_domain.shtml?configMode=1&location=X;PAYLOAD;&regDomain5=A&regDomain24=B` → `system()` → root 任意命令
- **证据**（[audit-0] major①，[audit-1] chain 补充）：handler 0x99bc（分发表第 3 项，flag=4，URL 在 auth.require 之外）。参数 configMode(int, atoi@0x9abc)/location(sp+76)/regDomain5(sp+40)/regDomain24(sp+52) → 3 条固定 `run_system_capture` 读当前 wcp 状态 → 守卫 0x9c4c–0x9c88（任一参数与当前值不等 → 应用路径 0x9fac——默认状态即不等，必走）→ sink 0x9cb8–0x9ce8 `snprintf(sp+272,128,"wcp_write wcp/dot11_tx_power_2g.set_domain %d %s %s %s",…)` → `system(sp+272)`@0x9ce8；5g 同款 0x9d10–0x9d24。**location 经 hard_c_str 无任何过滤直入 system()**（前缀约 51 字节 → 128 字节缓冲内约 76 字节 payload 空间，`;telnetd -l /bin/sh -p 9999;` 类足够）；regDomain5/24 经 `strncpy(dst,src,3)` 仅能注入 ≤2 字符元字符（辅助）。snprintf 定长 128 无溢出（[audit-1] 证实）。执行后 0x9e50 `/sbin/reboot -r` ——payload 先于 reboot 运行。持久化出口：payload 写 /www/x.sh + lighttpd `cgi.assign(".sh"=>"/bin/sh")`（lighttpd.conf L78-80，correlator 复核原文）→ `GET /x.sh` 二次触发。
- **置信度**：确认。rehost 实测 /get_universal_ap_reg_domain.xml pre-auth 200，set_universal 同在认证边界外。
- **复现路径**：objdump `--start-address=0x99bc --stop-address=0x9e60` 核对 0x9c4c–0x9c88/0x9cb8–0x9ce8/0x9d24；grep lighttpd.conf auth.require。
- **修复建议**：
  1. `location` 语义为监管域位置代码，合法值集封闭（ISO 国家/地区码 2–3 字符）：在参数解析处（0x9abc 附近取 sp+76 后）做枚举白名单校验，拒绝含元字符的值；
  2. `regDomain5/regDomain24` 语义为监管域类目（FCC/ETSI 等枚举），同样白名单（strncpy(3) 截断不是校验）；
  3. sink 0x9ce8/0x9d24 的 `system@plt` 改 exec 族（不启用 shell）或 wcp argv IPC；
  4. 执行后无条件 reboot（0x9e50）不应作为自愈手段依赖——payload 已先于 reboot 完成。

#### VULN-3 — config_set_ssid.cgi `wl_maclist%d` 命令注入（经 testfastcgi 无认证）【Critical / 确认】

- **类型**：OS 命令注入 → RCE（直接路径认证后，经 VULN-4 无认证）
- **利用链**：无认证 `POST /testfastcgi.cgi` body `wl_unit=1&wl_macmode=allow&wl_maclist0=;PAYLOAD;`（macmode 写入先于 gate 读取，单请求可成）→ `run_system` → root 任意命令。认证路径：`POST /oeap/config_set_ssid.cgi` 同参数（rehost 实测 post-auth 全族可达，Cisco/Cisco → 200）。
- **证据**（[audit-0] major③）：handler 0x8ab8（/oeap/config_set_ssid.cgi，flag=8→被 testfastcgi 遍历调用）。wl_unit==1 路径 0x8be4–0x8c00 **无条件**把 wl_macmode 写入 config+0x17c00+0x164（即 gate 检查字段）→ gate 0x96b8–0x96c8 检查 =="allow" → 0x96e8 `bl 0x8724`（全 binary 唯一调用者，与 VULN-14 同函数）→ 第一循环 0x8764–0x87cc 对 i=0..15 取 **POST 值** wl_maclist%d → sink 0x89b4–0x89e0 `sbuild("wcp_write wcp/Radio%d.add_local_ssid_acl_entry %s", radio, vec[i].c_str())` → `run_system`@0x89e0；0x8a20–0x8a4c 同款 "delete_local_ssid_acl_entry %s" → `run_system`@0x8a4c。**%s 无过滤/无引号**。
- **置信度**：确认（指令级）。上轮 VULN-3 判"高度可疑、注入语义待动态"，本轮 audit-0 完成指令级判定升级。
- **复现路径**：objdump 0x8ab8–0x8c00、0x8724–0x8a4c 核对 0x89e0/0x8a4c sink；动态 POST testfastcgi.cgi + serial log 取证。
- **修复建议**：
  1. wl_maclist%d 值语义为 MAC 地址：在第一循环取 POST 值处（0x8764–0x87cc）做格式校验（`^[0-9A-Fa-f:]{12,17}$`），任一值非法即拒绝整批请求；
  2. 第二循环从 /storage/config.oeap 读回的 wl_maclist%d_%d 值**同样过滤**——该值可能来自上传配置包（W4 链），存量数据不可信任；
  3. 0x89b4/0x8a20 的 sbuild→run_system 改 argv 接口（同 VULN-1 第 2 条）。

#### VULN-4 — /testfastcgi.cgi 全分发表遍历 = 通用认证绕过原语【Critical / 确认】

- **类型**：认证绕过原语（直接导致 VULN-3/5/9/10 无认证化）
- **利用链**：无前置 → `POST /testfastcgi.cgi`（任意参数）→ 28 项分发表中 22 个认证后 handler 逐个执行、POST 参数透传
- **证据**（[audit-0] major②）：handler 0xa05c（分发表第 1 项，flag=9，auth.require 外无认证直达）。反汇编实证（0xa05c–0xa148）：复制 arg1 → 140c4(新map) 解析当前请求参数 → 新map["TEST_FASTCGI"]="1" → **从 0x31014 遍历全分发表：flag bit0 置位则跳过（0xa114 `tst r3,#1; bne`），否则 `blx handler(...)`（0xa11c–0xa130）——不做任何 URL 匹配、无认证、无会话校验**。被跳过仅 6 项（testfastcgi 自身/config_set_radio/config_set_dhcp/config_set_firewall flag=9；webauth.json/webauth_result.json flag=0x11），其余 22 项全部执行。已验证影响：① resetlogin.json 凭据重置（VULN-9）；② config_set_ssid.cgi wl_maclist 注入（VULN-3）；③ firmwareupload.cgi 配置包上传+tar 解包（body 经 `_raw_post_data` 键传入，str@0x1c1ac）（VULN-5）；④ firmwaredownload.cgi 配置/凭据哈希下载（VULN-10）；⑤ evt_log_clear.cgi(0x6fa8) 清空 /var/log/messages = **无认证日志擦除（反取证）**。
- **置信度**：确认。rehost 实测 /testfastcgi.cgi 无认证 200。
- **复现路径**：objdump `--start-address=0xa05c --stop-address=0xa148`；分发表 .data.rel.ro 0x31014–0x311f4（28 项 ×16B {name_ptr,handler,arg,flag}）逐项核对 flag bit0。
- **修复建议**：
  1. 该 handler 为调试遗留（TEST_FASTCGI 标志），发布构建应整体移除：删除分发表 0x31014 起第 1 项，或 handler 0xa05c 入口直接返回 404；
  2. 若厂内诊断必须保留：加编译期开关（默认关闭）+ 已认证会话校验——注意仅置位自身 flag bit0 不能修复（它遍历的是别人），唯一安全处置是移除或认证门控；
  3. lighttpd 层对该 URI（及 /slow-stats/ 前缀）默认拒绝，作为纵深防御。
- **附带**：/slow-stats/test_dump.cgi（主循环 0xfb64–0xfc30 精确匹配，按 `size` 参数回显 FCGI stdin body，无认证）为调试遗留回显端点，信息价值低，并入本条不单列（上轮曾与 testfastcgi 并列——本轮 testfastcgi 实质大幅升级）。修复同上：移除或拒绝。

#### VULN-9 — resetlogin.json 无认证管理凭据重置（经 testfastcgi）【High / 确认（写入动作）；登录效果待动态】

- **类型**：认证状态篡改
- **利用链**：无认证 `POST /testfastcgi.cgi`（任意参数）→ 遍历调用 resetlogin → 管理凭据状态变为已知默认（admin/admin）→ OEAP 管理面全权（或见下方张力：Basic auth 锁死）
- **证据**（[audit-0] major⑤）：handler 0xa930（flag=8→被遍历）。0xa948 清全局会话标志 [0x31798]=0；0xa95c–0xa970 把 config+0x17800+0x330（存储的管理员用户名，与 authenticate_user.json@0xaac4、auth_redirect.json@0x84d4 同一字段）赋为 "admin"（str@0x1cab5）；随后两个 String="admin" → 0x5c54 链：ssl_encrypt("admin","SHA256")@0x5ca0 → sbuild("%s:%s\n")@0x5cf0 → `write_to_file_rename_atomic("/etc/lighttpd-htpasswd.user"@0x1b78a,…)`@0x5d14。应答 {"reset":"1"}。
- **置信度与张力（correlator 裁定，未自行升级）**：写入动作**确认**；重置后凭据的实际登录效果需动态验证。rehost L3-修复 7 交叉证据：lighttpd 1.4.54 mod_authn_file htpasswd 后端**不认裸 sha256**（仅明文/crypt/{SHA}/$apr1$）→ resetlogin 写入 `admin:<sha256-hex>` 后实际效果可能是 (a) webauth 层凭据状态重置可登录，或 (b) Basic auth 锁死（认证 DoS）。两种后果均为未授权安全事件。镜像出厂无 htpasswd 文件（correlator 复核：/etc 下无该文件，运行期生成；lighttpd.conf L85 userfile 为 `__AUTH_BACKEND__` 模板占位，运行期替换）。
- **复现路径**：objdump 0xa930–0xa994 与 0x5c54–0x5d14；动态：POST testfastcgi.cgi 后在 guest 内 `cat /etc/lighttpd-htpasswd.user`、并以 admin/admin 试登录 /oeap/。
- **修复建议**：
  1. "恢复默认凭据"必须要求已认证会话或物理接触触发：分发表该条目 flag bit0 置位使其脱离 testfastcgi 遍历，且 handler 0xa930 入口加会话校验；
  2. 写入格式缺陷一并修复：0x5c54 链写入的 `admin:<sha256-hex>` 不被 lighttpd 1.4.54 htpasswd 后端接受——改写为 lighttpd 认可格式（{SHA} 或 crypt）；
  3. 凭据文件路径（/etc/lighttpd-htpasswd.user）如与 fastcgi 自身初始化写同一文件（rehost 实测 fastcgi 启动即覆写该文件），应分离 fastcgi 内部状态文件与 lighttpd 认证文件，消除互相覆写。

#### VULN-10 — firmwaredownload.cgi 无认证配置/凭据哈希泄露（经 testfastcgi）【High / 确认（sink）；下载内容待 PoC】

- **类型**：敏感信息泄露
- **利用链**：无认证 `POST /testfastcgi.cgi` → 遍历调用 firmwaredownload → 下载配置包 → 离线破解凭据哈希 → 登录管理面
- **证据**（[audit-0] major②④）：命令均固定串 `cp /storage/base_capwap_cfg_info /tmp/download_config;cp /storage/config.* …;tar -cvf …`（@0x1be58；sink 0x6d34/0x6e34 mkdir/rm + 0x6d84 cp+tar）→ /storage/config.oeap **含管理员凭据哈希**被打包供下载。文件名固定，无注入。
- **置信度**：确认（sink 固定串反汇编级）；下载体内容/哈希格式需 PoC 确认。
- **复现路径**：objdump 0x6d34–0x6d90 核对固定命令串；动态 POST testfastcgi.cgi 观察应答体。
- **修复建议**：
  1. 分发表该条目 flag bit0 置位脱离 testfastcgi 遍历（直接 URL 已在 /oeap/ Basic auth 保护内，唯一旁路就是 VULN-4）；
  2. 配置导出包不应包含凭据哈希：0x6d84 打包命令剔除 /storage/config.oeap 中的凭据字段（或导出前脱敏）；
  3. 该端点导出行为本身宜加二次确认（当前设计为诊断用途）。

#### VULN-5 — firmwareupload.cgi tar 解包路径穿越任意文件写（经 testfastcgi 无认证）【High / 高度可疑→确认】

- **类型**：路径穿越 → 任意文件写（与持久化机制组合可 RCE）
- **利用链**（两条升级路径）：
  1. **持久化 RCE**：tar 成员 `../../www/x.sh`（任意写）→ lighttpd cgi.assign(".sh"=>"/bin/sh") → `GET /x.sh` → root shell（全程无认证）；
  2. **时间转移注入（W4）**：解包出的 config.oeap 被读入并 save 到 /storage/config.oeap → 其中 `wl_maclist%d_%d` 键在**下一次** config_set_ssid ACL 同步（0x8724 第二循环）以 `delete_local_ssid_acl_entry %s` 进 `run_system`@0x8a4c——投毒配置延迟触发注入。
- **证据**（[audit-1] chain + [audit-0] major②③）：firmwareupload@0x7f20。multipart body 解析（find_left '\n'→split→operator[]，均有 __assert/边界检查，**无内存破坏**）→ 0x5ae0 写 /tmp/upload_config/uploaded_config_file.tar → 0x8068 `run_system("cd /tmp/upload_config;tar -xvf /tmp/upload_config/uploaded_config_file.tar"@0x1c1d7)`（固定串无注入）→ **GNU tar `../` 成员 = 路径穿越任意文件写**。无认证经 `POST /testfastcgi.cgi`（body 为伪造 tar，经 `_raw_post_data` 键传入）。
- **置信度**：高度可疑→确认（代码路径反汇编级确认；tar 穿越语义依赖 GNU tar 行为与目标写权限，需 PoC 验证；rehost post-auth 全族已可达）。
- **复现路径**：objdump 0x7f20–0x8130 核对 0x5ae0/0x8068；动态构造含 `../` 成员的 tar POST 到 testfastcgi.cgi，检查落盘路径。
- **附带**（[audit-1] minor）：畸形 body（如仅 1 个 '\n' 使 split <3 元素）→ Vector::operator[] __assert abort()——认证后 crash DoS（fastcgi 进程模型影响面待动态）。
- **修复建议**：
  1. 0x8068 解包前预读 tar 成员表，拒绝绝对路径与含 `..` 的成员名（GNU tar 默认剥前导 `/` 但保留相对 `..` 穿越语义）；或解包后对每个落盘文件做 realpath 前缀检查（解析结果必须落在 /tmp/upload_config 内）；
  2. 解包目标目录权限最小化（非 root、noexec），且解包进程放弃特权；
  3. config.oeap 读回值进入 VULN-3 第 2 条的过滤（堵 W4 链）；
  4. 移除 lighttpd `cgi.assign(".sh"=>"/bin/sh")` 映射（lighttpd.conf L78-80）——.sh 不应作为 CGI 执行，该映射把任意文件写直接放大为 RCE（与 VULN-2 持久化出口同堵点）。

#### VULN-12 — stilecpd 0.0.0.0:4040 零认证 JSON-RPC（21 命令全部未授权）【High / 确认】

- **类型**：缺失认证 → 未授权设备操控 + 未授权 DoS×2
- **利用链**：无前置（4040 网络可达即零认证）→ 单个 TCP 连接 JSON-RPC → 任意命令效果
- **证据**（[audit-3] major① + major③，correlator 合并同根因）：nbar.service `ExecStart=/usr/bin/stilecpd --mode km --activate -s 0.0.0.0:4040`（明文 TCP，无 User= → root）。全链：RPCServer::do_work@0x6af3c（accept→new RPCWorker→Scheduler::add，无凭据检查）→ RPCWorker::check_request@0x6bcd4（仅协议状态检查）→ Server::handle_rpc_request@0x4bcf8 → ReqParser::parse@0x45e9c（Json::Reader::parse@0x88e28）→ parse_single_request@0x45754（仅校验 jsonrpc=="2.0" 与 method 存在）→ RpcCommandsTable::lookup → ParsedObject::execute@0x43c78 → RpcCommand::run@0x440a0。**符号表全文无任何 auth/token/password/session 函数**。21 命令经 RpcCmdsCore@0x6df18 注册逐一经 literal pool 实证。
- **未授权影响**：**shutdown**@0x6fe3c（单包远程 DoS，Restart=always 可循环打挂）；**log**（未授权操纵日志级别 = 反取证静默）；**sdavc** handle_enable_https@0x6dcc4（未授权改 SD-AVC 外联配置）；activate/deactivate/attach/detach（引擎状态操控 DoS）。**DoS×2**：① RpcTransportTCP::get_max_msg_size@0x4b228 = `mvn r0,#0`（-1 无限制）+ recv_msg_int@0x49eb0 16KB 循环 recv + `find("\n")`——无换行数据无限累积 → root 进程 OOM；② 请求路径走旧版 vendored Json::Reader（readValue@0x882d0 ↔ readObject@0x87e24/readArray@0x88838 互递归，无深度限制）→ 数十万层 `[[[…` 嵌套 JSON 栈溢出崩溃。
- **置信度**：确认（反汇编级；21 命令名逐一实证）。
- **复现路径**：objdump 0x6af3c/0x6bcd4/0x4bcf8/0x45e9c/0x43c78 链路；动态：`echo '{"jsonrpc":"2.0","method":"shutdown","id":1}' | nc <ip> 4040`。**注意**：rehost 最小 boot 未启动 nbar.service（4040 关闭），动态验证需先在 guest 内拉起 nbar.service。
- **修复建议**：
  1. `-s` 绑定改 127.0.0.1（nbar.service ExecStart），或改 unix domain socket + SO_PEERCRED 对端凭据校验；
  2. 增加认证：JSON-RPC 握手携带本地凭据/token；
  3. get_max_msg_size@0x4b228 的 -1 改具体上限（如 1 MiB），recv_msg_int@0x49eb0 按上限截断并断连；
  4. JSON 解析加深度限制（vendored 旧版 Json::Reader 无 depth 参数——升级 jsoncpp 并启用 maxDepth，或请求路径切换到二进制内已有的 OurReader 新实现）。
- **横向提示**（[audit-1] minor）：fastcgi 的 Json 解析器实体在 **libmeraki.so**（未审计），无认证端点（webauth.json 等）POST body 直入——stilecpd 同源旧版 Json::Reader 已证栈耗尽，libmeraki.so 为同类未审计风险（见 §4 待办）。

#### VULN-13 — stilecpd `unload`+`load` → dlopen 任意 .so = root RCE【Critical / 高（静态确认）】

- **类型**：任意代码装载 → RCE（与 tftpd :69 上传成链，S1）
- **利用链**：tftpd :69 未授权上传恶意 libntcp_k.so（VULN-20）→ stilecpd :4040 未授权 `unload` + `load {"path":"/tftpboot"}` → `dlopen("/tftpboot/libntcp_k.so")` → **root RCE**。前置仅 4040 与 69 网络可达（均无认证）。
- **证据**（[audit-3] major② + chain）：RpcCmdLoad::_run@0x6f36c（parse_path("path")：validate_path@0x44420 = stat+S_ISDIR，**仅验证目录存在、无白名单**）→ Engine::load_engine@0x60504（state>0 时 throw，需先 unload）→ EngineKM::load_engine_int@0x66c5c → load_kms@0x669fc（**内核模块路径固定 "../modules/ntdp.ko"@0x9e3dc，与 RPC path 无关——insmod 变体不成立，RCE 落在 dlopen**）+ load_so@0x66860：`path.append("/libntcp_k.so",13)`（str@0x9e36c）→ **`dlopen(full, RTLD_NOW=2)`@0x668d8** → 攻击者 .so 构造函数即 root 执行。前置：① 先 `unload`（RpcCmdUnload::_run@0x6f248 → dlclose+delete_module，复位 state/句柄）；② path 指向任一已存在目录（/tmp、/tftpboot 均满足）。合法引擎库 /usr/lib/libntcp_k.so 与内核模块 /lib/modules/ntdp.ko 均在 rootfs 实证存在。
- **置信度**：高（静态确认）——dlopen 数据流反汇编级实证；组合链依赖 tftpd 上传（配置事实确认，inventory L69）。
- **复现路径**：objdump 0x6f36c/0x66860–0x668d8/0x44420；动态：`tftp <ip> -c put libntcp_k.so` → nc 4040 发 unload/load JSON → 观察 dlopen。
- **修复建议**：
  1. validate_path@0x44420 白名单化：仅允许固定引擎目录（/usr/lib），拒绝 /tmp、/tftpboot 等可写目录；
  2. 更根本：load_so@0x66860 的 dlopen 路径不取 RPC path——固定为 /usr/lib/libntcp_k.so（与内核模块路径同为固定值的现有做法一致）；
  3. 依赖 VULN-12 的绑定/认证修复兜底（4040 不可达则本条不可达）。

### 第二梯队：疑似链 / 依赖缺环

#### VULN-11 — capwapd FLEX_SLAVE_DOWNLOAD 命令注入（TLV 0xf4 → popen；远程可达性缺环在 wcpd）【High（若缺环闭合）/ sink 确认、远程可达性推测】

- **类型**：OS 命令注入 → RCE
- **利用链**：控制内部 WCP TLV 0xf4 内容（经 Unix socket /tmp/capwap_wcp_msg ← **wcpd**）→ strncpy 镜像名 → ImageActivateTask → popen → capwap-upgrade.sh → curl 裸拼 → 任意命令（capwapd 特权进程）
- **证据**（[audit-2] major，反汇编级全链）：① 入口 TLV 0xf4 AP_MASTER_SLAVE_CONFIG_PAYLOAD 解码器 0xf6abc（内部 WCP payload 注册表 0x1d847c 项 0x1dc03c）：0xf6f50–0xf6f84 `memset(struct+0x44c9,0,255)` 后 `strncpy(struct+0x44c9, src, 255)`@0xf6f80（len=msg[6]，**≤255 字节镜像名、无元字符过滤**），并置状态 [struct+0x44ac]=20；② 触发 ImageActivateTask（0x613a0/0x61424 `cmp r3,#20`）→ 0x61474 调 0x60f80；③ sink 0x60f80：0x61024–0x6103c `snprintf(sp+328,256,"/etc/capwap-upgrade.sh -r %d -s %s -n %s FLEX_SLAVE_DOWNLOAD",…)` → **`popen(sp+328,"r")`@0x61074**（备分支 "/usr/bin/cli_scripts/image_download.sh -l %s -m 2 -x" 亦 popen）；server 参数安全（0x5d80c：IPv4 "%u.%u.%u.%u"/IPv6 inet_ntop）。④ 脚本侧无过滤（correlator 复核原文）：/etc/capwap-upgrade.sh:93 `flex_slave_ap_download ${tftp_download_retry} ${tftp_server_ip} ${tftp_image_name}`（无引号）→ capwap-upgrade-func.sh:1291 `/usr/bin/curl … tftp://${tftp_server_ip}/${tftp_image_name} -o $TMP_AP_FILE`（**变量裸拼**，`;`/空格/反引号均注入）。第二调用方 ImageEwlcDownloadTask 0x61e60 同构。
- **缺环（决定远程可达性）**：wcpd 如何产生 TLV 0xf4 未审计。correlator 拼装同向线索：[audit-0] minor 记录 config_set_firewall.cgi(0x12fe0) 防火墙规则字符串 → `send_ipc_to_capwap` → capwapd/wcpd 侧消费——若该管道通向 TLV 0xf4 构造，则 fastcgi 配置字符串 → capwapd popen 成跨 binary 链（C1）。**wire 侧直接路径已排除**（[audit-2] chain）：wire Discovery 解码器（AC_DESCRIPTOR 0xf2a2c 定长 20 检查 / IMAGE_FILENAME 0xf3788 魔数+仅写 4 字节 / AC_NAME 0xf2b44 cap 31 / 0xf3880 cap 255）均界内。
- **置信度**：sink 链确认（反汇编实证）；远程可达性推测（依赖 wcpd）。
- **复现路径**：objdump 0xf6abc–0xf6f84 / 0x60f80–0x61074 / 0x61424–0x61474；`sed -n '93p' $R/etc/capwap-upgrade.sh`；`sed -n '1291p' $R/etc/capwap-upgrade-func.sh`。待办：wcpd 产生 TLV 0xf4 的路径审计。
- **修复建议**：
  1. 0xf6f80 strncpy 后对镜像名做文件名白名单（`^[A-Za-z0-9._-]+$`，长度 255 上限已有）；
  2. 脚本侧 capwap-upgrade-func.sh:1291 的 curl URL 变量加引号并校验字符集（capwap-upgrade.sh:93 同）——纵深防御，二进制修复后仍应做；
  3. 0x61074 popen 改 execv（脚本调用无需 shell）；
  4. wcpd 侧 TLV 0xf4 构造点同加白名单（待 wcpd 审计定位后落点）。

#### VULN-17 — capwapd 版本串 → system() 三处无过滤（32 字节上限）【Medium / sink 确认；可达性同 VULN-11 缺环】

- **类型**：OS 命令注入（短 payload）
- **证据**（[audit-2] minor）：版本缓冲写入者 0x140a50–0x140a5c `strncpy_s([global+0x138c], src, 32)`（TLV 处理器 0x140934 家族）。未净化消费：① ewlcImageTimerHandler 0x60888–0x60890 `system("echo 'ws_management_version: %s' > /part2/mewlc_info.ver")`；② ImageWriteTask 0x61ca4–0x61cbc `system("/etc/capwap-upgrade.sh -m MASTER -v %s PREDOWNLOAD")`；③ 0x5ff0c–0x5ff14 `system("/etc/capwap-upgrade.sh COMPARE_MEWLC_VERSION %s")`。32 字节内 `;cmd` 类短 payload 可注入。
- **置信度**：sink 确认；可达性同 VULN-11 缺环（TLV 配置面/wcpd）。
- **复现路径**：objdump 0x140934–0x140a7c / 0x60888 / 0x61ca4 / 0x5ff0c。
- **修复建议**：版本串语义为版本号（`[0-9A-Za-z()._-]`），在 0x140a50 strncpy_s 后做白名单校验；三处 system 消费点改 exec 族。

#### VULN-18 — capwapd DTLS 证书校验宽松【Medium / 代码确认；运行态策略位未验证】

- **类型**：传输层认证弱化
- **证据**（[audit-2] minor）：dtls_cert_verify_callback@0x68244：X509 err 10（证书过期）+ MIC 检查（0x681d8）通过 → 'Allowing expired MIC certificate' → 返回 1 接受；另有全局策略位 [state+0x46f0]（0x49c00–0x49c08 从配置 +0x4e0 拷贝）==1 时**无条件接受**。Discovery 族消息按 RFC 5415 恒明文，ME 主选举入口 wtpProcessPrimaryDiscoveryResponse@0x45874 → 0x3fc80 → 0x45aec 链运行于明文。
- **利用链**：相邻网络位置 → 呈现过期 MIC 证书（或触发策略位）→ 伪造 WLC/中间人面扩大。明文 Join 是否被接受未完成验证。
- **置信度**：代码确认；运行态策略位取值未验证。
- **复现路径**：objdump 0x68244–0x68290 / 0x49c00。
- **修复建议**：移除 0x68244 的"过期 MIC 证书接受"分支（过期即失败）；全局策略位默认拒绝、仅显式配置开启并记录审计日志；Discovery→Join 升级路径强制 DTLS。

#### VULN-6 — wcpd/click 侧未审计消费面（redirecturl 二阶注入 + 异步自授权）【High（若闭合）/ 推测】

- **类型**：潜在二阶注入 / 授权绕过（延续上轮，未闭合）
- **证据**（[audit-0] chain 本轮新增 + 上轮 VULN-6）：redirect.cgi(0x67ec，无认证，:1233/:1234 强制门户将任意原始 URL 拼进 redirecturl) → 0x68c0 `click_read_param(结果, "/click/webauth_helper/query_redirect_url"@0x1bca5, sbuild("%s",redirecturl))`——redirecturl 经 unix socket 进 click 元素；fastcgi 侧无 shell sink（开放重定向为强制门户设计行为）。**消费端在 wcpd/click 侧，未审计**——若该元素处理拼 shell 则二阶注入。上轮异步授权模型（reqid 轮询 + wcp socket 写入方权限）未闭合。端点模型修正（[audit-0] chain）：fastcgi 分发表 28 项中无任何 /click/ URL——`/click/webauth_helper/query_redirect_url`、`/click/client_ip_table/set_vap_nat` 为 clickfs 元素路径，不是可请求端点；set_vap_nat 逻辑挂载在 /oeap/config_set_dhcp.cgi 且参数经 IPAddress/纯整数处理，无注入。
- **利用链（条件）**：无认证 redirect.cgi → click webauth_helper 元素 → wcpd/click 侧消费（缺环）→ 若拼 shell 则 RCE。
- **置信度**：推测（fastcgi 侧数据流已证，消费端语义缺环）。
- **复现路径**：objdump 0x67ec–0x6920 核对 click_read_param 调用；待办：wcpd/click 工单。
- **修复建议**：待 wcpd/click 审计闭合后定（fastcgi 侧本身无 sink）；可先行对 redirecturl 做长度/字符集预限制（≤512 字节、拒绝元字符），降低下游未审计消费面的风险敞口。

#### VULN-15 — stilecpd push_pcap 任意文件读取 oracle + ppack 任意已存在文件喂引擎【Medium / 高度可疑】

- **类型**：信息泄露 oracle / 潜在内存破坏入口
- **证据**（[audit-3] minor×2）：① RpcCmdPushPCAP::_run@0x722e4：filename 走 parse_string（**非 parse_file——无 stat/白名单校验**）→ push_filename@0x71e8c → Engine::push_pcap@0x61384 → CCapReaderFactory::CreateReader@0x8ffd8 → `fopen64(原始 RPC 路径)`——文件按 pcap 格式解析，响应/错误构成**存在性 oracle**（可探测 /etc/passwd、shadow 等）；内容级回读需运行期验证。② RpcCmdPPACK::_run@0x6e9e0：parse_file → validate_file@0x44390（stat+S_ISREG 仅存在性）→ Engine::load_ppack@0x608d4——解析器在 /usr/lib/libntcp_k.so（本 binary 外），畸形 ppack 是否致引擎内存破坏未验证。
- **利用链**：4040 可达零认证（VULN-12 前置）→ push_pcap 探测文件存在性 / ppack 喂畸形文件给引擎解析器。
- **置信度**：高度可疑（oracle 静态确认；内容回读/内存破坏待动态）。
- **复现路径**：objdump 0x722e4/0x71e8c/0x61384/0x8ffd8；0x6e9e0/0x44390/0x608d4。
- **修复建议**：push_pcap 的 filename 从 parse_string 改 parse_file（走 0x44420 validate_file）并加目录白名单（如仅 /tmp/*.pcap）；ppack 同理限定目录白名单；配合 VULN-12 认证修复兜底。

#### VULN-16 — stilecpd collect set_exporter / sdavc 任意外联配置 + file 模式任意路径写【Medium / 高度可疑】

- **类型**：未授权外联（exfil/beacon）/ 任意路径写
- **证据**（[audit-3] minor）：handle_collect_set_exporter@0x6d650：socket{server,port,path}，type∈{http,https,http-flat,https-flat,file,none} → ExporterConfig::set_server@0x743d4 / set_mode_file@0x7445c 等 → Engine::collectors_set_exporter@0x7532c。http(s) 族 = 未授权将 NBAR 采集数据导向任意 server:port（设备侧外联/数据外发原语，非经典 SSRF）；file 模式 = 采集数据写任意路径文件（写语义在引擎 .so 内未完全走读）。sdavc handle_enable_https@0x6dcc4 同类。
- **利用链**：4040 可达零认证 → collect set_exporter 指向攻击者 server:port → 设备定期外联（beacon/数据外发）或写任意路径。
- **置信度**：高度可疑（配置写入流反汇编确认；外联实际发起/写语义在 libntcp_k.so 未走读）。
- **复现路径**：objdump 0x6d650–0x6dcc4 / 0x743d4–0x7445c。
- **修复建议**：exporter server 参数做 IP/hostname 格式白名单；file 模式路径限定可写目录白名单；外联配置变更要求认证（VULN-12 修复）。

### 第三梯队：孤立发现与配置级风险

#### VULN-14 — config_set_ssid.cgi `wl_unit` sprintf 栈溢出（10 字节受限）【Medium（DoS）/ 确认（crash）】

- **类型**：栈溢出（受限，不可直达返回地址）
- **证据**（[audit-1] major）：函数 0x8724（与 VULN-3 同函数同入口）。wl_unit(int 无校验)@0x8b24 → 存 config+0x17d44 → ∉{0,1} 走 0x90f0 → gate（config+0x17c00+0x164=="allow"）→ 0x96e8 `bl 0x8724` → 0x8844 读 /storage/config.oeap → 循环 i=0..15：0x8868 memset(sp+56,0,15) + 0x887c `sprintf(sp+56,"wl_maclist%d_%d"@0x1c2f7, i, wl_unit)`——最长 "wl_maclist15_-2147483648"=25B **溢出 10 字节进 sp+72 的 HashMap 对象** → 0x8888 `bl 6788` 解引用被数字字节覆盖的首字（如 2147483647 → 0x33383437 wild pointer）→ SIGSEGV。
- **利用链**：/oeap/ Basic auth 后（或无认证经 testfastcgi，flag=8 被遍历）→ ① POST config_set_ssid.cgi `wl_unit=1&wl_macmode=allow`（置 gate 字段）→ ② POST `wl_unit=2147483647` → 崩溃。前置：/storage/config.oeap 存在且非空。
- **限制**：溢出字节仅数字/'-'/NUL；0x8724 帧缓冲最大写至 sp+81 < 保存寄存器区 sp+108——**不可直达返回地址**，定级 crash/DoS。
- **置信度**：确认（crash）；超 DoS 利用性低。**勘误上轮**：上轮"1 字节 NUL 溢出进栈 padding 不可利用"的证伪记录已被本轮修正。
- **复现路径**：objdump `--start-address=0x8724 --stop-address=0x88a0` 核对 0x887c/0x8888。
- **修复建议**：① 0x8b24 取 wl_unit 后立即校验 ∈{0,1}，非法值返回错误响应（当前逻辑对非法值继续走 0x9100/0x90f0 路径才是缺陷）；② 0x887c `sprintf` 改 `snprintf(sp+56, 15, ...)`——相邻 memset(sp+56,0,15) 已表明 15 字节意图，格式串 "wl_maclist%d_%d" 最长 25B 必然越界，或缓冲扩至 32 字节并同步调整布局。

#### VULN-19 — sshd `PermitEmptyPasswords yes` + 特权本地账户【Medium（若运行期口令为空）/ 推测】

- **证据**（[unpacker] minor）：sshd_config.me `PermitEmptyPasswords yes`、`DenyUsers root`；镜像无 shadow 文件（运行期生成）；passwd 中 support(uid=1)/rsyncuser(uid=5,**gid=0**) 带 /bin/ash shell。etc/dropbear/authorized_keys 存在但为空（无预置密钥后门）。
- **利用链**：:22 可达 + 运行期口令为空 → 无口令 SSH → 本地特权（rsyncuser gid=0）。
- **置信度**：推测（配置事实确认；运行期口令状态需动态——rehost 最小 boot sshd 未运行）。
- **修复建议**：`PermitEmptyPasswords` 改 no；移除 support/rsyncuser 账户的交互 shell（服务账户设 /sbin/nologin）；或 DenyUsers 追加两账户。

#### VULN-20 — tftpd-hpa :69 未授权任意文件上传【Medium（独立）/ Critical（作为 VULN-13 前置）/ 确认（配置事实）】

- **证据**（inventory L69）：tftpd-hpa.service `-L -M 8 -C /tftpboot`——**-C 允许客户端创建新文件（上传面）**，UDP :69 无认证。
- **利用链**：无前置 → `tftp <ip> -c put <file>` → ① 恶意 libntcp_k.so 供 stilecpd dlopen（VULN-13/S1 链）；② capwapd 从 /tftpboot/%s-pre%d...tar 取文件（surface.md §3）——投毒固件包/脚本的潜在链素材。
- **置信度**：确认（配置事实）；上传行为待动态（rehost 最小 boot tftpd 未运行）。
- **修复建议**：移除 `-C` 标志（只读模式）；如必须保留上传，/tftpboot 改 tmpfs + noexec + 定期清理，并与 VULN-13 的 load path 白名单修复联动。

#### VULN-21 — redis 硬编码口令（loopback）【Low / 确认（配置事实）】

- **证据**（[unpacker] minor）：etc/redis.conf 硬编码密码 `w!r3L3sS@CSCO`，bind 127.0.0.1，**protected-mode no**。
- **利用链**：任意本地执行/SSRF 原语（loopback 可达）→ 已知口令直连 redis → 写 RDB/模块 = LPE 借力（surface.md §3：redirect.cgi/testfastcgi.cgi 若可发起请求则可借力）。
- **置信度**：确认（配置事实）；无独立远程可达性。
- **修复建议**：移除硬编码 requirepass（改部署期生成或随机化）；protected-mode 改 yes。

#### VULN-22 — memcached 1.5.7 绑定 0.0.0.0:11111（SASL）【Medium / 确认（版本与绑定事实）；漏洞面待核】

- **证据**（inventory L70 + correlator strings 实证）：memcached.service **0.0.0.0:11111 与 [::]:11111**，SASL(-S)，DCDS 数据服务。版本 **memcached 1.5.7**（2018 年代）。planner 移交"版本已知问题核对 CVE"——correlator 按角色约束未做外部 CVE 检索，仅钉住版本供后续核对。
- **置信度**：确认（版本与绑定事实）；漏洞面待核。
- **修复建议**：升级 memcached 至当前维护版本；11111 绑定改内网接口或 loopback + 防火墙规则；SASL 凭据强制（当前 -S 已启用，需确认账号配置非空）。

---

## 3. 利用链分析

### 3.1 W1 — Web 面三条独立 pre-auth root RCE（确认）

| 入口 | 路径 | 依据 |
|---|---|---|
| A | `GET /set_universal_ap_reg_domain.shtml?location=;PAYLOAD;`（VULN-2，system@0x9ce8 直达） | [audit-0] chain |
| B | `POST /testfastcgi.cgi` body `wl_unit=1&wl_macmode=allow&wl_maclist0=;PAYLOAD;`（VULN-4→VULN-3，run_system@0x89e0） | [audit-0] chain |
| C | `GET /webauth/webauth.json?clientid=;PAYLOAD;`（VULN-1，强制门户面，run_system@0x10b98） | [audit-0] chain |

三条互相独立、均单请求、均无认证、均 root（fastcgi 以 root 运行，system 继承）。持久化共用出口：payload 写 /www/x.sh + cgi.assign(".sh"=>"/bin/sh") → `GET /x.sh` 二次触发。rehost 实测三入口端点均 pre-auth 200 可达（192.168.100.1）。

### 3.2 W2 — 凭据重置→管理面全权（确认写入动作；登录效果待动态）

`POST /testfastcgi.cgi`（任意参数，VULN-4）→ 遍历调用 resetlogin.json（VULN-9）→ 管理凭据变为已知默认（admin/admin）→ /oeap/ + /configure/ 认证后全族可达 → 再走认证后注入/上传。**张力**：lighttpd 1.4.54 不认裸 sha256（rehost L3-修复 7 实测），resetlogin 实际效果可能是默认凭据可登录或 Basic auth 锁死（认证 DoS）——两种后果均为未授权安全事件，PoC 阶段实测裁定。

### 3.3 W3 — 任意写→持久化 RCE（高度可疑）

`POST /testfastcgi.cgi`（body 为伪造 tar，VULN-4）→ firmwareupload.cgi tar 穿越（VULN-5）→ 写 `../../www/x.sh` → cgi.assign(".sh"=>"/bin/sh") → `GET /x.sh` → root shell。**全程无认证**。tar 穿越语义（GNU tar `../` 成员）需 PoC 验证。

### 3.4 W4 — 配置投毒→时间转移注入（高度可疑）

同 W3 入口 → 解包出的 config.oeap 被 load_oeap_specific_config 读入并 save 到 /storage/config.oeap → 其中 `wl_maclist%d_%d` 键在**下一次** config_set_ssid ACL 同步（0x8724 第二循环）以 `delete_local_ssid_acl_entry %s` 进 `run_system`@0x8a4c——上传时无害、触发时注入。第二循环数据流已反汇编级实证（[audit-0] chain）。

### 3.5 S1 — 服务面 root RCE（确认，静态）

tftpd :69 未授权上传恶意 libntcp_k.so（VULN-20）→ stilecpd :4040 未授权 `unload` + `load {"path":"/tftpboot"}`（VULN-12→VULN-13）→ `dlopen("/tftpboot/libntcp_k.so")` → root RCE。前置仅 4040 与 69 网络可达（默认全启动；rehost 需手动拉起 nbar.service/tftpd）。与 W3 的 `.sh→/bin/sh` 写链互为替代出口且互相独立（不同服务）。

### 3.6 C1 — 跨 binary 条件链（待验证，缺环在 wcpd）

fastcgi 配置字符串（防火墙规则等）→ `send_ipc_to_capwap` → wcpd → 内部 TLV 0xf4 → capwapd strncpy(0xf6f80) → popen(0x61074)（VULN-11）。两段证据均实证（[audit-0] minor + [audit-2] major），连接段（wcpd 转换）未审计。若闭合则 fastcgi 认证后配置面 → capwapd root 命令执行。**下一审计工单首选位置：wcpd**。

### 3.7 R1 — redirecturl 二阶注入（待验证，缺环在 wcpd/click）

无认证 redirect.cgi → click webauth_helper 元素（unix socket）→ wcpd/click 侧消费（VULN-6）→ 若拼 shell 则 RCE。与 C1 同指向 wcpd/click 工单。

### 3.8 反取证组合（确认）

VULN-4 → evt_log_clear.cgi 清空 /var/log/messages（Web 侧）+ stilecpd `log` 命令调级静默（VULN-12，4040 侧）——两服务均有无认证日志擦除/静默面，可组合清除攻击痕迹。

---

## 4. 覆盖面与方法

### 4.1 方法

- **静态审计**：全部结论基于 `arm-linux-gnueabi-objdump -d` 反汇编 + literal pool 字符串解析（audit-0/1）+ 自建 PC 相对字符串交叉引用工具（audit-2，9798 处 xref）+ Python ELF 程序头直读（audit-3），证据按函数/地址可复核，未凭 strings 猜测。
- **闭环纪律**：工单 hypotheses 逐条判定（audit-0 的 H1–H8、audit-2/3 的 checklist），证伪项全表记录（§4.4），供下游免复查。
- **配置事实复核**：correlator 对 lighttpd.conf auth.require/cgi.assign、capwap-upgrade.sh:93、capwap-upgrade-func.sh:1291 四处 load-bearing 事实直读原文核实；memcached 版本经 strings 钉为 1.5.7。
- **动态佐证**（rehost，FirmAE 改造形态全系统仿真，192.168.100.1）：pre-auth 端点（webauth.json/testfastcgi.cgi/get_universal_ap_reg_domain.xml/redirect.cgi/test_dump.cgi）实测 200；post-auth /oeap/* 以 Cisco/Cisco 可达（Basic auth 根因已修，decisions.md L3-修复 7）；命令注入取证通道为 serial log /tmp/ser34.log（wcp_write stub 逐参数回显）。

### 4.2 已覆盖

- **fastcgi**（两工单）：命令注入、认证绕过、内存破坏三角度全量；22 处 run_system/run_system_capture + 6 处 system@plt 调用点全表处置（注入仅 6 处：0x89e0/0x8a4c/0x10b98/0x9ce8/0x9d24 及其组合）；28 项 URL 分发表逐项定性；strcpy/strncpy/snprintf/memcpy/read/sscanf 全表分类。
- **capwapd**（一工单）：三套 payload 注册表（wire 消息类型 0x1d66bc / wire 消息元素 0x1d703c / 内部 WCP TLV 0x1d847c 共 248 项）结构定性；FLEX 升级链全走读；版本串 system×3；DTLS 回调；分片重组、sscanf 25 处全表证伪；升级脚本逐行核对。
- **stilecpd**（一工单）：零认证面全链、21 命令逐一 literal pool 实证、load/dlopen、DoS×2、文件 oracle、exporter 外联、RpcZip/str_to_level/Coffee 证伪。
- **配置级**：lighttpd 认证边界与 cgi.assign、tftpd-hpa、sshd、redis、memcached（版本钉住）。

### 4.3 未覆盖（明确边界——本报告可信度的一部分）

**被裁剪的审计目标**（planner 决策，理由见 surface.md §2）：
- **wcpd**——产生内部 TLV 0xf4 的路径未审计（VULN-11/17 远程可达性与链 C1 闭合的关键缺环；含 fastcgi send_ipc_to_capwap → wcpd 的配置字符串管道）。**下一轮投入产出比最高位置**。
- **libmeraki.so Json 解析器**——fastcgi 的 Json/click_read_param 实体在此库；无认证端点（webauth.json 等）POST body 直入；stilecpd 同源旧版 Json::Reader 已证栈耗尽（VULN-12②），同类风险未审计。
- **ap1g1 IOS httpd**——planner 以"PPC 单体体系不同"裁剪；rehoster 勘误实为 **mips-be**，补审成本降低。目标：html/level/15 表单 image_upgrade_tftp_server_address/image_upgrade_image_path 等入口与 sink。unicorn 契约就绪（agents/rehoster/unicorn_harness_fixed.py，基址 0x80080000，kseg0 物理别名已处理）——**该平台本轮零覆盖**。
- **nginx（:445/:448 反代 ME VM）与 ME VM 侧**——dynrest YAML 路由的消费方在 rootfs 内未定位（fastcgi 与全 rootfs grep 均无引用，倾向 ME VM 侧），未审计。
- **capwapd 残留**：0x44664 wire TLV 循环对逐元素长度未在循环内复核（元素 len 递减可为负→**潜在越界读**，未见越界写，未计入候选）；66 处 strcpy/291 处 memcpy 全表分类未完成（解析路径抽检未见无界写）；mwar_addr_list/lrad 未走读。
- **sshd/tftpd-hpa/memcached/redis**——配置级记录（VULN-19/20/21/22），未做二进制静态深审（planner 裁剪理由：上游软件/配置级风险归动态阶段）。

**待动态验证项**（静态不可判定，转 PoC 阶段）：
- /configure/ 前缀归一化绕过（lighttpd 1.4.54 mod_auth 层行为——未证实也未证伪，不计入候选）
- VULN-5 tar 穿越落盘语义、VULN-9 resetlogin 后登录效果、VULN-10 下载包内容、fastcgi crash 影响面（进程模型）、VULN-19 sshd 运行期口令状态
- VULN-12/13/15/16/20：rehost 最小 boot 未启动 nbar.service/tftpd/sshd/memcached（:22/:4040/:69/:11111/:64999 关闭），需在 guest 内拉起对应服务后验证
- VULN-11/17/18（capwapd）：capwapd 当前未运行，静态地址已钉住

**固件来源注记**：zip 下载截断（EOCD 缺失），ap1g4 完整副本取自 workdir/archive/ 经 SHA-512 清单 + 43.6MB 前缀逐字节比对双重验证——非降级，但审计基于 archive 副本，与官网分发件的一致性以该双重验证为准。

### 4.4 主要证伪清单（供下游免复查）

- capwapd 分片重组溢出（0x40f54：16000B 缓冲保证 + 每分片上限检查 + 偏移一致性 + 分片数上限）；capwapd sscanf（25 处仅 1 处 %s 且为错误打印路径）；tftp://%s/mewlc.bin 系列（%s 为 inet_ntop 输出）
- fastcgi 22 处 run_system 全表：注入仅 6 处（已列 VULN-1/2/3），其余 16 处固定串/纯整数安全；execl/popen 包装（0x179a4/0x1900c/0x19048）无调用者（死代码）
- fastcgi 内存破坏全表：strcpy×1/strncpy×4/snprintf×3/memcpy×8/read 循环/sscanf/gets/strcat 均安全；firmwareupload multipart 解析无内存破坏；残留潜伏缺陷：内嵌 vformat 宽度/精度转换经 ~104B 栈缓冲（0x19c04 帧）——**现版本全部格式串无宽度/精度 %s，不可达**，新增带宽度格式串即触发
- config_set_wan/dhcp/firewall.cgi 注入（wan 无 shell sink；dhcp sink 纯整数；firewall 参数→send_ipc_to_capwap，消费面转 C1）；dynrest（fastcgi 非 dynrest 消费者）
- stilecpd RpcZip 压缩面死代码 / str_to_level 纯 compare 链 / Coffee 无 system（H7/H8 证伪）
- 上轮 VULN-8 登录枚举 oracle（三重证伪撤销）

---

## 5. 附录：run 产物索引

| 产物 | 路径 |
|---|---|
| 本报告 | `workdir/artifacts/report.md` |
| correlator 候选漏洞清单 | `workdir/artifacts/vulns.md` |
| 全部审计发现（[unpacker]/[audit-0..3] 条目，证据本体） | `runs/20260917-041115/memory/findings.md` |
| 攻击面地图（候选全景/取舍/chain 提示） | `runs/20260917-041115/memory/surface.md` |
| 决策记录（planner 选单、rehoster backend/修复、correlator 拼链） | `runs/20260917-041115/memory/decisions.md` |
| 流水线上下文 + rehost 环境契约 | `runs/20260917-041115/memory/context.md` |
| unpacker 固件盘点 | `workdir/extracted/air-ap1850-k9-me-8-10-130-0/inventory.md` |
| planner 工作总结 | `runs/20260917-041115/agents/planner/summary.md` |
| 4 份审计工单 skill | `runs/20260917-041115/plan/skills/{fastcgi-cmdi-authbypass,fastcgi-memcorrupt,capwapd-cmdi-memcorrupt,stilecpd-authbypass-memcorrupt}/skill.md` |
| audit-0 工作总结 | `runs/20260917-045450/agents/audit-0/summary.md` |
| audit-1 工作总结 | `runs/20260917-045450/agents/audit-1/summary.md` |
| audit-2 工作总结 | `runs/20260917-045450/agents/audit-2/summary.md` |
| audit-3（summary 未产出，以 findings.md [audit-3] 段为准） | `runs/20260917-045450/agents/audit-3/memory.md` |
| rehost ap1g4 仿真（运行中，192.168.100.1） | 内核 /tmp/zImage.armel + /tmp/orig.dtb + FirmAE scratch/300/image.raw；serial /tmp/ser34.log；启动/停止命令见 memory/context.md |
| rehost ap1g1 unicorn harness | `runs/20260917-041115/agents/rehoster/unicorn_harness_fixed.py`（镜像 `workdir/extracted/air-ap1850-k9-me-8-10-130-0/ap1g1/ios_unpacked/-`，基址 0x80080000，mips-be） |

---

*报告完。置信度与证据均忠实转述自 correlator（vulns.md）与各 auditor（findings.md）原始条目；动态验证（PoC）由 poc-planner/finalizer 节点接力。*
