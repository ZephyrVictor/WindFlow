# iot_hunter 知识库索引（agent 开工必读）

> 跨 run 沉淀的通用经验，按 **厂商/固件家族 × 漏洞类型 × rehost 工艺** 三维组织。
> 人工从 run memory「晋升候选」审订合入；只收跨设备复用经验，单 run 细节留在 run memory。

## 条目字段规范（写新条目必须五要素齐全）

1. **适用特征**——新目标怎么命中本条目（可判定的特征，不是叙述）
2. **症状**——命中后遇到的典型现象/报错
3. **解法**——已验证的操作路径（含关键命令/地址/参数）
4. **死路**——已证伪/已排除的路线及原因（负结果闭环，防后人重走）
5. **溯源**——验证过本条目的 run id

## 命中表（按目标特征取条目）

| 目标/场景特征 | 应读条目 |
|---|---|
| Cisco Aironet **Mobility Express / Meraki 架构**（识别：ramfs_cisco、bootsh、merakiclick.ko、wcp 工具族、lighttpd+fastcgi） | `vendors/cisco-meraki-me.md` |
| Cisco Catalyst **经典 IOS 单体镜像**（MZIP：tar→bin→zip 层；httpd/SNMP 编译进同一镜像） | `vendors/cisco-ios-classic.md` |
| rehost 需要加载**厂商内核模块**（.ko），或服务起不来报 click/内核符号缺失 | `rehost/vermagic-engineering.md` + `vendors/cisco-meraki-me.md` |
| 验证**命令注入**类（system()/popen()/exec.Command("sh","-c") sink） | `vulns/command-injection.md` |
| 验证**栈溢出**类（saved LR/PC 控制主张） | `vulns/stack-overflow.md` |
| 验证**认证绕过/未授权面**（预认证可达主张） | `vulns/auth-bypass.md` |
| rehost 后**认证全 401**（环境异常 vs 漏洞相关分辨） | `vulns/auth-bypass.md` §环境异常排查 |

## 维护规则

- agent 本轮产生可跨设备复用的新经验 → 按 memory 纪律追加 run memory「晋升候选」节，由人工审订后合入对应分维文件
- 条目被新 run 证伪/细化 → 更新该条目并追加溯源，**不删除死路记录**
- 新增厂商/漏洞类型 → 新文件 + 本表加行
