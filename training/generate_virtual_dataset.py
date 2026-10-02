#!/usr/bin/env python3
"""Collecte d'un dataset virtuel : images synthétiques de jouets au sol.

Génère des images + annotations YOLO (labels.txt + fichiers .txt par image)
pour valider la chaîne d'entraînement sans données réelles. À remplacer par
vos vraies photos annotées dans training/datasets/toys/.
"""
import argparse
import os
import random
from pathlib import Path

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


CLASSES = ["teddy", "cube", "car"]
COLORS = {"teddy": (139, 69, 19), "cube": (200, 30, 30), "car": (30, 80, 200)}


def random_bg(size):
    if not HAS_PIL:
        return None, None
    img = Image.new("RGB", size, (60 + random.randint(0, 40),) * 3)
    draw = ImageDraw.Draw(img)
    for _ in range(300):
        x, y = random.randint(0, size[0]), random.randint(0, size[1])
        shade = random.randint(40, 120)
        draw.point((x, y), fill=(shade, shade, shade))
    return img, draw


def draw_toy(draw, label, cx, cy, s):
    w = {"teddy": 34, "cube": 26, "car": 44}[label]
    h = {"teddy": 40, "cube": 26, "car": 24}[label]
    color = COLORS[label]
    if label == "teddy":
        draw.ellipse([cx - w, cy - h, cx + w, cy + h], fill=color)
        draw.ellipse([cx - w - 8, cy - h - 6, cx - w + 10, cy - h + 14], fill=color)
        draw.ellipse([cx + w - 10, cy - h - 6, cx + w + 8, cy - h + 14], fill=color)
    elif label == "cube":
        draw.rectangle([cx - w, cy - h, cx + w, cy + h], fill=color)
    else:
        draw.rounded_rectangle([cx - w, cy - h, cx + w, cy + h], 6, fill=color)
    return cx - w, cy - h, cx + w, cy + h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="training/datasets/toys_virtual")
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if not HAS_PIL:
        print("PIL non installé (pip install Pillow) : génération d'images désactivée.")
        print("Génère seulement la structure YOLO pour référence.")
        out = Path(args.out)
        (out / "images").mkdir(parents=True, exist_ok=True)
        (out / "labels").mkdir(parents=True, exist_ok=True)
        (out / "labels.txt").write_text("\n".join(CLASSES) + "\n")
        return

    random.seed(args.seed)
    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    (out / "labels.txt").write_text("\n".join(CLASSES) + "\n")

    W, H = 640, 480
    for i in range(args.n):
        img, draw = random_bg((W, H))
        lines = []
        n_toys = random.randint(1, 4)
        for _ in range(n_toys):
            label = random.choice(CLASSES)
            cx, cy = random.randint(60, W - 60), random.randint(60, H - 60)
            x1, y1, x2, y2 = draw_toy(draw, label, cx, cy, 1)
            xc, yc, w, h = (x1 + x2) / 2 / W, (y1 + y2) / 2 / H, (x2 - x1) / W, (y2 - y1) / H
            lines.append(f"{CLASSES.index(label)} {xc:.5f} {yc:.5f} {w:.5f} {h:.5f}")
        img.save(out / "images" / f"img_{i:04d}.jpg")
        (out / "labels" / f"img_{i:04d}.txt").write_text("\n".join(lines) + "\n")
    print(f"{args.n} images générées dans {out}/images avec labels YOLO")


if __name__ == "__main__":
    main()
