# 候选漏洞清单 — correlator（run 20260917-041115）

固件：Cisco AIR-AP1850-K9 **Mobility Express 8.10.130.0**（ap1g4 主 rootfs，arm-el，Linux 3.4.103）
ROOTFS=`/home/fjw/workspace/flow/iot_hunter/workdir/extracted/air-ap1850-k9-me-8-10-130-0/ap1g4/_part.bin.extracted/rootfs`
证据基线：memory/findings.md 的 [unpacker]/[audit-0]/[audit-1]/[audit-2]/[audit-3] 条目（全部带反汇编地址，可按地址复核）+ surface.md + planner summary + rehost 环境契约（context.md）。
排序规则：确认的完整链 > 疑似链/依赖缺环 > 孤立发现与配置级风险。共 20 条（第一梯队 9、第二梯队 6、第三梯队 5），另撤销上轮 2 条（见映射表）。

**编号延续说明**：沿用上轮 run 20260915-095054（同版本固件）的编号（语义不变者保留原号），新发现自 VULN-9 起编号。rehost 环境 context.md 中引用的 VULN-N 为上轮编号，按下方映射表换算。

## 与上轮清单（20260915-095054）的映射

| 上轮 | 本轮 | 变化 |
|---|---|---|
| VULN-1 webauth.json clientid 注入 | VULN-1 | 复确认（同地址 0x10ab0/0x10b98）；rehost 实测端点无认证 200 |
| VULN-2 set_universal 注入 | VULN-2 | 复确认；**主向量修正为 `location`（无截断）**，regDomain5/24 经 strncpy(3) 仅 ≤2 字符元字符（辅助） |
| VULN-3 认证后注入族 | VULN-3 | wl_maclist 分支指令级确认 + 经 testfastcgi **升级为 pre-auth**；postlogin.cgi topage 分支本轮**证伪**（0x7828 仅置会话标志+重定向，无 shell） |
| VULN-4 testfastcgi 信息泄露 | VULN-4 | **大幅升级**：全分发表遍历 = 通用认证绕过原语（22 个 handler 无认证执行）；test_dump.cgi 降级为调试回显（并入本条） |
| VULN-5 tar 路径穿越 | VULN-5 | 复确认 + 经 testfastcgi 升级 pre-auth + 新增时间转移注入升级路径 |
| VULN-6 webauth 异步自授权（推测） | VULN-6 | 本轮未再审计；新增 redirect.cgi → click webauth_helper 线索（消费端同在 wcpd/click 侧） |
| VULN-7 capwapd 内存破坏（未审计推测） | **撤销** → VULN-11/17/18 | 本轮 audit-2 已审：分片重组/sscanf/wire 解码器证伪；新发现 TLV 0xf4 注入、版本串 system×3、DTLS 宽松 |
| VULN-8 登录错误串枚举 oracle | **撤销** | 上轮 finalizer 执行级证伪（四象限同响应）+ 本轮 rehost 复测（{"login_unsafe":true} 为默认口令标志非判别 oracle）+ audit-0 复核 authenticate_user.json(0xaa74) 不读请求参数 |

---

# 第一梯队：确认的完整利用链（无认证可达）

四条互相独立的 pre-auth root RCE 入口（VULN-1/2/3），一个通用认证绕过原语（VULN-4）及其直接产物（VULN-9/10/5），以及独立于 Web 面的 stilecpd dlopen 链（VULN-12/13）。除注明外均默认网络可达即可触发（80/443/1233/1234 开放即够）。

## VULN-1: /webauth/webauth.json `clientid` 无认证命令注入（单请求 root RCE）
- 类型：OS 命令注入 → RCE / 严重度：**Critical**
- 涉及组件与证据：$ROOTFS/usr/bin/fastcgi，handler 0x10ab0（分发表 /webauth/webauth.json，flag=0x11）。[audit-0] major④：clientid 读取 @0x10ad0；username 为空（[sp+48]==0 判空 @0x10b44）走 passthru 分支；0x10b6c–0x10b84 `sbuild(sp+164, "wcp_write wcp/wcp_db.set_webauth_done_to_fcgi %s 1"@0x1d328, clientid.c_str())` → `run_system(sp+164,1,0,0)`@0x10b98，前导 syslog(7,"passthru …")@0x10b68。**clientid 无过滤直入 shell**。webauth 为强制门户流程端点，:80/:443/:1233/:1234 设计上须登录前可达；lighttpd auth.require 仅覆盖 `/configure/`+`/oeap/`（$ROOTFS/etc/lighttpd.conf L87-96，本轮 correlator 复核原文）。上轮 audit-0/audit-2 双重记录同地址（0x10b84→0x10b98）。同族 webauth_result.json(0x10738) 已核实安全（clientid/requestid/authorized 仅 syslog+JSON 应答）。
- 利用链：无前置（pre-auth）→ `GET /webauth/webauth.json?clientid=;PAYLOAD;&redirecturl=x`（无需 username）→ sbuild %s 拼接 → run_system → root 任意命令（fastcgi 以 root 运行）。
- 置信度：**确认**。反汇编级全数据流；rehost 实测该端点无认证 200 可达（context.md rehost 段端点清单）。
- 复现路径（静态级）：`arm-linux-gnueabi-objdump -d --start-address=0x10ab0 --stop-address=0x10c00 $ROOTFS/usr/bin/fastcgi` 核对 0x10ad0/0x10b44/0x10b84/0x10b98。动态：curl 带 URL 编码 payload（query parser 0xa1c8 先 cp_urlunescape），serial log /tmp/ser34.log 看 wcp_write stub 参数回显与 /bin/sh "not found" 痕迹取证。

## VULN-2: /set_universal_ap_reg_domain.shtml `location` 无认证命令注入（单请求 root RCE）
- 类型：OS 命令注入 → RCE / 严重度：**Critical**
- 涉及组件与证据：fastcgi，handler 0x99bc（分发表第 3 项，str@0x1d95c，flag=4，URL 在 auth.require 之外）。[audit-0] major①：参数 configMode(int, atoi@0x9abc)/location(sp+76)/regDomain5(sp+40)/regDomain24(sp+52)（strncmp 长度 10/8/10/11 匹配）→ 3 条固定 run_system_capture 读当前 wcp 状态 → 守卫 0x9c4c–0x9c88（13520 String 相等：任一不等→应用路径 0x9fac——默认状态即不等，必走）→ sink 0x9cb8–0x9ce8 `snprintf(sp+272,128,"wcp_write wcp/dot11_tx_power_2g.set_domain %d %s %s %s",configMode,regDomain24[strncpy(dst,3)],regDomain5[strncpy(dst,3)],location.c_str())` → `system(sp+272)`@0x9ce8；5g 同款 0x9d10–0x9d24。**location 经 hard_c_str 无任何过滤直入 system()**（前缀约 51 字节 → ~76 字节 payload 空间，`;telnetd -l /bin/sh -p 9999;` 类足够）；regDomain5/24 经 strncpy(dst,src,3) 仅能注入 ≤2 字符元字符（辅助）。[audit-1] chain 证实 snprintf 定长 128 无溢出（注入是唯一缺陷）。执行后 0x9e50 `/sbin/reboot -r "%d: UX PRIMING VIA APP"`——payload 先于 reboot 运行。
- 利用链：无前置（pre-auth）→ `GET /set_universal_ap_reg_domain.shtml?configMode=1&location=X;PAYLOAD;&regDomain5=A&regDomain24=B` → system() → root 任意命令。持久化出口：payload 写 /www/x.sh，lighttpd `cgi.assign=(".sh"=>"/bin/sh")`（lighttpd.conf L78-80，本轮复核原文）→ GET /x.sh 二次触发。该 handler flag=4（bit0 清零）亦可经 /testfastcgi.cgi 触发（VULN-4）。
- 置信度：**确认**。反汇编级；上轮 VULN-2 同地址复确认（本轮修正主注入向量为 location）；rehost 实测 /get_universal_ap_reg_domain.xml pre-auth 200，set_universal 同在认证边界外（context.md：可直接复验，"location 为无截断向量"）。
- 复现路径：objdump `--start-address=0x99bc --stop-address=0x9e60` 核对 0x9c4c–0x9c88/0x9cb8–0x9ce8/0x9d24；grep lighttpd.conf auth.require。

## VULN-3: config_set_ssid.cgi `wl_maclist%d` 命令注入（经 testfastcgi 无认证；直接路径认证后）
- 类型：OS 命令注入 → RCE / 严重度：**Critical**
- 涉及组件与证据：fastcgi，handler 0x8ab8（/oeap/config_set_ssid.cgi，flag=8→bit0 清零→被 testfastcgi 遍历调用）。[audit-0] major③：wl_unit==1 路径 0x8be4–0x8c00 **无条件**把 wl_macmode 写入 config+0x17c00+0x164（即 gate 检查字段）→ gate 0x96b8–0x96c8 检查 =="allow"（str@0x1b7a6）→ 0x96e8 `bl 0x8724(param_map, radio)`（全 binary 唯一调用者，与 VULN-14 同函数）→ 0x8724 第一循环 0x8764–0x87cc 对 i=0..15 取 **POST 值** wl_maclist%d push 进 Vector → sink 0x89b4–0x89e0 `sbuild("wcp_write wcp/Radio%d.add_local_ssid_acl_entry %s", radio, vec[i].c_str())` → `run_system`@0x89e0；0x8a20–0x8a4c 同款 "delete_local_ssid_acl_entry %s" → `run_system`@0x8a4c。**%s 无过滤/无引号**。
- 利用链：无认证 `POST /testfastcgi.cgi` body `wl_unit=1&wl_macmode=allow&wl_maclist0=;PAYLOAD;`（macmode 写入先于 gate 读取，单请求可成）→ run_system → root 任意命令。认证路径：`POST /oeap/config_set_ssid.cgi` 同参数（rehost 已实测 post-auth 全族可达，Cisco/Cisco → 200）。
- 置信度：**确认**（指令级）。上轮 VULN-3 判"高度可疑、注入语义待动态"，本轮 audit-0 完成指令级判定升级；上轮所记 postlogin.cgi topage 注入分支本轮证伪。
- 复现路径：objdump 0x8ab8–0x8c00、0x8724–0x8a4c 核对 0x89e0/0x8a4c sink；动态 POST testfastcgi.cgi + serial log 取证。

## VULN-4: /testfastcgi.cgi 全分发表遍历 = 通用认证绕过原语
- 类型：认证绕过原语 / 严重度：**Critical**（直接导致 VULN-3/5/9/10 的无认证化）
- 涉及组件与证据：fastcgi，handler 0xa05c（分发表第 1 项，flag=9，auth.require 外无认证直达）。[audit-0] major② 反汇编实证（0xa05c–0xa148）：复制 arg1 → 140c4(新map, 请求对象) 解析当前请求参数 → 14450 新map["TEST_FASTCGI"]="1" → **从 0x31014 遍历全分发表（28 项）：flag bit0 置位则跳过（0xa114 `tst r3,#1; bne`），否则 `blx handler(响应, 新map(请求参数+TEST_FASTCGI), 原arg2, entry.arg)`（0xa11c–0xa130）——不做任何 URL 匹配、无认证、无会话校验**。被跳过仅 6 项（testfastcgi 自身/config_set_radio/config_set_dhcp/config_set_firewall flag=9；webauth.json/webauth_result.json flag=0x11），**其余 22 项全部执行**，POST 参数透传给每个被遍历 handler。
- 利用链：无前置 → `POST /testfastcgi.cgi`（任意参数）→ 22 个认证后 handler 逐个执行。已验证影响（audit-0 major② ①–⑤）：① resetlogin.json 管理凭据重置（VULN-9）；② config_set_ssid.cgi wl_maclist 注入 = 无认证 RCE（VULN-3）；③ firmwareupload.cgi 配置包上传+tar 解包（body 经 `_raw_post_data` 键传入，str@0x1c1ac，firmwareupload@0x7f20 读取）（VULN-5）；④ firmwaredownload.cgi 配置/凭据哈希打包下载（VULN-10）；⑤ evt_log_clear.cgi(0x6fa8) 清空 /var/log/messages = **无认证日志擦除（反取证）**。
- 置信度：**确认**。rehost 实测 /testfastcgi.cgi 无认证 200（context.md）。
- 复现路径：objdump `--start-address=0xa05c --stop-address=0xa148`；分发表 .data.rel.ro 0x31014–0x311f4（28 项 ×16B {name_ptr,handler,arg,flag}）逐项核对 flag bit0。
- 备注：/slow-stats/test_dump.cgi（主循环 0xfb64–0xfc30 精确匹配，按 size 参数回显 FCGI stdin body，无认证）为调试遗留回显端点，信息价值低，并入本条不再单列（上轮曾与 testfastcgi 并列为 VULN-4 信息泄露——本轮 testfastcgi 实质大幅升级）。

## VULN-9: resetlogin.json 无认证管理凭据重置（经 testfastcgi）
- 类型：认证状态篡改 / 严重度：**High**
- 涉及组件与证据：fastcgi，handler 0xa930（/oeap/resetlogin.json，flag=8→被 testfastcgi 遍历）。[audit-0] major⑤：0xa948 清全局会话标志 [0x31798]=0（postlogin.cgi@0x7840 置 1 的同一标志）；0xa95c–0xa970 `134e0` String::assign 把 config+0x17800+0x330（存储的管理员用户名，与 authenticate_user.json@0xaac4、auth_redirect.json@0x84d4 读同一字段）赋为 **"admin"**（str@0x1cab5）；随后两个 String="admin" → `bl 0x5c54`：ssl_encrypt("admin","SHA256")@0x5ca0 → sbuild("%s:%s\n")@0x5cf0 → `write_to_file_rename_atomic("/etc/lighttpd-htpasswd.user"@0x1b78a, …)`@0x5d14。应答 {"reset":"1"}。
- 利用链：无认证 `POST /testfastcgi.cgi`（任意参数）→ 遍历调用 resetlogin → 管理凭据状态变为已知默认（用户名 admin/口令 admin）→ OEAP 管理面全权。
- 置信度：**确认（写入动作）**；重置后凭据的实际登录效果需动态验证。**注意（rehost L3-修复 7 交叉证据）**：rehoster 实测 fastcgi 启动即把 /etc/lighttpd-htpasswd.user 重置为 `admin:<sha256-hex>` 格式，而 lighttpd 1.4.54 mod_authn_file htpasswd 后端**不认裸 sha256**（仅明文/crypt/{SHA}/$apr1$）→ 恒 401。这与 audit-0 "不影响 lighttpd Basic 生效"的判断存在张力：resetlogin 的实际效果可能是（a）webauth 层凭据状态重置可登录，或（b）Basic auth 锁死（认证 DoS）。镜像出厂无 htpasswd 文件（本轮 correlator 复核：/etc 下无该文件，运行期生成；lighttpd.conf L85 userfile 为 `__AUTH_BACKEND__` 模板占位，运行期替换）。两种后果均为未授权安全事件，PoC 阶段应实测判定。
- 复现路径：objdump 0xa930–0xa994 与 0x5c54–0x5d14；动态：POST testfastcgi.cgi 后在 guest 内 cat /etc/lighttpd-htpasswd.user、并以 admin/admin 试登录 /oeap/。

## VULN-10: firmwaredownload.cgi 无认证配置/凭据哈希泄露（经 testfastcgi）
- 类型：敏感信息泄露 / 严重度：**High**
- 涉及组件与证据：fastcgi（分发表 /oeap/firmwaredownload.cgi，flag bit0 清零→被 testfastcgi 遍历）。[audit-0] major②④：命令均固定串 `cp /storage/base_capwap_cfg_info /tmp/download_config;cp /storage/config.* …;tar -cvf …`（@0x1be58；sink 0x6d34/0x6e34 mkdir/rm + 0x6d84 cp+tar）→ /storage/config.oeap **含管理员凭据哈希**被打包供下载。文件名固定（uploaded/download_config 路径固定），无注入。
- 利用链：无认证 `POST /testfastcgi.cgi` → 遍历调用 firmwaredownload → 下载配置包 → 离线破解凭据哈希 → 登录管理面（或与 VULN-3 认证路径组合）。
- 置信度：**确认（sink 固定串反汇编级）**；下载体内容/哈希格式需 PoC 确认。
- 复现路径：objdump 0x6d34–0x6d90 核对固定命令串；动态 POST testfastcgi.cgi 观察应答体。

## VULN-5: firmwareupload.cgi tar 解包路径穿越任意文件写（经 testfastcgi 无认证）
- 类型：路径穿越 → 任意文件写 / 严重度：**High**（与持久化机制组合可 RCE）
- 涉及组件与证据：fastcgi，firmwareupload@0x7f20。[audit-1] chain：multipart body 解析（find_left '\n'→split→operator[]，均有 __assert/边界检查，**无内存破坏**）→ 0x5ae0 写 /tmp/upload_config/uploaded_config_file.tar → 0x8068 `run_system("cd /tmp/upload_config;tar -xvf /tmp/upload_config/uploaded_config_file.tar"@0x1c1d7)`（固定串无注入）→ **GNU tar `../` 成员 = 路径穿越任意文件写**。随后 MerakiConfig 读 /tmp/upload_config/config.oeap 并 save /storage/config.oeap、send_ipc_to_capwap(25)。[audit-0] major②③：无认证经 `POST /testfastcgi.cgi`（body 为伪造 tar，经 `_raw_post_data` 键传入）。
- 利用链（两条升级路径）：
  1. **持久化 RCE**：tar 成员 `../../www/x.sh`（任意写）→ lighttpd cgi.assign(".sh"=>"/bin/sh") → `GET /x.sh` → root shell（全程无认证）。
  2. **时间转移注入**（[audit-0] chain 配置上传→ACL 注入）：解包出的 config.oeap 被读入并 save 到 /storage/config.oeap → 其中 `wl_maclist%d_%d` 键在**下一次** config_set_ssid ACL 同步（0x8724 第二循环）以 `delete_local_ssid_acl_entry %s` 进 `run_system`@0x8a4c——投毒配置延迟触发注入。
- 置信度：**高度可疑→确认**（代码路径反汇编级确认；tar 穿越语义依赖 GNU tar 行为与目标写权限，需 PoC 验证；rehost post-auth 全族已可达）。
- 复现路径：objdump 0x7f20–0x8130 核对 0x5ae0/0x8068；动态构造含 `../` 成员的 tar POST 到 testfastcgi.cgi，检查落盘路径。
- 附带（audit-1 minor）：畸形 body（如仅 1 个 '\n' 使 split <3 元素）→ Vector::operator[] __assert abort()——认证后 crash DoS（fastcgi 进程模型影响面待动态）。
- 上轮 VULN-5 为同一发现（post-auth），本轮经 testfastcgi 升级为 pre-auth。

## VULN-12: stilecpd 0.0.0.0:4040 零认证 JSON-RPC（21 命令全部未授权）
- 类型：缺失认证 → 未授权设备操控 / 严重度：**High**
- 涉及组件与证据：$ROOTFS/usr/bin/stilecpd（nbar.service：`ExecStart=/usr/bin/stilecpd --mode km --activate -s 0.0.0.0:4040`，明文 TCP，无 User= → root）。[audit-3] major① 全链地址证据：RPCServer::do_work@0x6af3c（accept→new RPCWorker→Scheduler::add，无凭据检查）→ RPCWorker::check_request@0x6bcd4（仅协议状态检查 [req+0x24] 状态机）→ Server::handle_rpc_request@0x4bcf8 → ReqParser::parse@0x45e9c（Json::Reader::parse@0x88e28）→ parse_single_request@0x45754（仅校验 jsonrpc=="2.0" 与 method 存在）→ RpcCommandsTable::lookup → ParsedObject::execute@0x43c78 → RpcCommand::run@0x440a0（vtable+8）。**符号表全文无任何 auth/token/password/session 函数**。21 命令经 RpcCmdsCore::RpcCmdsCore@0x6df18 注册逐一经 literal pool 实证：ping/status/cmds/events/attach/detach/activate/deactivate/load/unload/reload/mt/collect/push_pcap/ppack/pmap/coffee/shutdown/log/sdavc/pd。
- 未授权影响清单：**shutdown**@0x6fe3c（单包远程 DoS，Restart=always+RestartSec=5 自动拉起但可循环打挂）；**log**（未授权操纵日志级别 = 反取证静默）；**sdavc** handle_enable_https@0x6dcc4（未授权改设备 SD-AVC 外联配置）；activate/deactivate/attach/detach（引擎状态操控 DoS）。
- **未授权 DoS ×2**（[audit-3] major③，同一根因并入本条）：① RpcTransportTCP::get_max_msg_size@0x4b228 = `mvn r0,#0`（-1 无限制）+ recv_msg_int@0x49eb0 16KB 循环 recv + `find("\n")`——无换行数据无限累积进 [this+16] std::string → root 进程 OOM；② 请求路径走旧版 vendored Json::Reader（readValue@0x882d0 ↔ readObject@0x87e24/readArray@0x88838 互递归，无深度限制）→ 数十万层 `[[[…` 嵌套 JSON 栈溢出崩溃。两者叠加报文大小无上限。
- 利用链：无前置（4040 网络可达即零认证）→ 单个 TCP 连接 JSON-RPC → 上述任意效果。
- 置信度：**确认**（反汇编级；21 命令名逐一实证）。
- 复现路径：objdump 0x6af3c/0x6bcd4/0x4bcf8/0x45e9c/0x43c78 链路；动态：`echo '{"jsonrpc":"2.0","method":"shutdown","id":1}' | nc <ip> 4040`。**注意**：rehost 最小 boot 未启动 nbar.service（4040 关闭），动态验证需先在 guest 内拉起 nbar.service（context.md 能力声明）。
- 横向提示（audit-1 minor）：fastcgi 的 Json 解析器实体在 **libmeraki.so**（未审计），无认证端点（webauth.json 等）POST body 直入——stilecpd 同源旧版 Json::Reader 已证栈耗尽，libmeraki.so 为同类风险的未审计面（见待办）。

## VULN-13: stilecpd `unload`+`load` → dlopen 任意 .so = root RCE（与 tftpd :69 上传成链）
- 类型：任意代码装载 → RCE / 严重度：**Critical**
- 涉及组件与证据：stilecpd。[audit-3] major②：RpcCmdLoad::_run@0x6f36c（parse_path("path")：validate_path@0x44420 = stat+S_ISDIR，**仅验证目录存在、无白名单**；req["mt"]==true → force）→ Engine::load_engine@0x60504（[this+0x74] state>0 时 throw"已加载"，需先 unload）→ EngineKM::load_engine_int@0x66c5c → load_kms@0x669fc（**内核模块路径固定 "../modules/ntdp.ko"@0x9e3dc，与 RPC path 无关——insmod 变体不成立，RCE 落在 dlopen**）+ **load_so@0x66860：`path.append("/libntcp_k.so",13)`（str@0x9e36c）→ `dlopen(full, RTLD_NOW=2)`@0x668d8** → 攻击者 .so 构造函数即 root 执行（nbar.service 无 User=）。前置：① 先 `unload`（RpcCmdUnload::_run@0x6f248 → Engine::unload_engine@0x602b4 → unload_engine_int@0x66518：dlclose+delete_module，复位 state/句柄）；② path 指向任一已存在目录（/tmp、/tftpboot 均满足——validate_path 仅 stat 目录）。
- 利用链（[audit-3] chain）：tftpd-hpa :69 `-C /tftpboot` 未授权上传恶意 libntcp_k.so（见 VULN-20）→ stilecpd :4040 未授权 `unload` + `load {"path":"/tftpboot"}` → `dlopen("/tftpboot/libntcp_k.so")` → **root RCE**。前置仅 4040 与 69 网络可达（均无认证）。
- 置信度：**高（静态确认）**——dlopen 数据流反汇编级实证；组合链依赖 tftpd 上传（配置事实确认，inventory L69）。与 fastcgi `.sh→/bin/sh` 写链（VULN-5 升级路径 1）互为替代出口，且互相独立（不同服务）。
- 复现路径：objdump 0x6f36c/0x66860–0x668d8/0x44420；动态：tftp put libntcp_k.so → nc 4040 发 unload/load JSON → 观察 dlopen（合法引擎库 /usr/lib/libntcp_k.so 与内核模块 /lib/modules/ntdp.ko 均在 rootfs 实证存在，[audit-3] chain 条目）。

---

# 第二梯队：疑似链 / 依赖缺环

## VULN-11: capwapd FLEX_SLAVE_DOWNLOAD 命令注入（内部 WCP TLV 0xf4 → popen；远程可达性缺环在 wcpd）
- 类型：OS 命令注入 → RCE / 严重度：**High**（若缺环闭合）
- 涉及组件与证据：$ROOTFS/opt/cisco/capwapd/8.10.130.0/bin/capwapd。[audit-2] major 反汇编级全链：① 入口 TLV 0xf4 AP_MASTER_SLAVE_CONFIG_PAYLOAD 解码器 0xf6abc（内部 WCP payload 注册表 0x1d847c 项 0x1dc03c）：0xf6f50–0xf6f84 `memset(struct+0x44c9,0,255)` 后 `strncpy(struct+0x44c9, src, 255)`@0xf6f80（len=msg[6]，**≤255 字节镜像名、无元字符过滤**），并置状态 [struct+0x44ac]=20；② 触发 ImageActivateTask（0x613a0/0x61424 `cmp r3,#20`）→ 0x61474 调 0x60f80(r4+0x3d03, retry, server_str, struct+0x44c9)；③ sink 0x60f80：0x61024–0x6103c `snprintf(sp+328,256,"/etc/capwap-upgrade.sh -r %d -s %s -n %s FLEX_SLAVE_DOWNLOAD",…)` → **`popen(sp+328,"r")`@0x61074**（备分支经全局标志拼 "/usr/bin/cli_scripts/image_download.sh -l %s -m 2 -x" 亦 popen）；server 参数安全（0x5d80c：IPv4 "%u.%u.%u.%u" / IPv6 inet_ntop）。④ 脚本侧无过滤（本轮 correlator 复核原文）：/etc/capwap-upgrade.sh:93 `flex_slave_ap_download ${tftp_download_retry} ${tftp_server_ip} ${tftp_image_name}`（无引号）→ capwap-upgrade-func.sh:1291 `/usr/bin/curl … tftp://${tftp_server_ip}/${tftp_image_name} -o $TMP_AP_FILE`（**变量裸拼**，`;`/空格/反引号均注入）。
- 利用链：控制内部 WCP TLV 0xf4 内容（经 Unix socket /tmp/capwap_wcp_msg ← **wcpd**）→ strncpy 镜像名 → ImageActivateTask → popen → capwap-upgrade.sh → curl 裸拼 → 任意命令（capwapd 特权进程；第二调用方 ImageEwlcDownloadTask 0x61e60 同构）。
- **缺环（决定远程可达性）**：wcpd 如何产生 TLV 0xf4 未审计。[audit-2] 转 correlator：若 ME 主从架构中 master AP 经 CAPWAP 下发的配置由本机 wcpd 转成 TLV 0xf4，则**远程恶意 master 可达**。**correlator 拼装的同向线索**：[audit-0] minor（H6 证伪条）记录 config_set_firewall.cgi(0x12fe0) 的防火墙规则字符串 → `send_ipc_to_capwap` → capwapd/wcpd 侧消费（工单外）——fastcgi 配置面经 send_ipc_to_capwap 与 TLV 0xf4 产生路径同向；若该管道通向 TLV 0xf4 构造，则 fastcgi 配置（防火墙规则等字符串）→ capwapd popen 成跨 binary 链。**wire 侧直接路径已排除**：[audit-2] chain 验证 wire Discovery 解码器（AC_DESCRIPTOR dec_cb 0xf2a2c 定长 20 检查 / IMAGE_FILENAME 0xf3788 魔数+仅写 4 字节 / AC_NAME 0xf2b44 cap 31 / 0xf3880 cap 255）均界内，未发现 wire 字段直接字符串化进 system()。
- 置信度：**sink 链确认（反汇编实证）；远程可达性推测（依赖 wcpd）**。
- 复现路径：objdump 0xf6abc–0xf6f84 / 0x60f80–0x61074 / 0x61424–0x61474；sed -n '93p' /etc/capwap-upgrade.sh；sed -n '1291p' /etc/capwap-upgrade-func.sh。待办：wcpd 产生 TLV 0xf4 的路径审计（见覆盖面说明）。

## VULN-17: capwapd 版本串 → system() 三处无过滤（32 字节上限）
- 类型：OS 命令注入 / 严重度：**Medium**（与 VULN-11 同前置缺环）
- 涉及组件与证据：[audit-2] minor：版本缓冲写入者 0x140a50–0x140a5c `strncpy_s([global+0x138c], src, 32)`（TLV 处理器 0x140934 家族，日志 'EWLC image master len=%u IP=%s'@0x140920 / 'Invalid controller eWLC image version [%s]'@0x140a7c）。未净化消费：① ewlcImageTimerHandler 0x60888–0x60890 `system("echo 'ws_management_version: %s' > /part2/mewlc_info.ver")`（fmt@0x17af12）；② ImageWriteTask 0x61ca4–0x61cbc `system("/etc/capwap-upgrade.sh -m MASTER -v %s PREDOWNLOAD")`（前置 0x618ec 预下载状态==2）；③ 0x5ff0c–0x5ff14 `system("/etc/capwap-upgrade.sh COMPARE_MEWLC_VERSION %s")`。
- 利用链：TLV 配置面写入版本串 → system %s → 32 字节内 `;cmd` 类短 payload。
- 置信度：**sink 确认；可达性同 VULN-11 缺环（TLV 配置面/wcpd）**。
- 复现路径：objdump 0x140934–0x140a7c / 0x60888 / 0x61ca4 / 0x5ff0c。

## VULN-18: capwapd DTLS 证书校验宽松
- 类型：传输层认证弱化 / 严重度：**Medium**
- 涉及组件与证据：[audit-2] minor：dtls_cert_verify_callback@0x68244：X509 err 10（证书过期）+ MIC 检查（0x681d8）通过 → 'Allowing expired MIC certificate'（str@0x6828c）→ 返回 1 接受；另有全局策略位 [state+0x46f0]（0x49c00–0x49c08 从配置 +0x4e0 拷贝）==1 时**无条件接受**。Discovery 族消息按 RFC 5415 恒明文，ME 主选举入口 wtpProcessPrimaryDiscoveryResponse@0x45874 → 0x3fc80 → 0x45aec 链运行于明文。
- 利用链：相邻网络位置 → 呈现过期 MIC 证书（或触发策略位）→ 伪造 WLC/中间人面扩大。明文 Join 是否被接受未完成验证（hypothesis 5 部分覆盖）。
- 置信度：**代码确认；运行态策略位取值未验证**。
- 复现路径：objdump 0x68244–0x68290 / 0x49c00。

## VULN-6: wcpd/click 侧未审计消费面（redirecturl 二阶注入 + 异步自授权）——延续上轮，未闭合
- 类型：潜在二阶注入/授权绕过 / 严重度：**High（若闭合）**
- 涉及组件与证据：本轮新增（[audit-0] chain）：redirect.cgi(0x67ec，无认证，:1233/:1234 强制门户将任意原始 URL 拼进 redirecturl) → redirecturl + REMOTE_ADDR → 0x68c0 `click_read_param(结果, "/click/webauth_helper/query_redirect_url"@0x1bca5, sbuild("%s",redirecturl))`——**redirecturl 经 unix socket 进 click 元素**；fastcgi 侧无 shell sink（开放重定向为强制门户设计行为）。**消费端在 wcpd/click 侧，未审计**——若该元素处理拼 shell 则二阶注入。上轮 VULN-6（本轮未再审计）：0x10ab4 异步授权模型（reqid 轮询 + wcp socket 写入方权限）未闭合。
- 端点模型修正（[audit-0] chain，纠正 surface.md §0）：fastcgi 分发表 28 项中**无任何 /click/ URL**——`/click/webauth_helper/query_redirect_url`、`/click/client_ip_table/set_vap_nat` 为 clickfs 元素路径（字符串仅被 handler 内部引用），**不是可请求端点**；set_vap_nat 逻辑挂载在 /oeap/config_set_dhcp.cgi 且参数经 IPAddress/纯整数处理，无注入。
- 利用链（条件）：无认证 redirect.cgi → click webauth_helper 元素 → wcpd/click 侧消费（缺环）→ 若拼 shell 则 RCE。
- 置信度：**推测**（fastcgi 侧数据流已证，消费端语义缺环）。
- 复现路径：objdump 0x67ec–0x6920 核对 click_read_param 调用；待办：wcpd/click 工单。

## VULN-15: stilecpd push_pcap 任意文件读取 oracle + ppack 任意已存在文件喂引擎
- 类型：信息泄露 oracle / 潜在内存破坏入口 / 严重度：**Medium**
- 涉及组件与证据：[audit-3] minor×2：① RpcCmdPushPCAP::_run@0x722e4：filename 走 parse_string（**非 parse_file——无 stat/白名单校验**）→ push_filename@0x71e8c → Engine::push_pcap@0x61384 → CCapReaderFactory::CreateReader@0x8ffd8 → `fopen64(原始 RPC 路径)`——文件按 pcap 格式解析，响应/错误构成**存在性 oracle**（可探测 /etc/passwd、shadow 等）；内容级回读（事件/统计通道是否带回文件派生数据）需运行期验证。② RpcCmdPPACK::_run@0x6e9e0：cmd∈{load,unload}，parse_file → validate_file@0x44390（stat+S_ISREG 仅存在性）→ Engine::load_ppack@0x608d4——解析器在 /usr/lib/libntcp_k.so（本 binary 外），**畸形 ppack 是否致引擎内存破坏未验证**。
- 利用链：4040 可达零认证（VULN-12 前置）→ push_pcap 探测文件存在性 / ppack 喂畸形文件给引擎解析器。
- 置信度：**高度可疑**（oracle 静态确认；内容回读/内存破坏待动态）。
- 复现路径：objdump 0x722e4/0x71e8c/0x61384/0x8ffd8；0x6e9e0/0x44390/0x608d4。

## VULN-16: stilecpd collect set_exporter / sdavc 任意外联配置 + file 模式任意路径写
- 类型：未授权外联（exfil/beacon）/ 任意路径写 / 严重度：**Medium**
- 涉及组件与证据：[audit-3] minor：handle_collect_set_exporter@0x6d650：socket{server,port,path}，type∈{http,https,http-flat,https-flat,file,none}（str@0x9f21c–0x9f244）→ ExporterConfig::set_server@0x743d4 / set_mode_http_flat@0x743fc / set_mode_https_flat@0x7442c / set_mode_file@0x7445c → Engine::collectors_set_exporter@0x7532c。http(s) 族 = 未授权将 NBAR 采集数据导向任意 server:port（设备侧外联/数据外发原语，非经典 SSRF）；file 模式 = 采集数据写任意路径文件（写语义在引擎 .so 内未完全走读）。sdavc handle_enable_https@0x6dcc4（socket+agent_id/client_id/secret_id → SDAVCConfig::set_mode_https@0x74370）同类。
- 利用链：4040 可达零认证 → collect set_exporter 指向攻击者 server:port → 设备定期外联（beacon/数据外发）或写任意路径。
- 置信度：**高度可疑**（配置写入流反汇编确认；外联实际发起/写语义在 libntcp_k.so 未走读）。
- 复现路径：objdump 0x6d650–0x6dcc4 / 0x743d4–0x7445c。

---

# 第三梯队：孤立发现与配置级风险

## VULN-14: config_set_ssid.cgi `wl_unit` sprintf 栈溢出（10 字节受限，远程 crash/DoS）
- 类型：栈溢出（受限）/ 严重度：**Medium（DoS）**
- 涉及组件与证据：fastcgi，函数 0x8724（与 VULN-3 同函数、同入口）。[audit-1] major：wl_unit(int 无校验)@0x8b24 `bl 78d0(request,"wl_unit")` → 存 config+0x17d44 → ∉{0,1} 走 0x90f0 → gate 0x96b8–0x96c8（config+0x17c00+0x164=="allow"）→ 0x96e8 `bl 8724(request, wl_unit)`（全 binary 唯一调用者）→ 0x8724 内 @0x8844 读 /storage/config.oeap（read_possibly_nonexistent_file → meraki_config_string_to_map）→ 循环 i=0..15：@0x8868 memset(sp+56,0,15) + @0x887c `sprintf(sp+56,"wl_maclist%d_%d"@0x1c2f7, i, wl_unit)`——最长 "wl_maclist15_-2147483648"=25B **溢出 10 字节进 sp+72 的 HashMap 对象** → @0x8888 `bl 6788(被破坏的 HashMap, sp+56)` 解引用被数字字节覆盖的首字（如 2147483647 → 0x33383437 wild pointer）→ SIGSEGV。
- 利用链：/oeap/ Basic auth 后（或无认证经 testfastcgi，flag=8 被遍历）→ ① POST config_set_ssid.cgi `wl_unit=1&wl_macmode=allow`（置 gate 字段）→ ② POST `wl_unit=2147483647` → 崩溃。前置：/storage/config.oeap 存在且非空（已配置 AP 正常满足）。
- 限制：溢出字节仅数字/'-'/NUL；0x8724 帧为 push{r4-r11,lr}+sub#108，缓冲最大写至 sp+81 < 保存寄存器区 sp+108——**不可直达返回地址**，定级 crash/DoS。
- 置信度：**确认（crash）**；超 DoS 利用性低。
- 复现路径：objdump `--start-address=0x8724 --stop-address=0x88a0` 核对 0x887c/0x8888。**勘误上轮**：上轮证伪记录"0x887c 1 字节 NUL 溢出进栈 padding 不可利用"——本轮 audit-1 修正为 10 字节可控溢出进相邻 HashMap 对象（可达崩溃）。

## VULN-19: sshd `PermitEmptyPasswords yes` + 特权本地账户（动态待验）
- 类型：弱认证配置 / 严重度：**Medium（若运行期口令为空）**
- 涉及组件与证据：[unpacker] minor：sshd_config.me `PermitEmptyPasswords yes`、`DenyUsers root`；镜像无 shadow 文件（运行期生成）；passwd 中 support(uid=1)/rsyncuser(uid=5,**gid=0**) 带 /bin/ash shell。AuthorizedKeysFile /storage/ssh.me/.ssh/authorized_keys；etc/dropbear/authorized_keys 存在但为空（无预置密钥后门）。
- 利用链：:22 可达 + 运行期口令为空 → 无口令 SSH → 本地特权（rsyncuser gid=0）。
- 置信度：**推测**（配置事实确认；运行期口令状态需动态——rehost 最小 boot sshd 未运行，需拉起后验证）。
- 复现路径：grep sshd_config.me；动态：起 sshd 后 `ssh rsyncuser@<ip>`（空口令尝试）。

## VULN-20: tftpd-hpa :69 未授权任意文件上传
- 类型：未授权文件创建 / 严重度：**Medium（独立）/ Critical（作为 VULN-13 前置）**
- 涉及组件与证据：inventory L69：tftpd-hpa.service `-L -M 8 -C /tftpboot`——**-C 允许客户端创建新文件（上传面）**，UDP :69 无认证。
- 利用链：无前置 → tftp put 任意文件至 /tftpboot → ① 恶意 libntcp_k.so 供 stilecpd dlopen（VULN-13）；② surface.md §3 提示 capwapd 从 /tftpboot/%s-pre%d...tar 取文件——投毒固件包/脚本的潜在链素材。
- 置信度：**确认（配置事实）**；上传行为待动态（rehost 最小 boot tftpd 未运行）。
- 复现路径：grep tftpd-hpa.service；动态：`tftp <ip> -c put libntcp_k.so`。

## VULN-21: redis 硬编码口令（loopback）
- 类型：硬编码凭据 / 严重度：**Low（仅 loopback，作为借力素材）**
- 涉及组件与证据：[unpacker] minor：etc/redis.conf 硬编码密码 `w!r3L3sS@CSCO`，bind 127.0.0.1，**protected-mode no**。
- 利用链：任意本地执行/SSRF 原语（loopback 可达）→ 已知口令直连 redis → 写 RDB/模块 = LPE 借力（surface.md §3：redirect.cgi/testfastcgi.cgi 若可发起请求则可借力）。
- 置信度：**确认（配置事实）**；无独立远程可达性。
- 复现路径：grep -A2 requirepass etc/redis.conf。

## VULN-22: memcached 1.5.7 绑定 0.0.0.0:11111（SASL）
- 类型：过时暴露服务 / 严重度：**Medium（待 CVE 核对）**
- 涉及组件与证据：inventory L70：memcached.service **0.0.0.0:11111 与 [::]:11111**，SASL(-S)，DCDS 数据服务（etc/systemd/memcached.env）。本轮 correlator 补钉版本（strings 实证）：**memcached 1.5.7**（2018 年代版本）。planner 移交"版本已知问题核对 CVE"——本轮按角色约束未做外部 CVE 检索，仅钉住版本供后续核对。
- 利用链：11111 可达 → SASL 认证面 + 1.5.7 已知漏洞面（待核对）→ 待定。
- 置信度：**确认（版本与绑定事实）**；漏洞面待核。
- 复现路径：strings usr/bin/memcached | grep 'memcached 1'；动态：nmap -sV -p 11111。

---

# 跨组件组合链总览

| 链 | 路径 | 状态 |
|---|---|---|
| **W1（pre-auth RCE ×3，互为独立）** | A：`GET /set_universal_ap_reg_domain.shtml?location=;PAYLOAD;`（VULN-2）｜B：`POST /testfastcgi.cgi` body `wl_unit=1&wl_macmode=allow&wl_maclist0=;PAYLOAD;`（VULN-4→VULN-3）｜C：`GET /webauth/webauth.json?clientid=;PAYLOAD;`（VULN-1） | **确认**，单请求、无认证、root（[audit-0] chain 汇总链） |
| **W2（凭据重置→全权）** | VULN-4 → resetlogin（VULN-9）→ 已知默认凭据 → /oeap/+/configure/ 认证后全族 | 确认（写入动作）；登录效果待 PoC（sha256/lighttpd 张力，见 VULN-9） |
| **W3（任意写→持久化 RCE）** | VULN-4 → firmwareupload tar 穿越（VULN-5）→ 写 /www/x.sh → cgi.assign(".sh"=>"/bin/sh") → GET /x.sh | 高度可疑（tar 语义需 PoC）；**全程无认证** |
| **W4（配置投毒→时间转移注入）** | VULN-4 → firmwareupload → 解包 config.oeap → save /storage/config.oeap → 下次 config_set_ssid 同步 0x8724 第二循环 → `delete_local_ssid_acl_entry %s` → run_system@0x8a4c | 高度可疑（第二循环数据流已实证） |
| **S1（服务面 root RCE）** | tftpd :69 上传（VULN-20）→ stilecpd :4040 unload+load（VULN-12→VULN-13）→ dlopen → root | 确认（静态）；需 4040+69 可达（默认全启动，rehost 需手动拉起） |
| **C1（跨 binary，缺环）** | fastcgi 配置字符串（防火墙规则等）→ send_ipc_to_capwap → wcpd → 内部 TLV 0xf4 → capwapd strncpy → popen（VULN-11） | **待验证**——若 wcpd 转换路径证实则闭合（下一审计工单位置：wcpd） |
| **R1（缺环）** | redirect.cgi redirecturl → click webauth_helper → wcpd/click 消费（VULN-6） | 待验证（同 C1，wcpd/click 工单） |
| **反取证组合** | VULN-4 → evt_log_clear.cgi 清日志 + stilecpd `log` 命令调级静默（VULN-12）——两服务均有无认证日志擦除/静默面 | 确认 |

---

# 被丢弃/证伪项（本轮及上轮合并，供下游免复查）

- **capwapd 分片重组溢出证伪**（[audit-2]）：重组函数 0x40f54——首分片 0x69198 确保 16000B 缓冲（失败即拒）、每分片 0x41404 `cmp r8,#16000; bhi` 上限检查后才 memcpy@0x4141c、偏移一致性 0x413e0、分片数上限（0x41780）。
- **capwapd sscanf 证伪**（[audit-2]）：25 处仅 0x78308 一处 %s（错误打印路径 'Invalid PC value'，非网络解析），其余全数值格式。
- **tftp://%s/mewlc.bin 系列安全**（[audit-2]）：0x61dfc/0x61e20 的 %s 为 inet_ntop 输出。
- **fastcgi 22 处 run_system/run_system_capture 全表处置**（[audit-0] minor）：注入仅 4 处（0x89e0/0x8a4c=wl_maclist→VULN-3；0x10b98=clientid→VULN-1）+ reg_domain system 2 处（0x9ce8/0x9d24=location→VULN-2）；其余 16 处固定串/纯整数安全；execl/popen 包装 0x179a4/0x1900c/0x19048 无调用者（死代码）。
- **fastcgi 内存破坏全表处置**（[audit-1]）：strcpy 仅 1 处 strdup 模式安全；strncpy 4 处定长安全；snprintf 3 处定长；memcpy 8 处定长/界内；read 循环界内；sscanf/gets/strcat 无 PLT 调用。firmwareupload multipart 解析无内存破坏（VULN-5 的穿越是唯一缺陷）。残留：内嵌 vformat 宽度/精度转换经 ~104B 栈缓冲（0x19c04 帧）——**现版本全部格式串无宽度/精度 %s，不可达**，属潜伏缺陷（新增带宽度格式串即触发）。
- **config_set_wan/dhcp/firewall.cgi 注入证伪**（[audit-0] minor）：wan 无 shell sink；dhcp sink 纯整数；firewall 参数→MerakiConfig 字段→send_ipc_to_capwap（消费面见链 C1）。
- **dynrest 证伪（fastcgi 侧）**（[audit-0] minor）：fastcgi 与 rootfs 全 grep 均无 dynrest 消费者——倾向 ME VM 侧（nginx :445/:448 反代）消费，未定位（覆盖面缺口）。
- **stilecpd RpcZip 压缩面死代码 / str_to_level 纯 compare 链 / Coffee 无 system**（[audit-3] chain）：H7/H8 证伪。
- **login 枚举 oracle（上轮 VULN-8）**：上轮 finalizer 执行级证伪 + 本轮 rehost 复测 + audit-0 复核，撤销。
- **/configure/ 前缀归一化绕过**（audit-0 minor）：属 lighttpd 1.4.54 mod_auth 层行为，静态不可判定，**转 PoC 阶段动态验证**（未证实也未证伪，不计入候选）。

---

# 覆盖面说明与待办

## 本轮已覆盖
- fastcgi（fastcgi-cmdi-authbypass + fastcgi-memcorrupt 两工单）：命令注入、认证绕过、内存破坏三角度全量；22 处 run_system 调用点全表处置；28 项分发表逐项定性。
- capwapd（capwapd-cmdi-memcorrupt）：三套 payload 注册表（wire 消息类型/wire 消息元素/内部 WCP TLV）、FLEX 升级链、版本串、DTLS、分片重组、sscanf 全表、升级脚本。
- stilecpd（stilecpd-authbypass-memcorrupt）：零认证面、21 命令、load/dlopen、DoS×2、文件 oracle、exporter 外联、证伪清单。
- 配置级：lighttpd 认证边界与 cgi.assign（本轮 correlator 复核原文）、tftpd/sshd/redis/memcached（unpacker+correlator 补钉 memcached 版本）。

## 未覆盖（按价值排序的待办，非本轮 correlator 职责）
1. **wcpd 产生内部 TLV 0xf4 的路径**（VULN-11/17 远程可达性 + 链 C1 闭合的关键缺环；含 fastcgi send_ipc_to_capwap → wcpd 的配置字符串管道）——下一审计工单首选。
2. **libmeraki.so Json 解析器**（audit-1 建议）：无认证端点（webauth.json 等）POST body 直入；stilecpd 同源旧版 Json::Reader 已证栈耗尽（VULN-12 ②）。
3. **ap1g1 IOS httpd**（planner 本轮裁剪；rehoster 勘误实为 **mips-be** 非 ppc-be，补审成本降低）：html/level/15 表单 image_upgrade_tftp_server_address/image_upgrade_image_path 等入口与 sink；unicorn 契约就绪（agents/rehoster/unicorn_harness_fixed.py，基址 0x80080000，kseg0 物理别名已处理）。
4. **wcpd/click webauth_helper 元素消费端**（VULN-6/链 R1）。
5. **capwapd 残留**（audit-2 未覆盖项）：0x44664 wire TLV 循环对逐元素长度未循环内复核（元素 len 递减可为负→**潜在越界读**，未见越界写）；66 处 strcpy/291 处 memcpy 全表分类；mwar_addr_list/lrad 走读。
6. **dynrest 消费方定位**（倾向 ME VM 侧，经 nginx :445/:448 反代）。
7. **memcached 1.5.7 CVE 核对**（版本已钉住）。
8. 动态验证项（PoC 阶段）：/configure/ 前缀绕过、fastcgi crash 影响面（进程模型）、resetlogin 后登录效果、sshd 运行期口令状态、tftpd/stilecpd（rehost 需拉起 nbar.service/tftpd）。

## rehost 环境对验证的约束（context.md 摘要）
- ap1g4 仿真实例运行中（192.168.100.1）：:80/:443/:1233/:1234 开放——**VULN-1/2/3/4/5/9/10 全部可动态验证**（pre-auth 端点实测 200；post-auth /oeap/* 以 Cisco/Cisco 可达）。
- :22/:4040/:69/:11111/:64999 在最小 boot 下未监听——**VULN-12/13/19/20/22 需先在 guest 内拉起对应服务**。
- 命令注入取证以 serial log /tmp/ser34.log 为准（wcp_write stub 逐参数回显 + /bin/sh 报错可见；计时 PoC 不可靠）。
- VULN-11/17/18（capwapd）当前不可动态验证（capwapd 未运行），静态地址已钉住。

---

# 拼装结论

本轮最高价值产出为**四条互相独立、单请求、无认证的 root RCE 入口**：VULN-1（webauth.json clientid）、VULN-2（set_universal location）、VULN-3（testfastcgi→wl_maclist）、VULN-13（stilecpd dlopen，需 :4040+:69）——前三者仅需 80/443/1233/1234 任一端口可达。VULN-4（testfastcgi 全表遍历）是通用认证绕过原语，把 resetlogin/firmwareupload/firmwaredownload/evt_log_clear 一并无认证化，并衍生 W2/W3/W4 三条组合链。根因层面：lighttpd auth.require 仅护 /configure/+/oeap/ 两个前缀（VULN-1/2/4 的共同前置）、fastcgi 全部 sink 无元字符过滤（VULN-1/2/3）、stilecpd 完全无认证（VULN-12/13/15/16）。capwapd 侧 VULN-11 sink 已实证但远程可达性卡在 wcpd 缺环（链 C1），是下一轮审计投入产出比最高的位置。上轮 8 条候选中 6 条经本轮深审升级或复确认、2 条撤销；无空手领域——三梯队 20 条均有可溯源证据。
