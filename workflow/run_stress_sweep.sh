#!/bin/bash
# ================================================================
# NiTi Stress-Strain Curve Automation Script
#
# Features:
#   - Auto-detects loading vs unloading from STRESS_LEVELS order
#   - Reads MVF from output to control NOISE_ON in constants.h
#   - Supports chaining: unloading's first input = last loading output
#   - Safe to run in background (nohup) and to cancel at any time
#
# Usage:
#   Normal (foreground):    bash run_stress_sweep.sh
#   Background:             nohup bash run_stress_sweep.sh > sweep.log 2>&1 &
#   Monitor progress:       tail -f sweep.log
#   Cancel cleanly:         kill <PID>   or   Ctrl+C
#
# To chain loading -> unloading:
#   1. Run loading sweep with STRESS_LEVELS=(0 5 10 ... 50)
#   2. Set INITIAL_INPUT_STRESS=50, INITIAL_INPUT_TIMESTEP=<last timestep>
#   3. Run unloading sweep with STRESS_LEVELS=(50 45 40 ... 0)
# ================================================================

# ================================================================
# USER CONFIGURATION
# ================================================================

# ---- Compiler environment (required for unattended/nohup runs) ----
source /etc/profile.d/lmod.sh 2>/dev/null || true
module load nvhpc/24.11

RUN_TAG="${SWEEP_TAG:-s1p01}"   # job-name / MT-file prefix

# Stress levels IN ORDER. Script auto-detects loading vs unloading.
#   Loading example:   STRESS_LEVELS=(0 5 10 15 20 25 30 35 40)
#   Unloading example: STRESS_LEVELS=(40 35 30 25 20 15 10 5 0)
STRESS_LEVELS=(${SWEEP_LEVELS:-0 5 10 15 20 25 28 30 32 34 35 36})

# The stress level whose output files already exist as the starting input.
#   Loading:   typically the equilibration run at stress=0
#   Unloading: set this to the last loading stress level (e.g. 50)
INITIAL_INPUT_STRESS=${SWEEP_INIT_STRESS:-0}

# Timestep of the INITIAL_INPUT_STRESS output files
INITIAL_INPUT_TIMESTEP=${SWEEP_INIT_TIMESTEP:-15000}

# MVF threshold: NOISE_ON is disabled once MVF exceeds this value
# (only used during loading; unloading always has noise off — see FORCE_NOISE_OFF below)
NOISE_THRESHOLD=0.1

# Set to "true" to disable noise for ALL steps regardless of MVF.
# Automatically set to "true" when DIRECTION=unloading (see below).
FORCE_NOISE_OFF="false"

# Number of eta variant files (0 .. NUM_VARIANTS-1, matches MartV in constants.h)
NUM_VARIANTS=4

# File label prefix for loading and unloading runs
LOAD_PREFIX="load"
UNLOAD_PREFIX="unload"

# Seconds between SLURM job status polls
POLL_INTERVAL=30

# ================================================================
# AUTO-DETECT LOADING VS UNLOADING
# ================================================================

FIRST_STRESS=${STRESS_LEVELS[0]}
LAST_STRESS=${STRESS_LEVELS[${#STRESS_LEVELS[@]}-1]}

if awk "BEGIN{exit !($FIRST_STRESS <= $LAST_STRESS)}"; then
    DIRECTION="loading"
    PREFIX="$LOAD_PREFIX"
else
    DIRECTION="unloading"
    PREFIX="$UNLOAD_PREFIX"
    FORCE_NOISE_OFF="true"   # unloading never needs noise
fi

# ================================================================
# HELPER FUNCTIONS
# ================================================================

# Logging with timestamp
log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ---- Modify STRESS_MAG in inhom_v3.c ----
# Matches:  #define STRESS_MAG (<value>)
set_stress() {
    local stress=$1
    sed -i "s/^#define STRESS_MAG ([^)]*)/\#define STRESS_MAG (${stress})/" inhom_v3.c
    log "  [inhom_v3.c]        STRESS_MAG = ${stress}"
}

# ---- Modify eta input filenames in initialization.c ----
# Matches lines of the form:
#   sprintf(filename,"input_files/eta_pure_<label>_<v>_t<T>.vtk");
set_input_files() {
    local label=$1       # e.g. "load10" or "unload40"
    local timestep=$2
    local num_variants=$3

    for v in $(seq 0 $((num_variants - 1))); do
        sed -i \
          "s|sprintf(filename,\"input_files/eta_pure_[^\"]*_${v}_t[0-9]*.vtk\")|sprintf(filename,\"input_files/eta_pure_${label}_${v}_t${timestep}.vtk\")|g" \
          initialization.c
    done
    log "  [initialization.c]  Input: eta_pure_${label}_{0..$((num_variants-1))}_t${timestep}.vtk"
}

# ---- Select the eta source in initialization.c ----
#   fresh : leave the eta input lines commented -> initial_condition1() (austenite)
#   chain : uncomment them -> read the previous step's eta from input_files/
set_eta_source() {
    local mode=$1
    # NOTE: each sed is a single line. A backslash line-continuation inside the
    # single-quoted script is literal, not a continuation, and silently breaks it.
    if [ "$mode" = "chain" ]; then
        sed -i 's|^//\([[:space:]]*sprintf(filename,"input_files/eta_pure_\)|\1|' initialization.c
        sed -i 's|^//\([[:space:]]*init_from_file(&eta_r\[[0-9]\]\[0\]\[0\]\[0\]\)|\1|' initialization.c
        if grep -q '^//[[:space:]]*init_from_file(&eta_r\[[0-9]\]\[0\]\[0\]\[0\]' initialization.c; then
            log "ERROR: eta input lines are still commented out — chaining would"
            log "       silently start from austenite. Aborting."
            exit 1
        fi
        log "  [initialization.c]  eta source: chained (verified uncommented)"
    else
        sed -i 's|^\([[:space:]]*sprintf(filename,"input_files/eta_pure_\)|//\1|' initialization.c
        sed -i 's|^\([[:space:]]*init_from_file(&eta_r\[[0-9]\]\[0\]\[0\]\[0\]\)|//\1|' initialization.c
        log "  [initialization.c]  eta source: fresh austenite (initial_condition1)"
    fi
}


# ---- Modify output label in io.c and output redirect in slr_run.sh ----
# Matches any existing  eta_pure_load<N>_  or  eta_pure_unload<N>_
set_output_label() {
    local new_label=$1   # e.g. "load25" or "unload20"

    # io.c: replace whichever prefix pattern currently exists
    sed -i "s|eta_pure_${LOAD_PREFIX}[0-9.]*_|eta_pure_${new_label}_|g; \
            s|eta_pure_${UNLOAD_PREFIX}[0-9.]*_|eta_pure_${new_label}_|g" io.c

    # slr_run.sh: replace the output redirect at the end of the last line
    sed -i "s|> MT_.*$|> MT_${RUN_TAG}_${new_label}|" slr_run.sh

    log "  [io.c + slr_run.sh] Output label: ${new_label}"
}

# ---- Modify SLURM --job-name in slr_run.sh ----
set_job_name() {
    local name=$1
    sed -i "s/^#SBATCH --job-name=.*/#SBATCH --job-name=${name}/" slr_run.sh
    log "  [slr_run.sh]        Job name: ${name}"
}

# ---- Enable or disable #define NOISE_ON in constants.h ----
# Matches the line whether or not it is currently commented out
set_noise() {
    local enable=$1   # "on" or "off"
    if [ "$enable" = "on" ]; then
        sed -i 's|^//#define NOISE_ON|#define NOISE_ON|' constants.h
        log "  [constants.h]       NOISE_ON = ENABLED"
    else
        sed -i 's|^#define NOISE_ON$|//#define NOISE_ON|' constants.h
        log "  [constants.h]       NOISE_ON = disabled"
    fi
}

# ---- Extract MVF from the last "vf = <value>" line of an output file ----
# Output line format:  vf = 0.045101 ,v1=... ,v2=...
get_mvf() {
    local output_file=$1
    grep -oP "(?<=vf = )[0-9]+\.[0-9]+" "$output_file" | tail -1
}

# ---- Return "on" or "off" based on MVF vs threshold ----
noise_from_mvf() {
    local mvf=$1
    if [ -z "$mvf" ]; then
        echo "on"   # conservative default if MVF cannot be read
        return
    fi
    awk -v mvf="$mvf" -v thr="$NOISE_THRESHOLD" \
        'BEGIN { print (mvf+0 > thr+0) ? "off" : "on" }'
}

# ---- Wait for a SLURM job to finish ----
wait_for_job() {
    local job_id=$1
    log "  Waiting for SLURM job ${job_id} ..."
    while squeue -j "$job_id" -h 2>/dev/null | grep -q "$job_id"; do
        sleep "$POLL_INTERVAL"
    done
    log "  Job ${job_id} finished."
}

# ---- Clean shutdown handler (Ctrl+C or kill) ----
CURRENT_JOB_ID=""
cleanup() {
    echo ""
    log "Interrupt received — shutting down cleanly."
    if [ -n "$CURRENT_JOB_ID" ]; then
        log "Cancelling SLURM job ${CURRENT_JOB_ID} ..."
        scancel "$CURRENT_JOB_ID"
        log "Job cancelled."
    fi
    log "Exiting. Source files are in their last-modified state."
    exit 1
}
trap cleanup INT TERM

# ================================================================
# MAIN LOOP
# ================================================================

log "======================================================"
log "  NiTi Stress-Strain Sweep  [${DIRECTION}]"
log "  Stress levels : ${STRESS_LEVELS[*]}"
log "  Noise threshold (MVF) : ${NOISE_THRESHOLD}"
log "======================================================"

PREV_LABEL="${SWEEP_INIT_LABEL:-${LOAD_PREFIX}${INITIAL_INPUT_STRESS}}"
PREV_TIMESTEP=$INITIAL_INPUT_TIMESTEP
NOISE_STATE="on"   # always start with noise on

for i in "${!STRESS_LEVELS[@]}"; do
    STRESS=${STRESS_LEVELS[$i]}
    CURRENT_LABEL="${PREFIX}${STRESS}"

    log ""
    log "=== Step ${i}/${#STRESS_LEVELS[@]} : STRESS_MAG = ${STRESS} (${DIRECTION}) ==="

    # ----------------------------------------------------------
    # 1. Determine noise state
    #    Unloading always off; loading uses MVF threshold
    # ----------------------------------------------------------
    if [ "$FORCE_NOISE_OFF" = "true" ]; then
        NOISE_STATE="off"
        log "  Noise: off (unloading — no threshold check needed)"
    elif [ "$i" -gt 0 ]; then
        PREV_OUTPUT_FILE="MT_${PREV_LABEL}"
        if [ -f "$PREV_OUTPUT_FILE" ]; then
            MVF=$(get_mvf "$PREV_OUTPUT_FILE")
            NOISE_STATE=$(noise_from_mvf "$MVF")
            log "  MVF from previous step = ${MVF:-unreadable}  →  noise ${NOISE_STATE}"
        else
            log "  WARNING: '${PREV_OUTPUT_FILE}' not found; keeping noise ${NOISE_STATE}"
        fi
    else
        log "  First step: noise ${NOISE_STATE} (default)"
    fi

    # ----------------------------------------------------------
    # 2. Modify all source files
    # ----------------------------------------------------------
    log "  Modifying source files ..."
    set_noise        "$NOISE_STATE"
    set_stress       "$STRESS"
    set_input_files  "$PREV_LABEL"    "$PREV_TIMESTEP" "$NUM_VARIANTS"
    if [ "$i" -eq 0 ] && [ "${SWEEP_FRESH_START:-1}" = "1" ]; then
        set_eta_source "fresh"
    else
        set_eta_source "chain"
    fi
    set_output_label "$CURRENT_LABEL"
    set_job_name     "${RUN_TAG}_${CURRENT_LABEL}"

    # ----------------------------------------------------------
    # 3. Compile
    # ----------------------------------------------------------
    log "  Compiling ..."
    if ! make 2>&1; then
        log "ERROR: make failed at stress=${STRESS}. Aborting."
        exit 1
    fi
    log "  Compilation OK."

    # ----------------------------------------------------------
    # 4. Submit SLURM job and wait for completion
    # ----------------------------------------------------------
    SUBMIT_OUT=$(sbatch slr_run.sh)
    CURRENT_JOB_ID=$(echo "$SUBMIT_OUT" | grep -oP "(?<=Submitted batch job )\d+")
    if [ -z "$CURRENT_JOB_ID" ]; then
        log "ERROR: Could not parse job ID from: ${SUBMIT_OUT}. Aborting."
        exit 1
    fi
    log "  Submitted SLURM job: ${CURRENT_JOB_ID}"

    wait_for_job "$CURRENT_JOB_ID"
    CURRENT_JOB_ID=""   # clear so cleanup() won't cancel a finished job

    # ---- Verify the step actually produced output -------------------------
    # Void_model.exe calls exit(0) on its error paths (bad input file, wrong
    # grid size), so SLURM reports COMPLETED/0:0 even when nothing ran. Check
    # for the eta files this step was supposed to write before chaining on.
    MISSING=0
    for v in $(seq 0 $((NUM_VARIANTS - 1))); do
        ls output_files/eta_pure_${CURRENT_LABEL}_${v}_t*.vtk >/dev/null 2>&1 || MISSING=1
    done
    if [ "$MISSING" -eq 1 ]; then
        log "ERROR: step ${CURRENT_LABEL} produced no eta output files."
        log "       Check the SLURM .o file for job ${CURRENT_JOB_ID}. Aborting."
        exit 1
    fi
    log "  Output files verified for ${CURRENT_LABEL}."

    # ----------------------------------------------------------
    # 5. Read final timestep from MT_<label> (the program's stdout redirect)
    #    Looks for lines like:  timestep=80000 completed
    # ----------------------------------------------------------
    MT_FILE="MT_${CURRENT_LABEL}"
    if [ -f "$MT_FILE" ]; then
        LAST_STEP=$(grep -oP "(?<=timestep=)\d+" "$MT_FILE" | tail -1)
        if [ -n "$LAST_STEP" ]; then
            PREV_TIMESTEP=$LAST_STEP
            log "  Detected final timestep: ${PREV_TIMESTEP}  (from ${MT_FILE})"
        else
            log "  WARNING: Could not parse timestep from ${MT_FILE}; keeping ${PREV_TIMESTEP}"
        fi
    else
        log "  WARNING: ${MT_FILE} not found; keeping timestep ${PREV_TIMESTEP}"
    fi

    PREV_LABEL="$CURRENT_LABEL"
    log "  → Next input will be: eta_pure_${PREV_LABEL}_*_t${PREV_TIMESTEP}.vtk"
done

log ""
log "======================================================"
log "  All ${#STRESS_LEVELS[@]} steps complete. [${DIRECTION}]"
log "======================================================"
