#!/usr/bin/env python3
"""Prépare et fusionne des datasets YOLO en un dataset unique normalisé.

Sources acceptées (une ou plusieurs, à lister dans --sources) :
  - datasets téléchargés depuis Roboflow Universe (format YOLOv8 : images/ + labels/)
  - vos propres photos annotées (même format)
  - le dataset synthétique (training/generate_virtual_dataset.py)

Le script :
  1. collecte les images/labels de chaque source
  2. remappe les classes de chaque source vers vos classes finales (--classes)
  3. gère les doublons de noms de fichiers (préfixe par source)
  4. divise en train/val (--val-split)
  5. écrit le dataset final + un fichier data.yaml prêt pour l'entraînement

Exemples :
  # fusion de deux datasets Roboflow avec une classe unique "toy"
  python training/prepare_dataset.py \
      --sources ../datasets/roboflow_tips ../datasets/roboflow_kidtoys \
      --class-map ../datasets/roboflow_tips/data.yaml:*:toy \
      --class-map ../datasets/roboflow_kidtoys/data.yaml:*:toy \
      --out ../datasets/toys_merged

  # avec le dataset synthétique
  python training/prepare_dataset.py \
      --sources datasets/toys_virtual \
      --class-map datasets/toys_virtual/labels.txt:0=teddy,1=cube,2=car \
      --out datasets/toys_virtual_ready --val-split 0.2
"""
import argparse
import random
import shutil
import sys
from pathlib import Path

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def find_images(root: Path) -> list:
    return sorted(
        p for p in root.rglob("*") if p.suffix.lower() in IMG_EXTS
    )


def find_labels_for(img: Path, roots: list) -> Path | None:
    stem = img.stem
    for root in roots:
        cand = root / f"{stem}.txt"
        if cand.exists():
            return cand
        cand = root / img.parent.name / f"{stem}.txt"
        if cand.exists():
            return cand
    return None


def parse_class_map(spec: str) -> tuple:
    """Formats acceptés :
       chemin/vers/data.yaml:0=teddy,1=cube,2=car   (mapping explicite)
       chemin/vers/data.yaml:*:toy                   (toutes classes -> toy)
    """
    if ":" not in spec:
        raise ValueError(f"--class-map invalide (attendu fichier:mapping) : {spec}")
    path, _, mapping = spec.partition(":")
    src_names = {}
    yaml_path = Path(path)
    if yaml_path.suffix in (".yaml", ".yml") and yaml_path.exists():
        src_names = read_yaml_names(yaml_path)
    elif yaml_path.exists():  # labels.txt : un nom par ligne
        src_names = {
            i: l.strip() for i, l in enumerate(yaml_path.read_text().splitlines()) if l.strip()
        }
    if mapping.strip() == "*":
        return src_names, lambda idx, name: None  # -> toutes vers classe unique (gérée plus haut)
    explicit = {}
    for part in mapping.split(","):
        left, _, target = part.partition("=")
        left = left.strip()
        target = target.strip()
        if left.isdigit():
            explicit[int(left)] = target
        else:
            matches = [t for t in target for _ in [0]]
            explicit[left] = target
    def mapper(idx, name):
        if idx in explicit:
            return explicit[idx]
        if name in explicit:
            return explicit[name]
        return None
    return src_names, mapper


def read_yaml_names(yaml_path: Path) -> dict:
    """Lit la section names d'un data.yaml Roboflow/YOLO (sans PyYAML)."""
    names = {}
    inside = False
    for line in yaml_path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith("names:"):
            rest = s[len("names:"):].strip()
            if rest.startswith("["):
                for i, n in enumerate(rest.strip("[]").split(",")):
                    names[i] = n.strip().strip("'\"")
            inside = not rest
            continue
        if inside and s and s[0].isdigit():
            num, _, val = s.partition(":")
            names[int(num.strip())] = val.strip().strip("'\"")
            continue
        if inside and (s.startswith("- ") or line.startswith("  ") and s.startswith("- ")):
            names[len(names)] = s[2:].strip().strip("'\"")
    return names


def remap_label_file(label_path: Path, mapper, final_classes: list, unify: str | None) -> list:
    """Retourne les lignes remappées, ou None-lignes filtrées (classe inconnue)."""
    out = []
    text = label_path.read_text(encoding="utf-8", errors="replace") if label_path.exists() else ""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            idx = int(float(parts[0]))
        except ValueError:
            continue
        if unify is not None:
            target = unify
        else:
            target = mapper(idx, None)
        if target not in final_classes:
            continue
        parts[0] = str(final_classes.index(target))
        out.append(" ".join(parts))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", nargs="+", required=True, help="dossiers sources (format YOLO images+labels)")
    ap.add_argument("--out", required=True, help="dossier de sortie du dataset fusionné")
    ap.add_argument("--classes", required=True, help="classes finales, séparées par des virgules : toy  ou  teddy,cube,car")
    ap.add_argument("--class-map", action="append", default=[],
                    help="mapping par source : 'chemin/data.yaml:0=toy,1=toy' ou 'chemin/labels.txt:*:toy'")
    ap.add_argument("--val-split", type=float, default=0.2, help="fraction d'images pour la validation (défaut 0.2)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    final_classes = [c.strip() for c in args.classes.split(",") if c.strip()]
    out = Path(args.out)
    (out / "images" / "train").mkdir(parents=True, exist_ok=True)
    (out / "images" / "val").mkdir(parents=True, exist_ok=True)
    (out / "labels" / "train").mkdir(parents=True, exist_ok=True)
    (out / "labels" / "val").mkdir(parents=True, exist_ok=True)

    maps = []
    for spec in args.class_map:
        maps.append(parse_class_map(spec))

    rng = random.Random(args.seed)
    all_items = []  # (image_path, [lignes remappées])

    for si, src in enumerate(args.sources):
        src = Path(src)
        imgs = find_images(src / "images") if (src / "images").exists() else find_images(src)
        label_roots = [
            src / "labels",
            src / "images",
            src,
            src / "train" / "labels",
            src / "valid" / "labels",
        ] + [p for p in src.rglob("labels")]
        src_map = maps[si] if si < len(maps) else ({}, None)
        unify = None
        if len(args.class_map) > si and args.class_map[si].endswith(":*:" + final_classes[0]) and len(final_classes) == 1:
            unify = final_classes[0]
        for img in imgs:
            if "labels" in img.parts:
                continue
            label = find_labels_for(img, label_roots)
            lines = remap_label_file(label, src_map[1], final_classes, unify)
            all_items.append((f"src{si}_{img.name}", img, lines))

    rng.shuffle(all_items)
    n_val = int(len(all_items) * args.val_split)
    counts = {"train": 0, "val": 0}
    dropped = 0
    for i, (name, img, lines) in enumerate(all_items):
        split = "val" if i < n_val else "train"
        if not lines:
            dropped += 1
            continue
        shutil.copy2(img, out / "images" / split / name)
        (out / "labels" / split / f"{Path(name).stem}.txt").write_text("\n".join(lines) + "\n")
        counts[split] += 1

    yaml_text = (
        f"path: {out.resolve()}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(final_classes))
    )
    (out / "data.yaml").write_text(yaml_text)

    print(f"Dataset fusionné : {out}")
    print(f"  train : {counts['train']} images")
    print(f"  val   : {counts['val']} images")
    if dropped:
        print(f"  ({dropped} images sans labels valides ignorées)")
    print(f"  classes : {final_classes}")
    print(f"\nPrêt pour l'entraînement :")
    print(f"  python training/train_yolo.py --data {out / 'data.yaml'} --epochs 100")
    return 0


if __name__ == "__main__":
    sys.exit(main())
