#!/usr/bin/env bash
# tool-evidence-collect.sh — per-bug tool-evidence assembler (delivery-format §6).
# Usage: bash tool-evidence-collect.sh <bug-id> [--phase discovery|full]
#   discovery: auditor + poc-runner sessions (run by bug-planner BEFORE the
#              report chain starts — tokens.txt is then stable for Q23)
#   full     : adds report/verify/exploit/check chain sessions (run by
#              packager/controller before export; discovery section unchanged)
# Assembles staged/<bug-id>/evidence/tool/{README.md,architecture.md,prompts/,
# responses/,scripts/,tokens.txt} and runs the contamination gate.
# INTERNAL ONLY as a workdir script; a copy legitimately ships in tool/scripts/.
set -u
export LC_ALL=C
BUG="${1:?usage: tool-evidence-collect.sh <bug-id> [--phase discovery|full]}"
PHASE="discovery"
shift 2>/dev/null || true
while [ $# -gt 0 ]; do
  case "$1" in
    --phase) PHASE="${2:?--phase needs a value}"; shift 2 ;;
    discovery|full) PHASE="$1"; shift ;;
    *) echo "collect: unknown arg $1" >&2; exit 2 ;;
  esac
done
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNS="$ROOT/runs"
STAGED="$ROOT/workdir/staged/$BUG"
TOOL="$STAGED/evidence/tool"
SESSDIR="${CLAUDE_PROJECT_SESSIONS_DIR:-$HOME/.claude/projects/$(printf '%s' "$ROOT/workdir" | tr / -)}"

[ -d "$STAGED" ] || { echo "COLLECT FAIL: no staged dir $STAGED" >&2; exit 1; }

# ---- 1. resolve the node chain ------------------------------------------
# chain nodes from the chain work order (explicit list) ...
CHAIN_NODES=$(grep -h '^chain-node:' "$RUNS"/plan/skills-b/"$BUG".md 2>/dev/null \
  | sed 's/^chain-node:[[:space:]]*//; s/[[:space:]]*$//')
# ... or from the batch flow.yaml that contains b<BUG>-report
if [ -z "$CHAIN_NODES" ]; then
  for y in $(ls -t "$RUNS"/plan/bug-batch-*/flow.yaml 2>/dev/null); do
    if grep -q "b${BUG}-report" "$y" 2>/dev/null; then
      RID=$(basename "$(dirname "$(dirname "$y")")")
      for n in report verify exploit check; do
        grep -q "b${BUG}-${n}" "$y" && CHAIN_NODES="$CHAIN_NODES
$RID/b${BUG}-${n}"
      done
      break
    fi
  done
fi
# fallback: skills-b may live under <run-root>/plan (find newest)
if [ -z "$CHAIN_NODES" ]; then
  WO=$(ls -t "$RUNS"/*/plan/skills-b/"$BUG".md 2>/dev/null | head -1)
  [ -n "$WO" ] && CHAIN_NODES=$(grep '^chain-node:' "$WO" | sed 's/^chain-node:[[:space:]]*//')
fi

# poc-runner node(s): the poc order for this id + the wave yaml that injects it
POC_NODES=""
POC_ORDER=$(ls -t "$RUNS"/*/plan/poc-orders/"$BUG".md 2>/dev/null | head -1)
if [ -n "$POC_ORDER" ]; then
  for y in $(ls "$RUNS"/*/plan/poc-wave-*/flow.yaml 2>/dev/null); do
    if grep -q "poc-orders/${BUG}.md" "$y" 2>/dev/null; then
      RID=$(basename "$(dirname "$(dirname "$(dirname "$y")")")")
      for n in $(grep -oE '^  poc-[A-Za-z0-9_-]+:' "$y" | tr -d ' :'); do
        POC_NODES="$POC_NODES
$RID/$n"
      done
    fi
  done
fi

# auditor node(s): FINDINGS anchor quoted in the poc order, grepped in summaries
AUD_NODES=""
if [ -n "$POC_ORDER" ]; then
  ANCHOR=$(grep -oE '\[audit-[0-9]+\]' "$POC_ORDER" | head -1)
  if [ -n "$ANCHOR" ]; then
    for s in $(grep -lF "## ${ANCHOR}" "$RUNS"/*/agents/*/summary.md 2>/dev/null); do
      RID=$(basename "$(dirname "$(dirname "$(dirname "$s")")")")
      NOD=$(basename "$(dirname "$s")")
      AUD_NODES="$AUD_NODES
$RID/$NOD"
    done
    # fallback: tty.log grep (slower)
    if [ -z "$AUD_NODES" ]; then
      for t in $(grep -lF "## ${ANCHOR}" "$RUNS"/*/agents/*/tty.log 2>/dev/null); do
        RID=$(basename "$(dirname "$(dirname "$(dirname "$t")")")")
        NOD=$(basename "$(dirname "$t")")
        AUD_NODES="$AUD_NODES
$RID/$NOD"
      done
    fi
  fi
fi

DISCOVERY_NODES=$(printf '%s\n%s\n' "$AUD_NODES" "$POC_NODES" | grep -v '^$' | sort -u)
if [ -z "$DISCOVERY_NODES" ]; then
  echo "COLLECT WARN: no discovery nodes resolved for $BUG (no poc order / auditor anchor found)" >&2
fi

# The work order's explicit chain-node list is authoritative when present:
# bug-planner records the discovery chain there (auditor + poc-runner +
# rework nodes) and appends the validation chain nodes after the batch
# launches. The auto-resolution above (poc-order filename + [audit-N]
# anchor) is ambiguous when several auditors share a FINDINGS section
# number, so it stays as the fallback for work orders without an explicit
# list. Phase membership is decided by node-name pattern, not by aud/poc
# substrings: validation nodes are exactly b<NN>-<stage> names.
EFFECTIVE_NODES="$DISCOVERY_NODES"
if [ -n "$CHAIN_NODES" ]; then
  EFFECTIVE_NODES="$CHAIN_NODES"
  printf '%s\n' $CHAIN_NODES | grep -qE '(aud|poc)' \
    || echo "COLLECT WARN: chain-node list has no auditor/poc-runner node for $BUG" >&2
fi

# ---- 2. assemble tool/ ---------------------------------------------------
# tool/ is fully generated — wipe and rebuild so re-collection is idempotent
rm -rf "$TOOL"
mkdir -p "$TOOL/prompts" "$TOOL/responses" "$TOOL/scripts"
COLLECTED=""
collect_node() {  # $1 = run/node
  local rid="${1%%/*}" nod="${1##*/}"
  local nd="$RUNS/$rid/agents/$nod"
  [ -d "$nd" ] || { echo "COLLECT WARN: missing node dir $nd" >&2; return; }
  mkdir -p "$TOOL/prompts/${rid}__${nod}" "$TOOL/responses/${rid}__${nod}"
  cp -f "$nd/task.md" "$TOOL/prompts/${rid}__${nod}/" 2>/dev/null
  cp -f "$nd/agent.md" "$TOOL/prompts/${rid}__${nod}/" 2>/dev/null
  # session JSONL: first user record contains the node dir path
  local jl=""
  if [ -d "$SESSDIR" ]; then
    for f in $(grep -l "runs/${rid}/agents/${nod}/" "$SESSDIR"/*.jsonl 2>/dev/null); do
      if python3 - "$f" "$rid" "$nod" <<'PY'
import json,sys
f,rid,nod=sys.argv[1],sys.argv[2],sys.argv[3]
try:
    for line in open(f):
        r=json.loads(line)
        if r.get('type')=='user':
            c=r.get('message',{}).get('content','')
            if isinstance(c,list): c=' '.join(str(x.get('text','')) for x in c if isinstance(x,dict))
            sys.exit(0 if (f"runs/{rid}/agents/{nod}/" in c) else 1)
except Exception: sys.exit(1)
PY
      then jl="$jl $f"; fi
    done
  fi
  if [ -n "$jl" ]; then
    local i=1
    for f in $jl; do cp -f "$f" "$TOOL/responses/${rid}__${nod}/transcript$([ $i -gt 1 ] && echo $i).jsonl"; i=$((i+1)); done
  else
    cp -f "$nd/tty.log" "$TOOL/responses/${rid}__${nod}/tty.log" 2>/dev/null \
      && echo "COLLECT NOTE: no session JSONL for $1, copied tty.log" >&2
  fi
  COLLECTED="$COLLECTED $1"
}

for n in $EFFECTIVE_NODES; do collect_node "$n"; done

# scripts: campaign orchestration + harness scripts (+ this bug's sub-pipelines)
cp -f "$ROOT/flow.yaml" "$TOOL/scripts/" 2>/dev/null
for y in "$ROOT"/pipelines/*.yaml; do cp -f "$y" "$TOOL/scripts/" 2>/dev/null; done
for y in $(ls "$RUNS"/*/plan/poc-wave-*/flow.yaml 2>/dev/null) \
         $(ls "$RUNS"/*/plan/bug-batch-*/flow.yaml 2>/dev/null); do
  if grep -q "poc-orders/${BUG}.md\|b${BUG}-report\|skills-b/${BUG}.md" "$y" 2>/dev/null; then
    d=$(dirname "$y"); rid=$(basename "$(dirname "$(dirname "$d")")"); sub=$(basename "$d")
    mkdir -p "$TOOL/scripts/${rid}__${sub}" && cp -f "$y" "$TOOL/scripts/${rid}__${sub}/"
  fi
done
for s in lint_pkg.sh judge-replay.sh cvss_calc.py docker-pick.sh \
         tool-evidence-collect.sh tool-evidence-gate.sh; do
  cp -f "$SCRIPT_DIR/$s" "$TOOL/scripts/" 2>/dev/null
done
# injected knowledge files = prompt material for every session
if [ -d "$ROOT/knowledge" ]; then
  mkdir -p "$TOOL/prompts/knowledge"
  cp -f "$ROOT"/knowledge/*.md "$TOOL/prompts/knowledge/" 2>/dev/null
fi

# ---- 3. tokens.txt + architecture.md -------------------------------------
python3 - "$TOOL" "$BUG" "$PHASE" "$SCRIPT_DIR" <<'PY'
import json, os, sys, glob, datetime
tool, bug, phase = sys.argv[1], sys.argv[2], sys.argv[3]
def usage_of(path):
    inp=out=cr=cc=0; model=None
    try:
        for line in open(path):
            try: r=json.loads(line)
            except Exception: continue
            if r.get('type')=='assistant':
                m=r.get('message',{}); model=model or m.get('model')
                u=m.get('usage') or {}
                inp+=u.get('input_tokens',0); out+=u.get('output_tokens',0)
                cr+=u.get('cache_read_input_tokens',0); cc+=u.get('cache_creation_input_tokens',0)
    except Exception: pass
    return inp,cr,cc,out,model
rows=[]
for d in sorted(glob.glob(f"{tool}/responses/*__*")):
    name=os.path.basename(d)
    for f in sorted(glob.glob(f"{d}/*.jsonl")):
        i,cr,cc,o,m=usage_of(f)
        rows.append((name,os.path.basename(f),i,cr,cc,o,m))
    # tty.log-only nodes carry no machine usage; noted below

# representative response sample per session (judge-facing evidence scope:
# prompts in full + response excerpts prove LLM usage; the full session is
# used for token accounting and gate scanning only, and is removed from the
# shipped tree after the gate passes)
for d in sorted(glob.glob(f"{tool}/responses/*__*")):
    for f in sorted(glob.glob(f"{d}/transcript*.jsonl")):
        recs=[]
        for line in open(f, encoding='utf-8', errors='replace'):
            line=line.strip()
            if not line: continue
            try: recs.append(json.loads(line))
            except Exception: continue
        users=[r for r in recs if r.get('type')=='user']
        asst=[r for r in recs if r.get('type')=='assistant']
        idx=set(range(0,min(3,len(asst))))
        if len(asst)>3:
            idx |= set(range(len(asst)-2,len(asst)))
        sel=([users[0]] if users else [])+[asst[i] for i in sorted(idx)]
        with open(f"{d}/response-sample.jsonl","w",encoding='utf-8') as w:
            for r in sel:
                w.write(json.dumps(r,ensure_ascii=False)+"\n")
import re as _re
def _validation(name):
    # session dirs are "<run-id>__<node>"; validation chain nodes use the
    # fixed b<NN>-<stage> naming (appended to the work order after batch
    # launch) — everything else is discovery-chain, so rework sessions are
    # metered into the DISCOVERY section like auditor/poc-runner sessions
    node=name.split('__',1)[1] if '__' in name else name
    return bool(_re.match(r'b\d+-(report|verify|exploit|check)$',node))
discovery=[r for r in rows if not _validation(r[0])]
def sect(title, rs):
    ti=tr=tc=to=0; lines=[f"## {title}","session | file | input_new | cache_read | cache_creation | output | input_reported | total | model"]
    for n,f,i,cr,cc,o,m in rs:
        rep=i+cr+cc; tot=rep+o; ti+=i; tr+=cr; tc+=cc; to+=o
        lines.append(f"{n} | {f} | {i} | {cr} | {cc} | {o} | {rep} | {tot} | {m or 'n/a'}")
    rep=ti+tr+tc; tot=rep+to
    lines.append(f"TOTAL | | {ti} | {tr} | {tc} | {to} | {rep} | {tot} |")
    lines.append("")
    return lines, rep, tot
out=["# tokens.txt — per-session LLM usage (bug: %s, phase: %s)"%(bug,phase),
     "input_reported = input_new + cache_read + cache_creation (prompt-cache reads included in input).",
     "Q23 (Token usage) numbers = the DISCOVERY section totals below.",""]
l1,rep1,tot1=sect("DISCOVERY chain (= Q23 numbers)",discovery)
out+=l1
if phase=='full':
    other=[r for r in rows if r not in discovery]
    l2,rep2,tot2=sect("VALIDATION chain (report/verify/exploit/check — informational)",other)
    out+=l2
else:
    out+=["## VALIDATION chain","(not yet run — assembled at --phase full before export)",""]
open(f"{tool}/tokens.txt","w").write("\n".join(out)+"\n")
# fill architecture template
cand=os.path.join(sys.argv[4], "tool-architecture-template.md")
tpl=open(cand).read() if os.path.exists(cand) else None
model=next((r[6] for r in rows if r[6]),"unknown")
import subprocess
try: cv=subprocess.run(["claude","--version"],capture_output=True,text=True,timeout=20).stdout.strip()
except Exception: cv="unknown"
tpl=(tpl or "# architecture\n(TEMPLATE MISSING)\n").replace("{{CLAUDE_VERSION}}",cv).replace("{{MODEL}}",model)
open(f"{tool}/architecture.md","w").write(tpl)
print("tokens: discovery input_reported=%d total=%d (%d sessions)"%(rep1,tot1,len(discovery)))
PY

# ---- 4. README.md (chain map) --------------------------------------------
{
  echo "# tool/ — discovery and validation chain for ${BUG}"
  echo
  echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ) (phase: ${PHASE})"
  echo
  echo "## Chain map"
  echo "\`prompts/<run>__<node>/\` holds the work order (task.md) and the agent"
  echo "contract (agent.md) as delivered to that session; \`responses/<run>__<node>/\`"
  echo "holds a representative session excerpt (response-sample.jsonl: the delivered"
  echo "prompt plus opening and closing assistant records, with usage records)."
  echo "Per-session token accounting over the full sessions is in tokens.txt."
  echo
  # phase split is deterministic: validation chain nodes use the fixed
  # b<NN>-<stage> naming (recorded in the work order after batch launch);
  # everything else in the chain-node list belongs to the discovery chain
  # (auditor / poc-runner / rework sessions alike)
  DISC_LIST=$(printf '%s\n' $EFFECTIVE_NODES | grep -vE '/b[0-9]+-(report|verify|exploit|check)$' | sort -u)
  VALID_LIST=$(printf '%s\n' $EFFECTIVE_NODES | grep -E '/b[0-9]+-(report|verify|exploit|check)$' | sort -u)
  echo "### Discovery chain (formed and proved the bug — Q23/Q24 basis)"
  [ -n "$DISC_LIST" ] && for n in $DISC_LIST; do echo "- \`$n\`"; done
  [ -z "$DISC_LIST" ] && echo "- (none resolved)"
  if [ "$PHASE" = "full" ]; then
    echo
    echo "### Validation chain (packaged and re-verified the bug)"
    [ -n "$VALID_LIST" ] && for n in $VALID_LIST; do echo "- \`$n\`"; done
  fi
  echo
  echo "## How the LLM led to the bug"
  echo "The auditor session(s) above formed the hypothesis from the target"
  echo "region's delivered-state baseline and declared-guarantee cross-check;"
  echo "the poc-runner session turned it into a machine-judged proof. See the"
  echo "transcripts for the exact prompts and responses."
  echo
  echo "## Re-run"
  echo "\`scripts/\` holds the campaign orchestration and deterministic harness"
  echo "(lint, judge-replay, collector). Verification steps need no API key;"
  echo "discovery re-runs with your own key via the claude CLI (see"
  echo "architecture.md)."
} > "$TOOL/README.md"

# ---- 5. contamination gate ------------------------------------------------
bash "$SCRIPT_DIR/tool-evidence-gate.sh" "$TOOL"
rc=$?
if [ "$rc" -eq 0 ]; then
  # gate passed on the full transcripts; ship only the representative samples
  find "$TOOL/responses" -name 'transcript*.jsonl' -type f -delete 2>/dev/null
  echo "COLLECT DONE: $TOOL (phase $PHASE; nodes:$COLLECTED)"
else
  # mechanical disposition (delivery-format §6): HARD hit = this bug drops the
  # tool claim (Q15 -> Simulation). The contaminated tree never travels:
  # remove it so the staged tree keeps only shippable bytes and the packager
  # can never zip it by accident. Token totals printed above stay recorded in
  # the chain work order and the decisions ledger (internal Q23 basis).
  rm -rf "$TOOL"
  echo "COLLECT DONE: tool/ dropped (gate FAIL — claim dropped, Q15 -> Simulation; phase $PHASE; nodes:$COLLECTED)" >&2
fi
exit $rc
