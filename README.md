# pf-sweep-toolkit

Tooling for running stress sweeps of a GPU phase-field simulation of
stress-induced martensitic transformation in NiTi, on an HPC cluster with
SLURM, and for turning the results into stress–strain curves.

Built around one awkward constraint: **the applied stress is a compile-time
`#define`**, so every stress level needs its own build. A full superelastic
cycle is therefore a chain of dozens of edit → compile → submit → wait →
verify steps, and the whole point of this toolkit is to run that chain
unattended without silently producing garbage.

It does **not** include the simulation itself, or anyone's experimental or
model data — see [Scope](#scope).

---

## What's here

```
workflow/
  run_stress_sweep.sh     one branch (loading OR unloading): edits the sources,
                          compiles, submits, waits, verifies output, chains on
  run_load_unload.sh      drives the above twice for a full cycle
  slr_run.sh              the SLURM job script (1 GPU)
  launch_set1_x3.sh       example: per-design-point levels, fine sampling
                          placed on previously measured transformation windows
  launch_set2_scout.sh    example: coarse pass to locate those windows

cm_generation/
  make_cm.py              sinusoidal concentration-modulation fields as legacy
                          ASCII VTK, on a fixed box
  make_cm_set2_periodic.py  same, but sizes each box to hold a whole number of
                          modulation periods (see Periodicity below)

analysis/
  plot_set1.py            hysteresis loops + model-vs-simulation comparison
  make_cm_excel.py        workbook: parameters, results, embedded renders,
                          figures, raw per-step data
  make_cm_grid.py         contact sheet of the rendered input fields

docs/
  PITFALLS.md             every failure mode this workflow has actually hit,
                          with the error signature for each. Read it.
```

---

## Setup

### On the cluster

```bash
git clone <this repo>
cp pf-sweep-toolkit/workflow/*.sh  /path/to/your/simulation/
cd /path/to/your/simulation
```

Then, once per simulation directory:

1. **Set your SLURM account** in `slr_run.sh`:
   ```
   #SBATCH --account=YOUR_PROJECT
   ```
2. **Set the walltime** in `slr_run.sh` to suit your grid. Measured on one
   A100-class GPU, 15,000 timesteps:

   | grid | cells | runtime | request |
   |------|------:|--------:|---------|
   | 96³  | 0.88 M | ~4 min  | 15 min |
   | 128³ | 2.10 M | ~10 min | 20 min |
   | 144³ | 2.99 M | ~14 min | 30 min |
   | 208³ | 9.00 M | ~43 min | 1 h 15 |
   | 256³ | 16.8 M | ~80 min | 2 h 15 |

   Request tightly. An over-long request cannot backfill into short gaps and
   will sit in the queue far longer than the job takes to run.
3. **Load your compiler module inside the script**, not just in your shell —
   an unattended run has no shell. `run_stress_sweep.sh` has a line for this:
   ```bash
   module load nvhpc/24.11
   ```
4. Make sure `conc/`, `input_files/` and `output_files/` exist.

### Locally, for the analysis

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install numpy matplotlib openpyxl pillow
```

---

## Running a sweep

Stress levels are passed in, not baked into the script:

```bash
# one full cycle
nohup setsid env SWEEP_TAG="run01" \
  CYCLE_LOAD_LEVELS="0 5 10 15 17 19 20 22" \
  CYCLE_UNLOAD_LEVELS="21 18 16 14 12 11 9 6 3 0" \
  CYCLE_TOP_STRESS=22 \
  bash run_load_unload.sh > cycle.log 2>&1 < /dev/null & disown

# one branch only (e.g. unloading from an existing loaded state)
nohup setsid env SWEEP_TAG="run01" \
  SWEEP_LEVELS="18 16 14 12 11 9 6 3 0" \
  SWEEP_INIT_STRESS=20 SWEEP_INIT_LABEL="load20" SWEEP_FRESH_START=0 \
  bash run_stress_sweep.sh > unload.log 2>&1 < /dev/null & disown
```

| variable | meaning |
|---|---|
| `SWEEP_TAG` | prefix for job names and output logs; lets several sweeps run at once |
| `CYCLE_LOAD_LEVELS` / `CYCLE_UNLOAD_LEVELS` | stress levels per branch (decimals allowed) |
| `CYCLE_TOP_STRESS` | the loading level the unload branch chains from |
| `SWEEP_FRESH_START` | `1` starts from austenite, `0` chains from a previous state |
| `SWEEP_INIT_LABEL` | which existing output to chain from |

**Run each design point in its own directory.** The stress and the input path
are edited into the sources in place, so two sweeps in one directory will
corrupt each other. Copy the tree per design point and give each a distinct
`SWEEP_TAG`.

Progress:

```bash
grep -a "Output files verified\|ERROR" cycle.log
squeue -u $USER
```

To stop a chain — note that `pkill -f run_stress_sweep.sh` matches *your own
command line* and kills the shell running it:

```bash
ps -eo pid,args --no-headers \
  | awk '$2=="bash" && $3=="run_stress_sweep.sh" {print $1}' | xargs -r kill
scancel -u $USER
```

---

## Concentration modulation fields

A sinusoidal Ni modulation along +y:

```
c(y) = avg/100 + (amp/100) * sin(2*pi*y / lambda)
```

`make_cm.py` writes it on a fixed box. `make_cm_set2_periodic.py` instead sizes
each box so it holds a whole number of periods.

### Periodicity — why the second generator exists

The solver is spectral, so the box is periodic: the last plane wraps onto the
first. If the box does not contain an integer number of modulation periods:

* the realized mean composition drifts away from the `avg` you asked for —
  by up to +0.43 at% in one case we measured, which for NiTi is a large shift
  in transformation temperature; and
* a composition step appears at the wrap plane, recurring at exactly the same
  location every box length.

Neither relaxes away if the composition field is static. Sizing the box to the
period removes both: our check reports a seam discontinuity of `0.00e+00` and a
mean offset at machine precision.

The rule used, with a 5 nm cell:

```
lambda_cells = lambda_nm / cell_nm
128 <= lambda_cells <= 256  ->  1 period,  box = lambda_cells
lambda_cells < 128          ->  n periods, n chosen so n*lambda_cells is
                                closest to 128
```

Note this makes the box size vary between design points, which changes the
per-step cost a lot — a 256³ box is 8× the cells of 128³. Set walltimes
accordingly.

---

## Choosing stress levels

Forward and reverse transformations in these simulations are **sharp**. Across
ten design points sampled at 10 MPa, every one lost 55–72 % of its martensite
volume fraction inside a single 10 MPa step. Sampling at 50 MPa steps over the
transformation therefore produces a straight line across a near-vertical drop,
and any loop area computed from it is a lower bound rather than a measurement.

Sampling uniformly at 10 MPa across the whole range is not affordable — it
would be thousands of jobs per design point. Two passes works:

1. **Scout** at 100 MPa spacing across the full range to locate each design
   point's forward and reverse windows (~28 steps per point).
2. **Target**: a 50 MPa backbone plus 10 MPa spacing across each point's *own*
   measured windows (~75 steps per point).

`launch_set2_scout.sh` and `launch_set1_x3.sh` are worked examples of the two
passes. Offset the unloading levels half a step from the loading ones so the
two branches sample different stresses and the loop reads at double
resolution.

---

## Configuration

Nothing here reads a config file by default — the sweep driver takes its
settings inline per run (so two sweeps can differ), and the analysis scripts
read three environment variables. For convenience a `.env.example` is
provided:

```bash
cp .env.example .env     # then edit
set -a; source .env; set +a
python3 analysis/plot_set1.py
```

| variable | used by | meaning |
|---|---|---|
| `SIM_DIR` | analysis | directory holding `set1_results.csv` and `set1_summary.csv` |
| `OUT_NAME` | `make_cm_excel.py` | workbook filename to write |
| `FIG_SUFFIX` | analysis | suffix on figure filenames, so several sweeps can coexist |

`.env` is gitignored. There are no credentials in it — the cluster connection
is handled separately (below).

---

## Driving this from Claude Code (optional)

The sweeps in this project were run through [pfmcp](https://github.com/aumsuthar/pfmcp),
a set of MCP servers that give Claude Code direct SSH/SLURM access to the
cluster. It is not required — every script here runs perfectly well from a
normal shell on the login node — but it is how the workflow was actually
operated, and it is what makes unattended multi-day sweeps practical to
supervise.

Setup, from pfmcp's own README:

```bash
git clone https://github.com/aumsuthar/pfmcp
cd pfmcp

# pf-sim (TypeScript) — the SSH/SLURM server, the one this toolkit needs
cd pf-sim && npm install && npm run build
cp .env.example .env          # fill in SLURM_HOST / SLURM_USERNAME / SLURM_PASSWORD
cd ..

# the Python servers (analysis/visualisation; optional for this toolkit)
for s in pf-core pf-data pf-analysis pf-viz; do
  python3 -m venv $s/.venv
  $s/.venv/bin/pip install -e $s
done
```

Register the servers (use absolute paths):

```bash
claude mcp add pf-sim      -s user -- node --env-file=/ABS/pfmcp/pf-sim/.env /ABS/pfmcp/pf-sim/dist/index.js
claude mcp add pf-data     -s user -- /ABS/pfmcp/pf-data/.venv/bin/pf-data
claude mcp add pf-analysis -s user -- /ABS/pfmcp/pf-analysis/.venv/bin/pf-analysis
claude mcp add pf-viz      -s user -- /ABS/pfmcp/pf-viz/.venv/bin/pf-viz
```

Restart Claude Code and the `mcp__pf-sim__*` tools appear. `pf-sim` is the only
one this toolkit depends on; it provides `slurm_run`, `slurm_submit_job`,
`slurm_upload_file`, `slurm_download_file` and friends.

Note the two `.env` files are different things and easy to confuse:

* **`pfmcp/pf-sim/.env`** — cluster credentials (`SLURM_HOST`,
  `SLURM_USERNAME`, `SLURM_PASSWORD`). Never commit this one.
* **`pf-sweep-toolkit/.env`** — local paths for the analysis scripts. No
  secrets.

---

## Analysis

```bash
python3 analysis/plot_set1.py            # hysteresis loops + comparison figures
python3 analysis/make_cm_excel.py set1   # workbook with renders, figures, raw data
```

Both read a results CSV of one row per step
(`cm, lambda_nm, amp, avg, branch, label, stress_mpa, strain, vf, v1..v4`),
extracted from the per-step logs. Paths are set by the `SIM_DIR`, `OUT_NAME`
and `FIG_SUFFIX` environment variables — see the top of each script.

---

## Read docs/PITFALLS.md before you change anything

Condensed, because each of these cost a run or a day:

* **A failed run can report success.** The simulation calls `exit(0)` on its
  error paths, so SLURM records COMPLETED / exit 0 for a job that did nothing.
  Never trust job state — `run_stress_sweep.sh` verifies the expected output
  files exist after every job and aborts the chain if they do not.
* **Broken chaining is silent.** If the state-input lines are left commented,
  every step restarts from austenite and the loading curve has no hysteresis.
  The signature is `vf = 0` on unloading with a perfectly linear
  strain-vs-stress line through the origin. The script uncomments them and then
  greps to confirm, aborting if the edit did not take.
* **VTK header lines must stay under 39 characters.** The reader skips the
  header with `fgets(buf, 40, fp)`; a longer line is split across two reads and
  the dimension parse then picks up stack garbage, reporting an absurd size.
* **Never edit a sweep script while it is running.** bash reads scripts
  incrementally by byte offset, so an edit makes a live instance resume at a
  shifted offset and execute nonsense.
* **A directory copied at some point keeps that version of the scripts.** A
  stale copy silently falls back to its own hardcoded defaults, which looks
  exactly like a successful launch. Check the levels the log reports, not the
  submission.

---

## Scope

Deliberately **not** included:

* **The phase-field simulation itself.** This toolkit drives it; it is not it.
  The scripts assume a `Makefile` producing a binary, a compile-time stress
  `#define`, and VTK input/output in the documented layout.
* **Any experimental or model data.** The sweeps in this project were driven by
  a collaborator's dataset which is not ours to redistribute.

Both are referenced by path and read at runtime, so the toolkit is usable with
your own copies of each.
