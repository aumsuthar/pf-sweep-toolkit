"""
set2 CM fields on integer-period cubic boxes.

The cell is fixed at 5 nm. Each box is sized so it holds a whole number of
modulation periods, removing the partial-wave problem (mean offset + a
composition step at the periodic seam) that set1's fixed 640 nm box had:

    lambda_cells = lambda_nm / 5
    128 <= lambda_cells <= 256 -> 1 period,  box = lambda_cells
    lambda_cells < 128         -> n periods, n chosen so n*lambda_cells is
                                  closest to 128

Box is cubic: box x box x box.
Header lines stay under 39 chars (io.c reads them with fgets(buf,40)).
"""
import csv, math
from pathlib import Path
import numpy as np

BASE = Path(__file__).resolve().parent
OUT = BASE / "set2_CM_periodic" / "fields"
OUT.mkdir(parents=True, exist_ok=True)
NM_PER_CELL = 5.0

def box_for(lam_nm):
    c = int(round(lam_nm / NM_PER_CELL))
    n = 1 if 128 <= c <= 256 else max(1, round(128 / c))
    return c, n, n * c

def write_vtk(prof, n, path, comment):
    hdr = ("# vtk DataFile Version 3.0\n" f"{comment}\n" "ASCII\n"
           "DATASET STRUCTURED_POINTS\n" f"DIMENSIONS {n} {n} {n}\n"
           "ORIGIN 0 0 0\nSPACING 1 1 1\n" f"POINT_DATA {n**3}\n"
           "SCALARS volume_scalars float\nLOOKUP_TABLE default\n")
    for line in hdr.rstrip("\n").split("\n"):
        if len(line) >= 39:
            raise ValueError(f"header line {len(line)} chars: {line!r}")
    slab = "".join(("%.6f\n" % v) * n for v in prof)   # x fastest, y is the profile
    with open(path, "w") as f:
        f.write(hdr)
        for _ in range(n):
            f.write(slab)

print(f"{'pt':>3} {'lam':>6} {'cells':>6} {'per':>4} {'box':>5} {'box nm':>7} {'Mcells':>7} {'file MB':>8} {'check':>22}")
rows = list(csv.DictReader(open(BASE / "set2.csv")))
man = []
for r in rows:
    pt = int(float(r["point"])); avg = float(r["avg"]); lam = float(r["wv"]); amp = float(r["amp"])
    c, nper, n = box_for(lam)
    y = np.arange(n) * NM_PER_CELL
    prof = avg/100.0 + (amp/100.0) * np.sin(2.0*math.pi*y/lam)
    slug = f"set2_pt{pt:02d}_wv{lam:.0f}nm_amp{amp:.2f}pct_box{n}"
    p = OUT / f"{slug}.vtk"
    write_vtk(prof, n, p, f"CM set2 pt{pt:02d} box{n}")
    # periodicity check: the wrap value must equal the first sample
    wrap = avg/100.0 + (amp/100.0)*math.sin(2.0*math.pi*(n*NM_PER_CELL)/lam)
    seam = abs(wrap - prof[0]) * 100
    mean_off = prof.mean()*100 - avg
    mb = p.stat().st_size/1e6
    print(f"{pt:>3} {lam:>6.0f} {c:>6} {nper:>4} {n:>5} {n*5:>7} {n**3/1e6:>7.2f} {mb:>8.1f}"
          f"   seam {seam:.2e}  d<c> {mean_off:+.2e}")
    man.append(dict(point=pt, lambda_nm=lam, amp=amp, avg=avg, lam_cells=c,
                    periods=nper, box_cells=n, box_nm=n*5, Mcells=round(n**3/1e6,3),
                    file=p.name))
with open(BASE / "set2_CM_periodic" / "manifest.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(man[0].keys())); w.writeheader(); w.writerows(man)
tot = sum(m["Mcells"] for m in man)
print(f"\ntotal {tot:.1f} Mcells vs {10*2.097:.1f} if all 128^3  ->  {tot/(10*2.097):.2f}x compute")
