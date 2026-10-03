#!/usr/bin/env python3
"""Génère un dataset synthétique de balles de tennis "vue robot".

Simule le point de vue de la caméra embarquée : sols variés (béton, dur,
gazon, parquet), caméra basse (~30-50 cm), balles posées au sol à
différentes distances. Produit des images + annotations YOLO (classe
unique `ball`) directement exploitables par prepare_dataset.py.

Usage :
  python training/generate_tennis_dataset.py --out ../datasets/tennis_virtual --n 300
"""

import argparse
import random
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

CLASSES = ["ball"]

# Sol : (nom, couleur de base, variance, granularité)
FLOORS = [
    ("hard_blue", (66, 102, 148), 18, 3.0),   # court dur bleu
    ("clay", (176, 96, 60), 20, 2.5),          # terre battue
    ("grass", (86, 130, 58), 22, 3.0),         # gazon
    ("concrete", (128, 128, 126), 12, 2.0),    # béton
    ("parquet", (168, 122, 82), 15, 6.0),      # parquet intérieur
    ("indoor_green", (70, 110, 90), 16, 3.0),   # moquette indoor
]

BALL_BASE = (208, 255, 62)  # jaune fluo balle de tennis


def random_bg(size, rng):
    """Sol texturé : couleur de base + bruit + lignes de sol (perspective légère)."""
    name, base, var, grain = FLOORS[rng.randrange(len(FLOORS))]
    img = Image.new("RGB", size, base)
    px = img.load()
    w, h = size
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            n = rng.randint(-var, var)
            c = tuple(max(0, min(255, base[i] + n)) for i in range(3))
            px[x, y] = c
            if x + 1 < w and y + 1 < h:
                px[x + 1, y] = c
                px[x, y + 1] = c
                px[x + 1, y + 1] = c
    draw = ImageDraw.Draw(img)
    # lignes de court / joints de sols en perspective
    horizon = h // 3
    line_color = tuple(max(0, min(255, base[i] + rng.randint(-40, 40))) for i in range(3))
    if rng.random() < 0.5:
        y_line = rng.randint(horizon, h - 40)
        draw.line([(0, y_line), (w, y_line)], fill=line_color, width=rng.randint(2, 4))
    if rng.random() < 0.4:
        # joint / ligne de fond verticale
        x_line = rng.randint(w // 4, 3 * w // 4)
        draw.line([(x_line, horizon), (x_line + rng.randint(-60, 60), h)], fill=line_color, width=3)
    # ombres diffuses
    for _ in range(rng.randint(3, 8)):
        ox, oy = rng.randint(0, w), rng.randint(0, h)
        r = rng.randint(20, 80)
        shade = tuple(max(0, base[i] - rng.randint(20, 45)) for i in range(3))
        draw.ellipse([ox - r, oy - r // 2, ox + r, oy + r // 2], fill=shade)
    return img.filter(ImageFilter.GaussianBlur(rng.uniform(0.4, 1.2)))


def draw_ball(draw, cx, cy, r, rng):
    """Balle vue de face : disque + ombre + coutures + nuance."""
    # ombre au sol
    draw.ellipse([cx - int(r * 1.15), cy - int(r * 0.25), cx + int(r * 1.15), cy + int(r * 0.55)],
                 fill=(30, 30, 30))
    shade = rng.randint(-25, 15)
    color = tuple(max(0, min(255, BALL_BASE[i] + shade)) for i in range(3))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    # coutures (courbes blanches caractéristiques)
    seam = tuple(max(0, min(255, color[i] - 60)) for i in range(3))
    lw = max(1, r // 10)
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=rng.randint(0, 90), end=rng.randint(140, 250),
             fill=seam, width=lw)
    draw.arc([cx - int(r * 0.55), cy - r, cx + int(r * 0.55), cy + r],
             start=rng.randint(180, 270), end=rng.randint(300, 380), fill=seam, width=lw)
    # reflet
    hl = rng.randint(20, 50)
    draw.ellipse([cx - r // 2, cy - r // 2, cx - r // 6, cy - r // 6],
                 fill=tuple(min(255, color[i] + hl) for i in range(3)))
    return cx - r, cy - r, cx + r, cy + r


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="training/datasets/tennis_virtual")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if not HAS_PIL:
        print("PIL non installé (pip install Pillow) : impossible de générer les images.")
        return 1

    rng = random.Random(args.seed)
    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    (out / "labels.txt").write_text("\n".join(CLASSES) + "\n")

    W, H = 640, 480
    n_empty = args.n // 8  # images sans balle (négatifs)
    for i in range(args.n):
        img = random_bg((W, H), rng)
        draw = ImageDraw.Draw(img)
        lines = []
        if i >= n_empty:
            n_balls = rng.randint(1, 3)
            for _ in range(n_balls):
                # distance simulée : balles proches grosses en bas, lointaines petites vers le milieu
                depth = rng.random()
                r = int(8 + (1 - depth) * 38)
                cy = int(H * (0.45 + 0.5 * depth)) + rng.randint(-20, 20)
                cx = rng.randint(r + 10, W - r - 10)
                x0, y0, x1, y1 = draw_ball(draw, cx, cy, r, rng)
                lines.append(f"0 {(cx / W):.6f} {(cy / H):.6f} "
                             f"{((x1 - x0) / W):.6f} {((y1 - y0) / H):.6f}")
        img.save(out / "images" / f"synth_{i:04d}.jpg", quality=rng.randint(80, 95))
        (out / "labels" / f"synth_{i:04d}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))

    print(f"Dataset synthétique : {out}")
    print(f"  {args.n} images ({n_empty} vides pour les négatifs)")
    print(f"  classes : {CLASSES}")
    print(f"\nFusion avec un dataset réel :")
    print(f"  python training/prepare_dataset.py "
          f"--sources {out} <autre_source> --class-map {out / 'labels.txt'}:*:ball --classes ball --out ...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
