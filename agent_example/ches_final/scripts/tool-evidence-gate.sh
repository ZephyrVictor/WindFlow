#!/usr/bin/env bash
# tool-evidence-gate.sh — contamination gate for evidence/tool/ (delivery-format §6).
# Usage: bash tool-evidence-gate.sh <tool-dir>
#
# Two scan scopes, by design:
#   identifier battery — API keys; internal markers loaded from
#     lint-codenames.txt (codenames / prior-work structure / sibling paths).
#     These strings have no legitimate occurrence anywhere: raw-byte scan of
#     every packaged file except the gate itself.
#   comparison vocabulary — upstream / 上游 / standalone diff / public repo /
#     repo URLs / pristine. Scanned ONLY inside session transcripts, and only
#     over agent-authored and user-typed text: assistant text blocks and
#     tool_use inputs, plus user-typed records after the initial prompt.
#     Exempt (they legitimately carry these words as banned-word listings,
#     or echo such listings through Read results): tool_result content, the
#     initial task prompt (archived separately under prompts/), compaction
#     summaries, <system-reminder> spans, thinking blocks (instruction
#     recitation is compliance, not violation), and the prompts/ + scripts/
#     trees (authored rulebook / harness material).
# Any HARD hit = that bug drops the tool claim (Q15 -> Simulation); session
# originals are never edited. A copy of this script ships in tool/scripts/;
# lint-codenames.txt does not travel with it (marker battery then inactive,
# vocabulary + key batteries remain).
set -u
export LC_ALL=C
DIR="${1:?usage: tool-evidence-gate.sh <tool-dir>}"
[ -d "$DIR" ] || { echo "GATE FAIL: no such dir $DIR" >&2; exit 1; }
# resolve SCRIPT_DIR from the invocation path BEFORE cd — a relative
# invocation would otherwise look for lint-codenames.txt inside the
# scanned tree and silently disable the marker battery
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE_NAME="$(basename "${BASH_SOURCE[0]}")"
cd "$DIR" || exit 2
hard=""
warn=""
hardhit() { echo "HARD: $*" >&2; hard=1; }
warnhit() { echo "WARN: $*" >&2; warn=1; }

rawscan() {  # $1 = extended regex, $2 = label (case-insensitive raw-byte scan)
  local pat="$1" label="$2" hits
  hits=$(find . -type f ! -name "$GATE_NAME" -print0 \
         | xargs -0 -r grep -lniE "$pat" 2>/dev/null)
  [ -n "$hits" ] || return 0
  while IFS= read -r line; do echo "  $line"; done <<< "$hits"
  hardhit "$label"
}

# 1. API key material (fatal everywhere; case-sensitive shapes)
hits=$(find . -type f ! -name "$GATE_NAME" -print0 \
       | xargs -0 -r grep -lnE 'sk-[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY' 2>/dev/null)
if [ -n "$hits" ]; then
  while IFS= read -r line; do echo "  $line"; done <<< "$hits"
  hardhit 'API key / private key material'
fi

# 2. internal markers (codenames / prior-work structure / sibling paths) —
#    pattern list lives in lint-codenames.txt next to this script and never ships
if [ -f "$SCRIPT_DIR/lint-codenames.txt" ]; then
  while IFS= read -r pat; do
    [ -n "$pat" ] || continue
    rawscan "$pat" "internal marker [$pat]"
  done < "$SCRIPT_DIR/lint-codenames.txt"
fi

# 3. comparison vocabulary — transcript-text scope only (header rationale)
python3 - "$DIR" <<'PYEOF' || hardhit 'comparison vocabulary in session text (per-record hits above)'
import json, re, sys, glob, os
root = sys.argv[1]
VOCAB = re.compile(
    r'(?<![A-Za-z0-9_])(upstream|diff|pristine)(?![A-Za-z0-9_])'
    r'|上游'
    r'|public repo|github\.com|bitbucket', re.I)
REM = re.compile(r'<system-reminder>.*?</system-reminder>', re.S)
COMPACTION = 'This session is being continued from a previous conversation'
hits = []
for path in sorted(glob.glob(os.path.join(root, '**', '*.jsonl'), recursive=True)):
    rel = os.path.relpath(path, root)
    if rel.split(os.sep)[0] in ('prompts', 'scripts'):
        continue
    seen_assistant = False
    try:
        lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    except Exception:
        continue
    for ln, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        typ = r.get('type')
        if typ == 'assistant':
            seen_assistant = True
            blocks = (r.get('message') or {}).get('content')
            if isinstance(blocks, str):
                blocks = [{'type': 'text', 'text': blocks}]
            for b in blocks or []:
                if not isinstance(b, dict):
                    continue
                if b.get('type') == 'text':
                    m = VOCAB.search(b.get('text', ''))
                    if m:
                        hits.append(f'{rel}:{ln} (assistant text): {m.group(0)!r}')
                elif b.get('type') == 'tool_use':
                    s = json.dumps(b.get('input', {}), ensure_ascii=False)
                    m = VOCAB.search(s)
                    if m:
                        hits.append(f'{rel}:{ln} (assistant tool_use): {m.group(0)!r}')
                # thinking blocks: skipped — model-internal scratch; reciting
                # the banned-word instructions is compliance, not violation
        elif typ == 'user':
            if not seen_assistant:
                continue  # initial task prompt — archived (and exempt) as prompts/
            c = (r.get('message') or {}).get('content')
            parts = [c] if isinstance(c, str) else \
                [b.get('text', '') for b in (c or [])
                 if isinstance(b, dict) and b.get('type') == 'text']
            for t in parts:
                t = REM.sub('', t)
                if t.startswith(COMPACTION):
                    continue  # compaction echo may embed rulebook/tool-result text
                m = VOCAB.search(t)
                if m:
                    hits.append(f'{rel}:{ln} (user text): {m.group(0)!r}')
for h in hits:
    print('  ' + h)
sys.exit(1 if hits else 0)
PYEOF

# 4. soft battery (operator review before export; not an automatic drop) —
#    possible internal n-codes in transcripts
hits=$(find . -type f -name '*.jsonl' ! -name "$GATE_NAME" -print0 \
       | xargs -0 -r grep -lnP "(?<!['A-Za-z0-9])[nN][0-9]{1,2}(?![A-Za-z0-9])" 2>/dev/null)
if [ -n "$hits" ]; then
  while IFS= read -r line; do echo "  $line"; done <<< "$hits"
  warnhit 'possible internal n-code in transcripts (review context)'
fi

if [ -n "$hard" ]; then
  echo "TOOL-GATE FAIL: $DIR — drop the tool claim for this bug (Q15 -> Simulation); never edit session originals" >&2
  exit 1
fi
echo "TOOL-GATE PASS: $DIR${warn:+ (with WARN items — operator review)}"
exit 0
