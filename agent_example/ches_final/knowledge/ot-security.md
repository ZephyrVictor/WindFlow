# ot-security — 攻击面清单与模块对策地图(审计工单底料)

来源:比赛 scope 声明 + 靶树实况。每轮由晋升机制充实(死路/结构要点按轮
沉淀进共享台账)。

## scope(规则明列)
ibex 核与安全对策、otp_ctrl、rom_ctrl、adc_ctrl、uart、rstmgr、aes、hmac、
kmac、csrng、lc_ctrl、flash_ctrl、alert_handler;**其他模块发现安全 bug
同样可提交**。

## 模块地图(靶树实际路径)

| 模块 | 路径(靶树相对) | 关键资产 | checklist 要点 |
|---|---|---|---|
| ibex | hw/vendor/lowrisc_ibex/rtl/ | PMP/CSR/异常流/lockstep | PMP 边界检查(ibex_pmp)、CSR 读写权限(ibex_cs_registers)、取指通路完整性(ibex_if/id_stage) |
| aes | hw/ip/aes/rtl/ | 轮密钥/状态机 | key_expand 清零(clear-integrity)、ctr_fsm default(fsm-default)、Sec* 参数消费(param-config)、cipher_core 轮间清除(clear-integrity/wipe-reachability) |
| ascon | hw/ip/ascon/rtl/ | 轻量密码状态 | 同 aes 模式面 |
| hmac | hw/ip/hmac/rtl/ | 消息密钥/上下文 | 密钥寄存器清除(clear-integrity)、core FSM default(fsm-default)、reg_top 权限(logic-inversion) |
| kmac | hw/ip/kmac/rtl/ | key/secret key 流 | key_full/key 清除(clear-integrity)、kmac_core 消息路径完整性、sideload 窗口 |
| csrng | hw/ip/csrng/rtl/ | 种子/内部状态 | reg_top 权限检查(logic-inversion)、instantiate/reseed 状态残留(clear-integrity/wipe-reachability) |
| entropy_src | hw/ip/entropy_src/rtl/ | 健康检查/熵池 | 健康检查判定逻辑(logic-inversion)、核心 FSM default(fsm-default)、条件阈值硬编码(param-config) |
| edn | hw/ip/edn/rtl/ | 种子分发 | 命令面 REGWEN 门控(lock-semantics)、重播种窗口 |
| keymgr | hw/ip/keymgr/rtl/ | KDF 密钥/advancing 状态 | ctrl 状态机清除(clear-integrity)、data_en_state 授权流(logic-inversion) |
| otbn | hw/ip/otbn/rtl/ | 密钥运算单元/SP | controller 非法指令流(fsm-default)、密钥寄存器清除(clear-integrity) |
| otp_ctrl | hw/ip/otp_ctrl/rtl/ | OTP secret/lc token | pkg 常量与分发(核对 token/secret 映射)、影子寄存器(lock-semantics)、DAI 访问面 |
| otp_macro | hw/ip/otp_macro/rtl/ | 宏单元存取 | 读写授权/校验路径(logic-inversion) |
| lc_ctrl | hw/ip/lc_ctrl/rtl/ | 生命周期状态/token | fsm 转移矩阵与 default(fsm-default)、signal_decode 输出使能(logic-inversion)——**高危资产,审最深** |
| prim(共享基元) | hw/ip/prim/rtl/ | 全 SoC 复用基元 | prim_onehot_check 判定(logic-inversion)、subreg_shadow 双写机制(lock-semantics)——**改一处影响全部消费 IP,variant 高发区** |
| rom_ctrl | hw/ip/rom_ctrl/rtl/ | 启动 ROM 完整性 | 校验完成信号/门控(logic-inversion)、读通路、跨复位同步(sync-reset) |
| spi_device | hw/ip/spi_device/rtl/ | TPM 通路 | spi_tpm 授权与地址检查(logic-inversion)、读写窗口 |
| flash_ctrl | hw/ip_templates/flash_ctrl/rtl/ | flash 加密/scramble | flash_phy_scramble 密钥使用与清除(clear-integrity)、信息页权限 |
| mbx | hw/ip/mbx/rtl/ | 邮箱数据通路 | imbx 读写授权(logic-inversion) |
| adc_ctrl / uart / rstmgr / alert_handler / pwrmgr | hw/ip/<mod>/ | 辅助面 | rstmgr 复位分发完整性(sync-reset)、alert_handler 升级路径与锁存清除(logic-inversion/lock-semantics)、pwrmgr 低功耗域门 |

## 工单生成指引(planner 用)
- hypotheses = 上表 checklist 要点 × impl-patterns.md 模式面,每工单
  1 个模块 × 2–4 个具体怀疑点
- prim/lc_ctrl/otp/keymgr 属高资产密度模块,值得双开(A+B)
- scope 内的辅助模块(adc_ctrl/uart/rstmgr/alert_handler/pwrmgr 等)
  与外设是安全 bug 的开阔地带,round-1 不裁
- 每个工单的第一件事=该模块的**交付现实基线**(引导流对该 IP 做了什么)
