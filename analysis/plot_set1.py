"""
set1: phase-field results and the comparison against the collaborator ML predictions.

Palette is categorical slots 1/2 of the validated reference palette
(CVD dE 24.7 protan, normal-vision dE 33.6, contrast pass). ML is always blue,
SIM always orange, in every panel — colour follows the entity, not the rank.
"""
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BASE = Path(__file__).resolve().parent
import os
RES  = BASE / os.environ.get("SIM_DIR", "set1_simulation_results")
SUF  = os.environ.get("FIG_SUFFIX", "")

C_ML, C_SIM, C_INK, C_MUTED, C_GRID = "#2A78D6", "#EB6834", "#0b0b0b", "#52514e", "#e6e5e1"

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": C_MUTED, "axes.linewidth": 0.8,
    "axes.labelcolor": C_INK, "text.color": C_INK,
    "xtick.color": C_MUTED, "ytick.color": C_MUTED,
    "font.size": 9, "axes.titlesize": 10, "legend.frameon": False,
    "grid.color": C_GRID, "grid.linewidth": 0.8,
})

def caption(ax, text):
    """One plain-language line under a panel saying what it means. Text wears
    text tokens, never a series colour."""
    ax.text(0.0, -0.30, text, transform=ax.transAxes, ha="left", va="top",
            fontsize=8.2, color=C_MUTED, wrap=True, linespacing=1.45)


def recessive(ax, ygrid=True):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if ygrid:
        ax.set_axisbelow(True)
        ax.yaxis.grid(True)
        ax.xaxis.grid(False)

# ── data ──────────────────────────────────────────────────────────────────────
runs = defaultdict(lambda: defaultdict(list))
meta = {}
for r in csv.DictReader(open(RES / "set1_results.csv")):
    br = "load" if r["branch"].startswith("load") else "unload"
    runs[r["cm"]][br].append((float(r["stress_mpa"]), float(r["strain"]), float(r["vf"])))
    meta[r["cm"]] = (r["lambda_nm"], r["amp"], r["avg"])
summ = {int(r["point"]): r for r in csv.DictReader(open(RES / "set1_summary.csv"))}
ml   = {int(float(r["point"])): r for r in csv.DictReader(open(BASE / "Semester_2" / "set1.csv"))}
pts  = sorted(summ)

# ── figure 1: the hysteresis loops ────────────────────────────────────────────
fig, axes = plt.subplots(2, 5, figsize=(19, 7.4), sharex=True, sharey=True)
fig.suptitle("Set 1 — simulated superelastic cycles (128³, 640 nm box)",
             fontsize=14, fontweight="bold", y=0.985)
for ax, p in zip(axes.ravel(), pts):
    cm = f"s1p{p:02d}"
    lam, amp, avg = meta[cm]
    top = float(summ[p]["sim_top_MPa"])
    L = sorted(q for q in runs[cm]["load"] if q[0] <= top)
    U = sorted(runs[cm]["unload"])
    ax.plot([q[1] * 100 for q in L], [q[0] for q in L], "-o", color=C_ML,
            lw=1.8, ms=4.5, label="loading")
    ax.plot([q[1] * 100 for q in U], [q[0] for q in U], "-o", color=C_SIM,
            lw=1.8, ms=4.5, label="unloading")
    ax.set_title(f"p{p}  λ={lam} nm  amp ±{amp}%\n⟨c⟩ {avg}%  ·  loop {summ[p]['sim_loop_area']}",
                 fontsize=8.5, color=C_INK)
    recessive(ax)
    if p == 1:
        ax.legend(loc="lower right", fontsize=8)
for ax in axes[-1]:
    ax.set_xlabel("strain (%)")
for ax in axes[:, 0]:
    ax.set_ylabel("applied stress (MPa)")
fig.tight_layout(rect=(0, 0, 1, 0.96))
fig.savefig(BASE / f"set1_hysteresis_loops{SUF}.png", dpi=200)
plt.close(fig)
print(f"saved set1_hysteresis_loops{SUF}.png")

# ── figure 2: ML vs SIM comparison ────────────────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(13.5, 11.6))
fig.suptitle("Set 1 — ML prediction vs phase field",
             fontsize=14, fontweight="bold", y=0.98)

CAPS = {
 "V1": ("Stress at which martensite reverts on unloading (vf crosses 0.5).\n"
        "The ML line is essentially flat — it predicts 1380-1421 MPa for every\n"
        "design point. The phase field spans 288-662 MPa, a 2.3x range. The model\n"
        "shows almost no sensitivity to wavelength or amplitude here."),
 "V3": ("Stress at which martensite forms on loading (vf crosses 0.5).\n"
        "Same picture: ML sits at 1744-1750 MPa for all ten (0.1% variation),\n"
        "while the phase field spans 540-1035 MPa. Both ML columns behave like\n"
        "constants, so they may not be per-design-point predictions at all."),
}
for ax, (mk, sk, name, key) in zip(axes[0],
        [("V1_stress", "sim_V1", "V1  (reverse / lower plateau)", "V1"),
         ("V3_stress", "sim_V3", "V3  (forward / upper plateau)", "V3")]):
    ax.plot(pts, [float(ml[p][mk]) for p in pts], "-o", color=C_ML, lw=1.8, ms=8, label="ML")
    ax.plot(pts, [float(summ[p][sk]) for p in pts], "-o", color=C_SIM, lw=1.8, ms=8, label="phase field")
    ax.set_title(name); ax.set_xlabel("design point"); ax.set_ylabel("stress (MPa)")
    ax.set_xticks(pts); ax.set_ylim(0, 1900); recessive(ax); ax.legend(loc="center right")
    caption(ax, CAPS[key])

ax = axes[1][0]
x = np.array([float(ml[p]["strain_range"]) for p in pts])
y = np.array([float(summ[p]["sim_strain_rng_at1100"]) for p in pts])
m, b = np.polyfit(x, y, 1)
r2 = np.corrcoef(x, y)[0, 1] ** 2
xs = np.linspace(x.min() - .01, x.max() + .01, 50)
ax.plot(xs, m * xs + b, "-", color=C_MUTED, lw=1.2, zorder=1)
ax.scatter(x, y, s=70, color=C_SIM, zorder=2, edgecolor="white", linewidth=.8)
for p, xi, yi in zip(pts, x, y):
    ax.annotate(f"p{p}", (xi, yi), textcoords="offset points", xytext=(6, -3),
                fontsize=7.5, color=C_MUTED)
ax.set_title(f"Strain range  (R² = {r2:.3f}, offset ≈ {np.mean(y - x):+.2f} pp)")
ax.set_xlabel("ML strain range (%)"); ax.set_ylabel("phase-field strain range at 1100 MPa (%)")
recessive(ax)
caption(ax, "Each dot is one design point; the line is the least-squares fit.\n"
            "Compared at a COMMON 1100 MPa. Strain range grows with how hard you\n"
            "load, and p2's cycle runs to 1300 MPa, so cycle-top values are not an\n"
            "equal comparison — on that basis R2 collapses to 0.005.\n"
            "Even on a fair basis the relationship is weak. The ML places all ten\n"
            "points inside 0.10 pp and the phase field inside 0.13 pp, so this is\n"
            "largely noise against noise. An earlier R2 of 0.99 came from p1 and p2\n"
            "sitting apart as outliers; both were flawed runs, and re-running them\n"
            "moved both into the cluster.")

ax = axes[1][1]
ratio = [float(summ[p]["sim_loop_area"]) and float(ml[p]["loop_area"]) / float(summ[p]["sim_loop_area"]) for p in pts]
ax.bar([str(p) for p in pts], ratio, color="#7A7A75", width=.62)
ax.axhline(np.mean(ratio), color=C_MUTED, ls="--", lw=1.1)
ax.annotate(f"mean {np.mean(ratio):.0f}×", (0.02, np.mean(ratio)), xycoords=("axes fraction", "data"),
            fontsize=8, color=C_MUTED, va="bottom")
ax.set_title(f"Loop area ML ÷ SIM  (spread {max(ratio)/min(ratio):.1f}× — not a pure units gap)")
ax.set_xlabel("design point"); ax.set_ylabel("ML ÷ SIM")
recessive(ax)
caption(ax, "ML and phase-field loop areas differ by ~78x, so they cannot share an\n"
            "axis; this is their ratio instead. If the gap were purely units or\n"
            "normalisation, every bar would be the same height and the dashed mean\n"
            "would pass through all of them. The 4x spread (34x to 140x) is real\n"
            "disagreement on top of whatever the scale difference is.")

fig.tight_layout(rect=(0, 0, 1, 0.962), h_pad=7.5, w_pad=3.0)
fig.savefig(BASE / f"set1_ml_vs_sim{SUF}.png", dpi=200)
plt.close(fig)
print(f"saved set1_ml_vs_sim{SUF}.png")
