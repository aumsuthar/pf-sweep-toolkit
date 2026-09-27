#!/bin/bash
# ================================================================
# Full superelastic cycle for one CM field: loading, then unloading.
#
# Drives run_stress_sweep.sh twice via SWEEP_* environment overrides.
# The unloading levels are chosen to interleave with the loading ones so the
# two branches sample different stresses and the hysteresis loop reads cleanly.
#
#   loading    0  5 10 15    17    19 20        (0-1000 MPa)
#   unloading        2  4  7  9 11 12 14 16 18   (100-900 MPa)
#
# Above 33 the loading grid is already at unit spacing (34/35/36), so there are
# no integer values in between; the reverse transformation happens well below
# the forward one anyway, so the unload branch starts at 33.
#
# Launch detached, single instance:
#   nohup setsid flock -n /tmp/s1p01_cycle.lock bash run_load_unload.sh \
#         > cycle.log 2>&1 < /dev/null & disown
# ================================================================
set -u
cd "$(dirname "$0")" || exit 1

LOAD_LEVELS="${CYCLE_LOAD_LEVELS:-0 5 10 15 17 19 20}"
UNLOAD_LEVELS="${CYCLE_UNLOAD_LEVELS:-18 16 14 12 11 9 7 4 2 0}"
TOP_STRESS="${CYCLE_TOP_STRESS:-20}"          # last loading level; the unload chain starts from its output

stamp() { echo "[$(date '+%F %T')] $*"; }

stamp "run tag: ${SWEEP_TAG:-s1p01}"
stamp "================= LOADING ================="
stamp "levels: ${LOAD_LEVELS}"
if ! SWEEP_LEVELS="$LOAD_LEVELS" \
     SWEEP_INIT_STRESS=0 \
     SWEEP_FRESH_START=1 \
     bash run_stress_sweep.sh; then
    stamp "LOADING FAILED — not starting the unload."
    exit 1
fi
stamp "loading complete"

stamp "================ UNLOADING ================"
stamp "levels: ${UNLOAD_LEVELS}  (chaining from load${TOP_STRESS})"
if ! SWEEP_LEVELS="$UNLOAD_LEVELS" \
     SWEEP_INIT_STRESS="$TOP_STRESS" \
     SWEEP_FRESH_START=0 \
     bash run_stress_sweep.sh; then
    stamp "UNLOADING FAILED"
    exit 1
fi

stamp "================ CYCLE COMPLETE ================"
stamp "MT logs: $(ls MT_s1p01_* 2>/dev/null | wc -l) files"
ls MT_s1p01_* 2>/dev/null
