"""Tile a *_CM/renders/ folder into one overview sheet per CSV.

Each ParaView render is cropped to the cube itself (colour bar and the
in-image annotation are dropped) and re-captioned from manifest.csv.

Usage:  python make_cm_grid.py set1_CM set2_CM
"""
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageChops


def crop_cube(path: Path) -> np.ndarray:
    """Drop the colour bar (right edge) and header text, then trim to the cube."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    im = im.crop((0, int(h * 0.09), int(w * 0.88), h))      # cut text band + colour bar
    bg = Image.new("RGB", im.size, (255, 255, 255))
    bbox = ImageChops.difference(im, bg).getbbox()
    if bbox:
        im = im.crop(bbox)
    return np.asarray(im)


def build(cm_dir: Path):
    rows = list(csv.DictReader(open(cm_dir / "manifest.csv")))
    n = len(rows)
    ncol = 5
    nrow = (n + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(2.9 * ncol, 4.1 * nrow))
    fig.suptitle(f"Concentration Modulation (CM) — {cm_dir.name.replace('_CM', '')} "
                 f"design points   ·   640 nm box, 128³, modulation along +y",
                 fontsize=13, fontweight="bold")
    for ax, r in zip(axes.ravel(), rows):
        ax.imshow(crop_cube(cm_dir / r["png"]))
        ax.set_title(
            f'point {r["point"]}\n'
            f'λ = {float(r["wavelength_nm"]):g} nm  ({float(r["waves_in_domain"]):.2f} wv)\n'
            f'⟨c⟩ = {float(r["avg_pct"]):.2f}%   amp = ±{float(r["amp_pct"]):.2f}%\n'
            f'c = {float(r["c_min_pct"]):.2f}–{float(r["c_max_pct"]):.2f}%',
            fontsize=8, linespacing=1.35)
        ax.axis("off")
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    fig.tight_layout(rect=(0, 0, 1, 0.97), h_pad=5.0)
    out = cm_dir / f"{cm_dir.name}_grid.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    print("saved", out)


if __name__ == "__main__":
    for d in sys.argv[1:]:
        build(Path(d).resolve())
