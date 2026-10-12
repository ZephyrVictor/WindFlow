#!/usr/bin/env python3
"""cvss_calc.py — CVSS 3.1 base-score engine (mechanical recompute for Q13).

Usage:
  cvss_calc.py "CVSS:3.1/AV:.../..."        # print score + severity band
  cvss_calc.py --report report.md           # verify Q12 vector vs Q13 score (exit 1 on mismatch)
  cvss_calc.py --selftest                   # assert engine on 6 classic vectors

Roundup = ceiling to one decimal (CVSS v3.1 spec). Engine ported from the
validated P1 lint engine (self-tested on the same 6 vectors). INTERNAL ONLY.
"""

import math
import re
import sys
from pathlib import Path

VECTOR_RE = re.compile(
    r"CVSS:3\.1/AV:([NALP])/AC:([LH])/PR:([NLH])/UI:([NR])/S:([UC])"
    r"/C:([HLN])/I:([HLN])/A:([HLN])"
)

W_AV = {"N": 0.852, "A": 0.62, "L": 0.55, "P": 0.2}
W_AC = {"L": 0.77, "H": 0.44}
W_PR = {"N": 0.85, "L": 0.62, "H": 0.27}
W_PR_CHANGED = {"N": 0.85, "L": 0.68, "H": 0.5}
W_UI = {"N": 0.85, "R": 0.62}
W_CIA = {"H": 0.56, "L": 0.22, "N": 0.0}


def cvss_base_score(av, ac, pr, ui, s, c, i, a):
    prw = (W_PR_CHANGED if s == "C" else W_PR)[pr]
    exploitability = 8.22 * W_AV[av] * W_AC[ac] * prw * W_UI[ui]
    iss = 1 - (1 - W_CIA[c]) * (1 - W_CIA[i]) * (1 - W_CIA[a])
    if s == "U":
        impact = 6.42 * iss
    else:
        impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
    if impact <= 0:
        return 0.0
    base = min(impact + exploitability, 10)
    if s == "C":
        base = min(1.08 * base, 10)
    return math.ceil(round(base * 10, 6)) / 10


def severity_band(score):
    if score == 0:
        return "None"
    if score <= 3.9:
        return "Low"
    if score <= 6.9:
        return "Medium"
    if score <= 8.9:
        return "High"
    return "Critical"


def selftest():
    cases = [
        ("CVSS:3.1/AV:P/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H", 6.3, "Medium"),
        ("CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H", 8.8, "High"),
        ("CVSS:3.1/AV:L/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H", 6.7, "Medium"),
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", 9.8, "Critical"),
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H", 10.0, "Critical"),
        ("CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H", 7.8, "High"),
    ]
    for vec, want_score, want_band in cases:
        m = VECTOR_RE.search(vec)
        assert m, f"selftest vector failed to parse: {vec}"
        got = cvss_base_score(*m.groups())
        assert abs(got - want_score) < 0.001, f"{vec}: got {got}, want {want_score}"
        assert severity_band(got) == want_band, f"{vec}: band {severity_band(got)}"
    print("selftest: 6/6 CVSS vectors OK")
    return 0


def q_section(text, n):
    m = re.search(
        rf"^## Q{n}\..*?$(.*?)(?=^## Q\d+\.|\Z)", text, re.M | re.S
    )
    return m.group(1) if m else ""


def report_check(path):
    text = Path(path).read_text(errors="replace")
    q12, q13 = q_section(text, 12), q_section(text, 13)
    vm = VECTOR_RE.search(q12)
    if not vm:
        print(f"FAIL: no CVSS:3.1 vector found in Q12 of {path}")
        return 1
    sm = re.search(r"\b(\d{1,2}\.\d)\b", q13)
    if not sm:
        print(f"FAIL: no numeric score found in Q13 of {path}")
        return 1
    got = cvss_base_score(*vm.groups())
    claimed = float(sm.group(1))
    print(f"vector:  {vm.group(0)}")
    print(f"engine:  {got:.1f} ({severity_band(got)})")
    print(f"Q13:     {claimed:.1f}")
    if abs(got - claimed) > 0.001:
        print(f"FAIL: Q13 {claimed:.1f} != engine {got:.1f} — fix Q13 to the recompute value")
        return 1
    print("CVSS OK: Q13 equals the mechanical recompute")
    return 0


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = [a for a in argv[1:] if a.startswith("--")]
    if "--selftest" in flags:
        return selftest()
    if not args:
        print(__doc__)
        return 1
    if "--report" in flags:
        return report_check(args[0])
    m = VECTOR_RE.search(args[0])
    if not m:
        print(f"FAIL: not a CVSS:3.1 vector: {args[0]}")
        return 1
    s = cvss_base_score(*m.groups())
    print(f"{s:.1f} ({severity_band(s)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
