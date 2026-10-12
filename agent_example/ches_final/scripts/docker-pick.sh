#!/bin/bash
# 判官容器挑闲器 — 输出当前最闲的容器名(stdout 唯一一行)
# 指标=容器内重活进程数(verilator/make/cc1plus;容器各自 PID namespace,互相独立),
# 并列时取 loadavg 低者。注意:容器内 /proc/loadavg 读的是宿主内核,只作并列 Tie-break。
# 用法: C=$(bash scripts/docker-pick.sh) && docker exec "$C" ...
# 全部容器不可用时 exit 1(stderr 说明),调用方应停手记录,不许绕过
FLEET="hackches hackches2 hackches3"
best=""; bestn=999999; bestload=999999
for c in $FLEET; do
  docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null | grep -q true || continue
  n=$(docker exec "$c" bash -c 'pgrep -c "verilator|make|cc1plus|cc1" 2>/dev/null' 2>/dev/null)
  [ -z "$n" ] && n=0
  l=$(docker exec "$c" cat /proc/loadavg 2>/dev/null | awk '{print $1}')
  [ -z "$l" ] && l=999
  echo "  $c busy_procs=$n loadavg=$l" >&2
  pick=0
  awk -v a="$n" -v b="$bestn" 'BEGIN{exit !(a<b)}' && pick=1
  if [ "$n" = "$bestn" ]; then
    awk -v a="$l" -v b="$bestload" 'BEGIN{exit !(a<b)}' && pick=1
  fi
  [ "$pick" = 1 ] && { best="$c"; bestn="$n"; bestload="$l"; }
done
[ -z "$best" ] && { echo "ERROR:no-judge-container-available" >&2; exit 1; }
echo "$best"
