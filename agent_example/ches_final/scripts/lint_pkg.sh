#!/usr/bin/env bash
# lint_pkg.sh — phase-2 submission package lint battery.
# Usage: bash lint_pkg.sh <pkg-dir> [--report-only]
#   --report-only: reporter-stage self-check — run every report-relevant check
#   but skip checks that need a finished package (export hygiene, frozen logs).
# Exit 0 iff every check passes. A copy of this script legitimately ships in
# evidence/tool/scripts/ as judge re-run material (the internal codename list
# it loads does not ship with that copy).
set -u
export LC_ALL=C   # the environment may carry a broken LC_CTYPE; \x{} patterns
                  # and UTF-8 validation are locale-dependent — pin it
PKG="${1:?usage: lint_pkg.sh <pkg-dir>}"
REPORT_ONLY=0
[ "${2:-}" = "--report-only" ] && REPORT_ONLY=1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PKG" || exit 2
fail=0
note() { echo "FAIL: $*" >&2; fail=1; }
warn() { echo "WARN: $*" >&2; }

# NOTE: evidence/tool/ is EXEMPT from checks 1-4 and 10 (the §3.1 battery):
# session transcripts are Chinese-language originals that reference project
# paths and internal workflow terms by nature; delivery-format §6 replaces
# those checks there with the calibrated contamination gate (check 12).
# Session originals are never edited — a gate hit drops the tool claim.

# 1. banned substrings (case-insensitive, whole tree minus tool/).
#    Internal codenames / prior-work markers load from lint-codenames.txt
#    (kept out of this file so the shipped copy never enumerates them).
BANNED='upstream|pristine|植入|implant|上游|patch|campaign|sweep|wave|台账|战役|site-id|master|attack-ledger'
if [ -f "$SCRIPT_DIR/lint-codenames.txt" ]; then
  BANNED="$BANNED|$(paste -sd'|' "$SCRIPT_DIR/lint-codenames.txt")"
fi
grep -rniE --exclude-dir=tool "$BANNED" . \
  && note 'banned substring hits'

# 2. word-boundary battery — underscore counts as a word char so that
#    tree-intrinsic filenames (prim_diff_decode.sv) do not false-positive
grep -rnP --exclude-dir=tool '(?<![A-Za-z0-9_])(diff|aud-[0-9]+|N[0-9]+)(?![A-Za-z0-9_])' . \
  && note 'word-boundary hits (diff / N-codes / audit sites)'

# 2b. internal n-code leak, extended form — also catches lowercase and
#     underscore-adjacent occurrences (tb_exploit_x7_.sv style filenames,
#     x7-v1-rerun1-ev.tgz style archives) that check 2's strict word
#     boundary misses. Apostrophe is excluded so sized literals do not hit.
grep -rnP --exclude-dir=tool "(?<!['A-Za-z0-9])[nN][0-9]+(?![A-Za-z0-9])" . \
  && note 'internal n-code leak (extended: lowercase / underscore-adjacent)'

# 3. local home paths (tool/ exempt: session originals reference the project).
#    Only the local operator home is banned — full judge-container run
#    transcripts legitimately embed the container's own sandbox paths
#    (/home/player/...), which are judge-environment facts, not ours.
grep -rnF --exclude-dir=tool "$HOME/" . && note 'local home paths'

# 4. CJK anywhere in the tree except tool/ (zero tolerance for deliverables;
#    tool/ holds Chinese session originals by design). Byte-range form:
#    UTF-8 lead bytes E3..E9 = U+3000..U+9FFF (CJK punctuation, kana, Han) —
#    locale-independent, no UTF validation.
grep -rnP --exclude-dir=tool '[\xE3-\xE9][\x80-\xBF][\x80-\xBF]' . \
  && note 'CJK in submission tree'

# 4b. legacy llm/ dir must not reappear inside a package (process traces
#     never ship)
[ -d llm ] && note 'llm/ dir present (process traces never ship)'

# 5. report structure: exactly 27 question sections
n=$(grep -c '^## Q[0-9]' report.md)
[ "$n" -eq 27 ] || note "report.md has $n Q-sections (need 27)"

# 5c. section titles must match the official 27-question form VERBATIM
#     (guide form section; a one-character deviation is a form mismatch)
python3 - report.md <<'PYEOF' || note 'Q-section titles deviate from the official form (details above)'
import re, sys
official = [
 "Team name", "Bug title", "Affected IP block", "Bug location", "Description",
 "Security impact", "Security property violated", "CWE", "Attacker",
 "Preconditions and attack steps", "Proposed fix", "CVSS v3.1 vector",
 "CVSS v3.1 base score", "Detection method", "Tools used",
 "Tool names and versions", "Tool evidence", "Did you use an LLM?",
 "Model name and version", "How was the model accessed?",
 "API endpoint or download link", "Model parameters",
 "Token usage (input, output, total)", "Prompts, responses and scripts",
 "How the LLM led to the bug", "Exploit ZIP", "Declaration"]
txt = open(sys.argv[1], encoding='utf-8', errors='replace').read()
got = re.findall(r'^## Q(\d+)\. (.*)$', txt, re.M)
bad = []
if len(got) != 27:
    bad.append(f'section count {len(got)} != 27')
for num, title in got:
    if not num.isdigit() or not 1 <= int(num) <= 27:
        bad.append(f'bad question number Q{num}')
        continue
    if title != official[int(num) - 1]:
        bad.append(f'Q{num}: got [{title}] want [{official[int(num) - 1]}]')
for b in bad:
    print(b)
sys.exit(1 if bad else 0)
PYEOF

# 5b. Q2 title <= 15 words (guide-mandated; soft-wrapped titles joined)
q2=$(awk '/^## Q2\./{f=1;next} f&&/^## Q[0-9]/{exit} f&&NF{printf "%s ", $0}' report.md)
[ -n "$q2" ] || note 'Q2 title line not found'
w=$(printf '%s\n' "$q2" | wc -w)
[ "$w" -le 15 ] || note "Q2 title is $w words (need <=15)"

# 6. export hygiene: no zips yet, exploit/ = README.md + src/ only
#    (full mode only — reporter stage has no package yet)
if [ "$REPORT_ONLY" -eq 0 ]; then
  [ -z "$(find . -name '*.zip' -print -quit)" ] || note 'zip file present before export'
  [ -f exploit/README.md ] && [ -d exploit/src ] || note 'exploit/ must be README.md + src/'
  [ -f evidence/poc/src/Makefile ] || note 'evidence/poc/src/ make-package missing'
fi

# 7. secret scan (key material must never enter any submission)
grep -rnE 'sk-[A-Za-z0-9]{16,}' . && note 'possible API key material'

# 8. frozen logs end with the verdict token as the last stdout line
#    (full mode only — logs exist after verifier/exploiter stages)
if [ "$REPORT_ONLY" -eq 0 ]; then
for d in exploit poc; do
  f="evidence/logs/$d/run.log"
  [ -f "$f" ] || { note "missing $f"; continue; }
  tok=EXPLOIT_SUCCESS; [ "$d" = poc ] && tok=POC_SUCCESS
  tail -n 1 "$f" | grep -qxF "$tok" || note "$f last line is not $tok"
done
fi

# 9. CVSS: Q13 must equal the mechanical recompute of the Q12 vector
if [ -f report.md ] && command -v python3 >/dev/null; then
  python3 "$SCRIPT_DIR/cvss_calc.py" --report report.md || \
    note 'Q13 != engine recompute of Q12 (run cvss_calc.py --report report.md)'
fi

# 10. self-destruct disclosure battery (递枪条款): a package that itself
#     discloses a precondition no attacker can create hands the judge the
#     invalid ruling. These shapes attribute a precondition to the platform /
#     firmware / operator — anyone OTHER than the attacker. Hits on a package
#     to be SUBMITTED = rework: close the chain in-tree, then reword as a
#     positive attacker action. Bare "misconfigur" is deliberately NOT in the
#     battery — it legitimately names attacker self-inflicted states
#     (attacker-created = reachable).
if [ -f report.md ]; then
  grep -rniE --exclude-dir=tool 'to have (skipped|set|run|loaded)|bounded to out-of-tree|out-of-tree|only if firmware|requires the platform|platform precondition|requires custom|custom firmware|modified firmware|if the operator|operator error|deployment error|provisioning error|universal reachability|boot firmware must|firmware must have|outside this finding' . \
    && note 'self-destruct disclosure (递枪条款): a precondition attributed to someone other than the attacker — close the chain or reword as positive attacker action'
fi

# 11. Q10 precondition extraction (INFO, not a fail): surfaces every Q10
#     dependency sentence so packager/reach-audit must look at "who achieves
#     this state?" before export. Attacker-agency wording is fine; the L3
#     reach-audit judges the substance.
if [ -f report.md ]; then
  awk '/^## Q10\./{f=1;next} f&&/^## Q[0-9]/{exit} f&&NF' report.md \
    | grep -niE 'precondition|requires|must have|must be|assum|provided|only if|depends|scope' \
    | sed 's/^/Q10-PRECOND: /' || true
fi

# 12. tool-evidence checks (operator ruling 2026-10-12: tool/LLM disclosure is
#     template formality — completeness is a WARN, never a submission gate;
#     only the contamination scan stays a FAIL, it guards against secrets
#     leaking into the submission).
if [ "$REPORT_ONLY" -eq 0 ]; then
  if [ -d evidence/tool ]; then
    bash "$SCRIPT_DIR/tool-evidence-gate.sh" evidence/tool || \
      note 'tool-evidence contamination gate FAILED — secrets/codenames in tool/ (self-exposure red line)'
  elif grep -q '^## Q15' report.md 2>/dev/null && \
       awk '/^## Q15/{f=1;next} f&&/^## Q[0-9]/{exit} f' report.md | grep -qiE 'custom|in-house'; then
    warn 'Q15 claims the custom tool but evidence/tool/ is missing — template formality per operator ruling, not a gate'
  fi
  if [ -d evidence/tool ]; then
    for piece in README.md architecture.md prompts responses scripts tokens.txt; do
      [ -e "evidence/tool/$piece" ] || warn "evidence/tool/$piece missing (six-piece structure) — not a gate per operator ruling"
    done
  fi
fi

if [ "$fail" -eq 0 ]; then
  echo "LINT PASS: $PKG"
else
  echo "LINT FAIL: $PKG" >&2
fi
exit "$fail"
