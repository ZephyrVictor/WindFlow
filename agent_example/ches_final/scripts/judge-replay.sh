#!/usr/bin/env bash
# judge-replay.sh — judge-exact container replay of an exploit package.
# Replicates the official judge flow verbatim: copy exploit/src/ into a FRESH
# /opt/opentitan/exploit/ inside the unmodified Docker image, then run
# `make && make run` under the image's own default environment (no env
# overrides, no extra packages, no manual steps). Asserts the judge-visible
# outcome: EXPLOIT_SUCCESS as the last stdout line, exit 0, total wall <= 30
# minutes. Verdict strings, not exit codes, are the judge's scoring basis —
# this script checks both because our make-package contract promises both.
# INTERNAL ONLY — lives in workdir/, never ships.
# Usage: bash judge-replay.sh <pkg-dir> [container] [scratch-dir]
#   <pkg-dir>     staged package dir (must contain exploit/src/)
#   [container]   judge container name; default = busiest-free pick
#   [scratch-dir] in-container work dir; default = unique per invocation
#                 (/opt/opentitan/exploit-<pid>-<epoch>). Two concurrent
#                 replays must never share scratch: the fresh-dir step
#                 rm -rf's it, which clobbers a peer mid-run and produces a
#                 bogus FAIL. Packages reference only TREE=/opt/opentitan,
#                 never their own location, so any scratch under /opt/opentitan
#                 is outcome-equivalent; pass /opt/opentitan/exploit explicitly
#                 to replicate the judge's exact path.
set -u
PKG="${1:?usage: judge-replay.sh <pkg-dir> [container] [scratch-dir]}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CID="${2:-$(bash "$SCRIPT_DIR/docker-pick.sh")}" || { echo "JUDGE-REPLAY FAIL: no judge container available" >&2; exit 2; }
SCRATCH="${3:-/opt/opentitan/exploit-$$-$(date +%s)}"

if [ ! -d "$PKG/exploit/src" ]; then
  echo "JUDGE-REPLAY SKIP: $PKG/exploit/src missing (no exploit deliverable)" >&2
  exit 3
fi

echo "# pkg: $PKG"
echo "# container: $CID"
echo "# scratch: $SCRATCH"

# fresh judge scratch (the only tree location judges themselves write).
# Cleanup runs as root: prior test runs may have left uid-mismatched files
# (docker cp preserves the copying host's uid) that the image's default user
# (player, uid 1001) cannot remove; ownership is normalized to player so the
# build below runs exactly as the judge's default user would see it.
docker exec -u 0 "$CID" bash -c "rm -rf '$SCRATCH' && mkdir -p '$SCRATCH' && chown player:player '$SCRATCH'" || exit 2
docker cp "$PKG/exploit/src/." "$CID:$SCRATCH/" || exit 2
docker exec -u 0 "$CID" chown -R player:player "$SCRATCH" || exit 2

OUT="$(mktemp /tmp/judge-replay.XXXXXX.out)"
ERR="$(mktemp /tmp/judge-replay.XXXXXX.err)"
t0=$SECONDS
docker exec -w "$SCRATCH" "$CID" bash -c 'make && make run' >"$OUT" 2>"$ERR"
rc=$?
wall=$((SECONDS - t0))

lastline="$(grep -v '^[[:space:]]*$' "$OUT" | tail -n 1 | tr -d '\r')"
echo "# wall: ${wall}s  exit: $rc  last-stdout: [$lastline]"
echo "# log: $OUT (stderr: $ERR)"

fail=0
[ "$rc" -eq 0 ] || { echo "JUDGE-REPLAY FAIL: make && make run exited $rc (contract: always exit 0)" >&2; fail=1; }
[ "$wall" -le 1800 ] || { echo "JUDGE-REPLAY FAIL: wall ${wall}s > 1800s judge budget" >&2; fail=1; }
[ "$lastline" = "EXPLOIT_SUCCESS" ] || { echo "JUDGE-REPLAY FAIL: last stdout line is not EXPLOIT_SUCCESS" >&2; fail=1; }

if [ "$fail" -eq 0 ]; then
  echo "JUDGE-REPLAY PASS: $PKG (${wall}s, EXPLOIT_SUCCESS, exit 0)"
else
  tail -n 20 "$OUT" "$ERR" >&2
fi
rm -f "$ERR"
exit "$fail"
