# flow-map — 跨模块数据流假设源(attack-ledger 源③底料)

流程审计 = 沿**跨模块数据流**逐握手点问「谁被授权、失败时去哪、跨域时谁
校验」。单边看每个模块都对,接起来的缝隙只在这里可见。poc-planner 轮首
把流程清单登记进 workdir/attack-ledger.md 的 UNTRIED 行。

## 流程清单(每条 = 一行;检查点即假设粒度)

| # | 流程 | 关键模块 | 资产/检查什么 |
|---|---|---|---|
| F1 | boot chain | rom_ctrl × ibex 取指门 ×(sw 边界) | 校验完成信号被谁消费/失败路径/取指窗口 |
| F2 | lifecycle 转移 | lc_ctrl × otp_ctrl(token/secret 分发)× pinmux/dft | 转移授权、token 窗口语义、失败态去向 |
| F3 | key 派生链 | keymgr × otp(secret2)× flash_ctrl(种子页)× kmac(KDF)× 消费方 | 种子读取授权/时机、KDF 输入隔离、跨级清除 |
| F4 | 熵链 | entropy_src(健康检验)→ csrng → edn → aes/hmac/kmac/otbn | 降质熵传播、重播种窗口、alerts 联动 |
| F5 | alert/escalation | 各 IP sender × alert_handler × rstmgr/ibex esc 接收 | 升级计时/宽度、接错 channel、失败闭环 |
| F6 | reset 域 | rstmgr × 全模块复位域 × crashdump 捕获 | 域覆盖完整性、捕获时机、复位值语义 |
| F7 | debug/DFT | rv_dm × lc_ctrl(debug enable)× ibex(ndm/dbg_req) | 生命周期门、越权窗口、debug 会话边界 |
| F8 | 存储加扰 | flash_ctrl × prim_ram_1p_scr/prim_scrambler × otp 加扰密钥 | 密钥使用/清除/窗口、地址加扰一致性 |
| F9 | OTP 分发 | otp_ctrl × 各消化方(pwrmgr/lc/keymgr/flash) | 消化窗口与 partition 锁定时机、digest 校验消费 |
| F10 | lc_tx 外溢 | lc_ctrl multicast lc_tx/lc_rx → 全 IP 访问使能 | tie-off/接错/默认拒绝 |
| F11 | pinmux/pad | pinmux × 各 IO 模块 × pad 属性 | 生命周期相关的 pad 使能门、retention 语义 |

## 方法(每个流程的假设生成模板)
1. 画出流程:入口 → 每个握手/域边界 → 资产汇点
2. 逐边界问三问:授权在哪边校验?失败/超时路径通向哪?跨域时序窗口
   (先到后锁?)有没有缝隙
3. 异常路径优先:复位中途、claim 后失败、部分完成、双发
4. 每个检查点 = 一条 attack-ledger 假设(带资产断言方向——密钥/token/
   状态/取证证据)

## 与模块审计的区别
模块审计(ot-security 车道)问「模块内部逻辑对不对」;流程审计问「跨模块
契约两边是否真的对齐」。两者假设分行登记,不互相替代;流程行的价值密度
高(缝隙无处可藏),登记优先级高于模块重扫。

## 耗尽纪律
每流程的检查点清完(产出或阴性)即 EXHAUSTED 带指针;全部流程 EXHAUSTED
+ 模块面 EXHAUSTED 才允许判收敛。
