"""
CM (Concentration Modulation) field builder + ParaView renderer.

For every design point (row) of a sweep CSV with columns
    point, avg, wv, amp, ...
build the Ni concentration field

    c(x, y, z) = avg/100 + (amp/100) * sin(2*pi*y / wv)

on a 640 nm cubic domain (128^3, 5 nm/voxel) and write it as a legacy ASCII
STRUCTURED_POINTS .vtk byte-compatible with the MATLAB-generated sele*.vtk
inputs the NiTi phase-field runs read (scalar "volume_scalars", Ni as a
fraction, SPACING 1 1 1, x fastest, modulation along +y).

Writes, per CSV, into <csv_stem>_CM/ :
    fields/<pointNN>_...vtk    the CM field (legacy ASCII, ~19 MB each)
    renders/<pointNN>_...png   ParaView surface render, iso camera
    manifest.csv               parameters + realized field statistics

Run through the ParaView MCP (pv_run_script):
    exec(open(".../make_cm.py").read()); run_csv(".../set1.csv")
"""

import csv
import math
import os

import numpy as np
from paraview.simple import *  # noqa: F401,F403

GRID_N       = 128     # points per side (matches constants.h L/M/N)
DOMAIN_NM    = 640.0   # physical box edge
NM_PER_VOXEL = DOMAIN_NM / GRID_N        # 5 nm
SPACING      = 1.0     # grid units in the .vtk header, as in sele*.vtk
ARRAY_NAME   = "volume_scalars"
IMG_W, IMG_H = 1400, 1200


# ── field construction ────────────────────────────────────────────────────────
def cm_profile(avg_pct, wv_nm, amp_pct, n=GRID_N):
    """Sine concentration modulation along +y, as Ni fractions."""
    y_nm = np.arange(n) * NM_PER_VOXEL
    return avg_pct / 100.0 + (amp_pct / 100.0) * np.sin(2.0 * math.pi * y_nm / wv_nm)


# io.c reads the header with fgets(ignore,40,fp), so any header line of 39+ chars
# is split across two reads, the 4-line skip lands short, and the DIMENSIONS parse
# picks up stack garbage. Every header line must stay under this.
HDR_MAX = 39


def write_vtk(prof, path, n=GRID_N, comment="CM field"):
    """Legacy ASCII STRUCTURED_POINTS, x fastest — the field is uniform in x and z,
    so one z-slab of text is built once and repeated."""
    header = (
        "# vtk DataFile Version 3.0\n"
        f"{comment}\n"
        "ASCII\n"
        "DATASET STRUCTURED_POINTS\n"
        f"DIMENSIONS {n} {n} {n}\n"
        "ORIGIN 0 0 0\n"
        f"SPACING {SPACING:g} {SPACING:g} {SPACING:g}\n"
        f"POINT_DATA {n * n * n}\n"
        f"SCALARS {ARRAY_NAME} float\n"
        "LOOKUP_TABLE default\n"
    )
    for line in header.rstrip("\n").split("\n"):
        if len(line) >= HDR_MAX:
            raise ValueError("VTK header line is %d chars, io.c truncates at %d: %r"
                             % (len(line), HDR_MAX, line))

    slab = "".join(("%.6f\n" % v) * n for v in prof)   # one z-plane: y outer, x inner
    with open(path, "w") as fh:
        fh.write(header)
        for _ in range(n):
            fh.write(slab)


# ── rendering ─────────────────────────────────────────────────────────────────
def render(vtk_path, png_path, label):
    src = LegacyVTKReader(FileNames=[vtk_path])
    src.UpdatePipeline()
    lo, hi = src.GetPointDataInformation()[ARRAY_NAME].GetRange()

    view = GetActiveViewOrCreate("RenderView")
    view.ViewSize = [IMG_W, IMG_H]
    view.UseColorPaletteForBackground = 0
    view.Background = [1.0, 1.0, 1.0]
    view.OrientationAxesVisibility = 0

    disp = Show(src, view)
    disp.Representation = "Surface"
    ColorBy(disp, ("POINTS", ARRAY_NAME))
    lut = GetColorTransferFunction(ARRAY_NAME)
    lut.ApplyPreset("Cool to Warm", True)
    lut.RescaleTransferFunction(lo, hi)
    GetOpacityTransferFunction(ARRAY_NAME).RescaleTransferFunction(lo, hi)

    disp.SetScalarBarVisibility(view, True)
    bar = GetScalarBar(lut, view)
    bar.Title = "Ni Conc. (fraction)"
    bar.ComponentTitle = ""
    bar.TitleColor = [0.0, 0.0, 0.0]
    bar.LabelColor = [0.0, 0.0, 0.0]
    bar.TitleFontSize = 18
    bar.LabelFontSize = 14
    bar.AutomaticLabelFormat = 0
    bar.LabelFormat = "{:.4f}"      # std::format (ParaView >= 6.1)
    bar.RangeLabelFormat = "{:.4f}"
    bar.ScalarBarLength = 0.55

    txt = Text(Text=label)
    tdisp = Show(txt, view)
    tdisp.Color = [0.0, 0.0, 0.0]
    tdisp.FontSize = 24
    tdisp.WindowLocation = "Upper Left Corner"

    # iso camera with +y (the modulation axis) up, so the CM reads as stripes
    extent = (GRID_N - 1) * SPACING
    c = extent / 2.0
    d = extent * 2.2
    view.CameraFocalPoint = [c, c, c]
    view.CameraPosition = [c + 0.80 * d, c + 0.45 * d, c + 0.80 * d]
    view.CameraViewUp = [0.0, 1.0, 0.0]
    view.CameraParallelProjection = 0
    Render(view)
    SaveScreenshot(png_path, view, ImageResolution=[IMG_W, IMG_H],
                   TransparentBackground=0)

    Delete(tdisp); Delete(txt)
    Hide(src, view); Delete(disp); Delete(src)
    return lo, hi


# ── driver ────────────────────────────────────────────────────────────────────
def run_csv(csv_path, out_root=None):
    csv_path = os.path.abspath(os.path.expanduser(csv_path))
    stem = os.path.splitext(os.path.basename(csv_path))[0]
    out_dir = os.path.join(out_root or os.path.dirname(csv_path), stem + "_CM")
    f_dir = os.path.join(out_dir, "fields")
    r_dir = os.path.join(out_dir, "renders")
    os.makedirs(f_dir, exist_ok=True)
    os.makedirs(r_dir, exist_ok=True)

    with open(csv_path) as fh:
        rows = list(csv.DictReader(fh))

    manifest = []
    for row in rows:
        pt   = int(float(row["point"]))
        avg  = float(row["avg"])
        wv   = float(row["wv"])
        amp  = float(row["amp"])
        slug = "point%02d_wv%dnm_amp%.2fpct" % (pt, round(wv), amp)

        prof = cm_profile(avg, wv, amp)
        vtk = os.path.join(f_dir, slug + ".vtk")
        png = os.path.join(r_dir, slug + ".png")
        write_vtk(prof, vtk, comment="CM %s pt%02d" % (stem, pt))

        nwv   = DOMAIN_NM / wv
        label = ("%s  point %d\n<c> = %.2f%%   lambda = %g nm (%.2f waves / 640 nm)"
                 "\namp = +/-%.2f%%   c = %.3f - %.3f%%"
                 % (stem, pt, avg, wv, nwv, amp,
                    prof.min() * 100.0, prof.max() * 100.0))
        lo, hi = render(vtk, png, label)

        manifest.append(dict(
            point=pt, avg_pct=avg, wavelength_nm=wv, amp_pct=amp,
            waves_in_domain=round(nwv, 4),
            c_min_pct=round(prof.min() * 100.0, 6),
            c_max_pct=round(prof.max() * 100.0, 6),
            field_min=lo, field_max=hi,
            vtk=os.path.relpath(vtk, out_dir),
            png=os.path.relpath(png, out_dir),
        ))
        print("  point %02d  lambda=%-6g nm  amp=+/-%.2f%%  ->  %s (%.1f MB)"
              % (pt, wv, amp, slug, os.path.getsize(vtk) / 1e6))

    man_path = os.path.join(out_dir, "manifest.csv")
    with open(man_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(manifest[0].keys()))
        w.writeheader()
        w.writerows(manifest)
    print("%s: %d CM fields -> %s" % (stem, len(manifest), out_dir))
    return out_dir
