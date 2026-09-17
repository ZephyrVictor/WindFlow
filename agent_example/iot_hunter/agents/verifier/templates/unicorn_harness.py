#!/usr/bin/env python3
"""unicorn_harness.py — 单体固件函数级仿真 harness 模板。

verifier 从本模板复制到工作目录改造：入口/sink 地址、参数缓冲构造、
dump 观察点按 skill 工单给定值填入（不要自己推算地址）。

用法（参数化部分可直接命令行使用，特殊缓冲构造需改代码）：
  python3 unicorn_harness.py --image <裸码文件> --base 0x80010000 \
      --arch mips-be --entry 0x800ca030 --stop-at 0x80315ea0 \
      --a0 0x7fe00000 --dump-at 0x7fd00000,4096

退出码：0 = 执行到 stop-at；3 = 未映射访问（附地址，按需补零页重试）
"""

from __future__ import annotations

import argparse
import sys

from unicorn import (
    UC_ARCH_ARM,
    UC_ARCH_MIPS,
    UC_ARCH_PPC,
    UC_HOOK_MEM_UNMAPPED,
    UC_MODE_ARM,
    UC_MODE_BIG_ENDIAN,
    UC_MODE_LITTLE_ENDIAN,
    UC_MODE_PPC32,
    UC_MODE_32,
    Uc,
)
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3, UC_MIPS_REG_SP, UC_MIPS_REG_RA
from unicorn.ppc_const import UC_PPC_REG_3, UC_PPC_REG_4, UC_PPC_REG_5, UC_PPC_REG_6, UC_PPC_REG_R1, UC_PPC_REG_LR
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR

# 哨兵返回地址：emu_start 的 until；目标函数"返回"时落到这里即停
MAGIC_RET = 0x70000000
STACK_TOP = 0x7FFF0000
STACK_SIZE = 0x00100000


def make_uc(arch: str):
    if arch == "mips-be":
        return Uc(UC_ARCH_MIPS, UC_MODE_32 | UC_MODE_BIG_ENDIAN), "mips"
    if arch == "mips-el":
        return Uc(UC_ARCH_MIPS, UC_MODE_32 | UC_MODE_LITTLE_ENDIAN), "mips"
    if arch == "ppc-be":
        return Uc(UC_ARCH_PPC, UC_MODE_PPC32 | UC_MODE_BIG_ENDIAN), "ppc"
    if arch == "arm-el":
        return Uc(UC_ARCH_ARM, UC_MODE_ARM | UC_MODE_LITTLE_ENDIAN), "arm"
    raise SystemExit(f"unsupported arch {arch}")


def set_args(uc, family: str, a0: int, a1: int, a2: int, a3: int, ret: int):
    if family == "mips":
        for reg, val in ((UC_MIPS_REG_A0, a0), (UC_MIPS_REG_A1, a1),
                         (UC_MIPS_REG_A2, a2), (UC_MIPS_REG_A3, a3)):
            uc.reg_write(reg, val)
        uc.reg_write(UC_MIPS_REG_SP, STACK_TOP - 0x1000)
        uc.reg_write(UC_MIPS_REG_RA, ret)
    elif family == "ppc":
        for reg, val in ((UC_PPC_REG_3, a0), (UC_PPC_REG_4, a1),
                         (UC_PPC_REG_5, a2), (UC_PPC_REG_6, a3)):
            uc.reg_write(reg, val)
        uc.reg_write(UC_PPC_REG_R1, STACK_TOP - 0x1000)
        uc.reg_write(UC_PPC_REG_LR, ret)
    else:  # arm
        for reg, val in ((UC_ARM_REG_R0, a0), (UC_ARM_REG_R1, a1),
                         (UC_ARM_REG_R2, a2), (UC_ARM_REG_R3, a3)):
            uc.reg_write(reg, val)
        uc.reg_write(UC_ARM_REG_SP, STACK_TOP - 0x1000)
        uc.reg_write(UC_ARM_REG_LR, ret)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, help="裸机器码文件（非 ELF 亦可）")
    ap.add_argument("--base", required=True, type=lambda x: int(x, 0), help="加载基址")
    ap.add_argument("--arch", required=True, choices=["mips-be", "mips-el", "ppc-be", "arm-el"])
    ap.add_argument("--entry", required=True, type=lambda x: int(x, 0))
    ap.add_argument("--stop-at", type=lambda x: int(x, 0), default=MAGIC_RET,
                    help="观察点地址（如 sink 函数入口）；到达即停并 dump")
    ap.add_argument("--a0", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--a1", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--a2", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--a3", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--map", action="append", default=[],
                    help="额外零页，格式 0xADDR,0xSIZE（补全局表用，可多次）")
    ap.add_argument("--dump-at", required=True,
                    help="dump 目标，格式 0xADDR,LEN——stop 时导出该缓冲内容")
    args = ap.parse_args()

    dump_addr_s, dump_len_s = args.dump_at.split(",")
    dump_addr, dump_len = int(dump_addr_s, 0), int(dump_len_s)

    uc, family = make_uc(args.arch)
    body = open(args.image, "rb").read()
    img_size = (len(body) + 0xFFF) & ~0xFFF

    uc.mem_map(args.base, max(img_size, 0x1000))
    uc.mem_write(args.base, body)
    uc.mem_map(STACK_TOP - STACK_SIZE, STACK_SIZE)
    uc.mem_map(MAGIC_RET & ~0xFFF, 0x1000)  # 哨兵页（全零，落到即停）
    for m in args.map:
        addr_s, size_s = m.split(",")
        addr, size = int(addr_s, 0), int(size_s, 0)
        uc.mem_map(addr & ~0xFFF, (size + 0xFFF) & ~0xFFF)

    unmapped: list[int] = []

    def hook_unmapped(uc_, access, address, size, value, user_data):
        unmapped.append(address)
        # 补零页让执行继续（定性记录在案）；若目标明显是 MMIO，工单排查节指引重选
        try:
            uc_.mem_map(address & ~0xFFF, 0x1000)
            return True
        except Exception:
            return False

    uc.hook_add(UC_HOOK_MEM_UNMAPPED, hook_unmapped)

    set_args(uc, family, args.a0, args.a1, args.a2, args.a3, MAGIC_RET)
    try:
        uc.emu_start(args.entry, args.stop_at, timeout=30 * 1000 * 1000)
    except Exception as e:
        pc = uc.reg_read({"mips": UC_MIPS_REG_RA}.get(family, UC_ARM_REG_LR))
        print(f"EMU-ERROR: {e}", file=sys.stderr)
        if unmapped:
            print(f"UNMAPPED-ACCESS: {[hex(a) for a in unmapped[:10]]}", file=sys.stderr)
        return 3

    data = uc.mem_read(dump_addr, dump_len)
    print(f"# stopped at {hex(args.stop_at)} (PC)")
    if unmapped:
        print(f"# unmapped accesses (auto-mapped zero pages): {[hex(a) for a in unmapped[:10]]}")
    sys.stdout.write("# dump {} len {}:\n".format(hex(dump_addr), dump_len))
    # 同时输出可 grep 的文本行与完整 hexdump
    printable = bytes(b if 32 <= b < 127 or b in (9, 10) else 0x2E for b in data)
    print(f"# text: {printable.decode('ascii', errors='replace')}")
    for off in range(0, min(dump_len, 512), 16):
        chunk = data[off:off + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        print(f"{dump_addr + off:08x}  {hexs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
