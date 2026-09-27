#!/bin/bash
# ============================================================
# set2 SCOUT pass — 100 MPa spacing, 0-1300 MPa.
#
# Purpose: locate each CM's forward and reverse transformation windows so the
# follow-up pass can place 10 MPa sampling on them, exactly as was done for
# set1. set1's fine grid was targeted using windows measured in its coarse
# pass; set2 has no such map yet, and it differs in ways that will move the
# cliffs a long way:
#     avg 50.55% for every point (set1 was 50.95-51.00) -> lower Ni, so a
#         higher Ms and a LOWER transformation stress
#     amp 0.04-1.00% (set1 was 0.40-0.56) -> p10 at 0.04% is close to a
#         uniform composition and may behave nothing like the rest
# The cliffs are ~10 MPa wide, so a blind uniform grid cannot catch them:
# 10 MPa across 0-1300 would be 2200 jobs per CM.
#
# Top stress 26 (1300 MPa) gives headroom; set2's ML V3 values (1148-1274)
# sit well below set1's 1746, and the lower Ni should transform earlier, but
# the low-amplitude points may need the extra range.
#
# 28 steps x 10 CMs = 280 jobs, ~67 GB.
# ============================================================
set -u
LOAD="0 2 4 6 8 10 12 14 16 18 20 22 24 26"
UNLOAD="25 23 21 19 17 15 13 11 9 7 5 3 1 0"
TOP=26

for n in 01 02 03 04 05 06 07 08 09 10; do
    cd "$HOME/s2p$n" || continue
    rm -f cycle.log
    nohup setsid env SWEEP_TAG="s2p$n" CYCLE_LOAD_LEVELS="$LOAD" \
        CYCLE_UNLOAD_LEVELS="$UNLOAD" CYCLE_TOP_STRESS="$TOP" \
        bash run_load_unload.sh > cycle.log 2>&1 < /dev/null &
    disown
    echo "launched s2p$n"
done
echo
echo "scout launched: 10 chains x 28 steps"
