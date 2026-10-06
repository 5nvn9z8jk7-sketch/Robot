#!/usr/bin/env python3
"""Test d'inférence : applique le modèle entraîné sur une image.

Usage :
  python training/predict.py --model runs/detect/train/weights/best.pt --image balle_test.jpg

Affiche les détections (classe, confiance, bbox) dans le terminal
et sauvegarde l'image annotée dans training/predictions/.
"""
import argparse
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="chemin du best.pt entraîné")
    ap.add_argument("--image", required=True, help="image à tester (ex: balle_test.jpg)")
    ap.add_argument("--conf", type=float, default=0.25, help="seuil de confiance (défaut 0.25)")
    ap.add_argument("--device", default=None, help="cpu ou 0 (GPU) ; défaut : auto")
    args = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics non installé : pip install ultralytics", file=sys.stderr)
        return 2

    model_path = Path(args.model)
    if not model_path.exists():
        print(f"Modèle introuvable : {model_path}", file=sys.stderr)
        print("Lancez d'abord : python training/train_yolo.py --data toys.yaml", file=sys.stderr)
        return 1

    model = YOLO(str(model_path))
    kwargs = {}
    if args.device:
        kwargs["device"] = args.device
    results = model.predict(args.image, conf=args.conf, save=True, project="training/predictions", name="test", exist_ok=True, **kwargs)

    result = results[0]
    names = result.names
    print(f"\n=== Résultats pour {args.image} ===")
    if len(result.boxes) == 0:
        print("Aucune détection au-dessus du seuil.")
        return 0

    for box in result.boxes:
        cls = names[int(box.cls)]
        conf = float(box.conf)
        x1, y1, x2, y2 = [round(float(v), 1) for v in box.xyxy[0]]
        print(f"  {cls:10s}  conf={conf:.2f}  bbox=({x1},{y1})-({x2},{y2})")

    out = Path(result.save_dir) / Path(args.image).name
    print(f"\nImage annotée : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
