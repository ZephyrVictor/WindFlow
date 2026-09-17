#!/usr/bin/env bash
# flow watchdog — 两类检测：
#   A. API 网关故障自动 nudge：tty.log 尾部含 "API Error" → flow inject 该节点一条恢复提示
#      （确定性基础设施故障，机器直接处理，不经 control；30 分钟节流）
#   B. 运行超时巡检：节点 started_at 距今 > 1800s → inject control 分析卡死/跑偏/正常
#      （stamp 2 小时过期，长故障会重复触发）
# 注意：不能用 tty.log mtime 判"无输出"——claude TUI 每 ~2min 重渲染一帧会持续刷新 mtime（已实证）。
set -u

FLOW=/home/fjw/workspace/flow/develop/.venv/bin/flow
PROJECT=/home/fjw/workspace/flow/iot_hunter
RUNS_DIR=$PROJECT/runs
STAMP_DIR=/tmp/flow-watchdog
IDLE_NODE=1800      # 判据 B：节点运行超 30 分钟
ALERT_TTL=7200      # 判据 B：stamp 2 小时过期（同节点长故障可再次提醒）
NUDGE_TTL=1800      # 判据 A：nudge 30 分钟节流
TTY_TAIL=4000       # 判据 A：检查 tty.log 尾部字节数

mkdir -p "$STAMP_DIR"

now=$(date +%s)
for STATE in "$RUNS_DIR"/*/state.json; do
    [ -f "$STATE" ] || continue
    RUN_ID=$(basename "$(dirname "$STATE")")

for node in $(python3 - "$STATE" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
if d.get("paused"):
    sys.exit()  # 暂停的 run 无编排进程在跑，inject 只会积压
for name, st in d.get("nodes", {}).items():
    if name == "control":
        continue  # control 是常驻角色，"运行时长"无巡检意义
    if st.get("status") == "running":
        print(name)
EOF
); do
    tty="$RUNS_DIR/$RUN_ID/agents/$node/tty.log"

    # --- 判据 A：API 网关故障 → 自动 nudge（30 分钟节流）---
    nudge_stamp="$STAMP_DIR/${RUN_ID}_${node}.nudge"
    if [ -f "$tty" ] && tail -c "$TTY_TAIL" "$tty" 2>/dev/null | strings | grep -q "API Error"; then
        last_nudge=$(cat "$nudge_stamp" 2>/dev/null || echo 0)
        if [ $(( now - last_nudge )) -ge "$NUDGE_TTL" ]; then
            "$FLOW" inject "$node" -p "$PROJECT" -- \
                "【watchdog 自动恢复】检测到你的会话遇到 API 网关故障（API Error）。若网关已恢复，请从中断处继续任务；产物与 memory 都在，不要从头重做。run: $RUN_ID" \
                "$RUN_ID" \
                && echo "$now" > "$nudge_stamp" \
                && echo "$(date -Is) nudged $RUN_ID/$node (API Error in tty tail)"
        fi
        # API 故障期间不必触发超时巡检（原因明确，等网关恢复即可）
        continue
    fi

    # --- 判据 B：运行超时 → 提醒 control 巡检（stamp 2h 过期）---
    alert_stamp="$STAMP_DIR/${RUN_ID}_${node}.alert"
    last_alert=$(cat "$alert_stamp" 2>/dev/null | head -1)
    last_alert=${last_alert:-0}
    [ $(( now - last_alert )) -lt "$ALERT_TTL" ] && continue
    started=$(python3 -c "import json,sys; print(int(json.load(open('$STATE'))['nodes']['$node']['started_at'] or 0))" 2>/dev/null) || continue
    run_age=$(( now - started ))
    if [ "$run_age" -gt "$IDLE_NODE" ]; then
        count=$(cat "$alert_stamp" 2>/dev/null | tail -1)
        count=${count:-0}; count=$(( count + 1 ))
        "$FLOW" inject control -p "$PROJECT" -- \
            "【watchdog 第 ${count} 次提醒】节点 $node 已运行 ${run_age}s（>${IDLE_NODE}s）。请按巡检流程判断卡死/跑偏/正常长任务并给出建议；若之前已提醒过，重点看节点自上次提醒以来是否有新产出。run: $RUN_ID（flow status/inject 操作该 run 时需带 run_id 参数）" \
            "$RUN_ID" \
            && printf '%s\n%s\n' "$now" "$count" > "$alert_stamp" \
            && echo "$(date -Is) alerted $RUN_ID/$node #${count} (run_age=${run_age}s)"
    fi
done
done
