#!/usr/bin/env python3
"""Entraînement YOLO pour la détection de jouets — à exécuter sur votre PC (GPU).

Étapes :
1. Collectez 200-500 photos réelles de jouets (training/datasets/toys/)
2. Annotsez-les sur Roboflow/Label Studio (bbox, classes: teddy/cube/car)
3. Exportez au format YOLO et créez toys.yaml (voir toys.yaml.example)
4. Lancez : python training/train_yolo.py --data toys.yaml
5. Exportez pour la Jetson :
   python training/train_yolo.py --export best.pt

Entraînement simulé (sans GPU / sans dataset, ici dans la sandbox) :
   python training/train_yolo.py --dry-run
"""
import argparse
import sys
from pathlib import Path


def dry_run():
    print("=== SIMULATION D'ENTRAÎNEMENT (dry-run) ===")
    epochs, batch, imgsz = 100, 16, 640
    for e in range(1, epochs + 1, 10):
        loss = 4.2 * (0.87 ** e)
        mAP = min(0.96, 0.30 + 0.65 * (1 - 0.90 ** e))
        print(f"epoch {e:3d}/{epochs}  box_loss={loss:.3f}  mAP50={mAP:.3f}")
    print("Résultat simulé : best.pt (mAP50=0.94)")
    print("Prochaine étape réelle : exécuter sur PC avec GPU + dataset réel.")
    print("Puis : yolo export model=best.pt format=engine half=True  (sur la Jetson)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="chemin du fichier .yaml du dataset")
    ap.add_argument("--model", default="yolov8s.pt")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--export", help="exporte un modèle .pt vers TensorRT engine")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        return dry_run()

    if args.export:
        from ultralytics import YOLO

        model = YOLO(args.export)
        engine_path = model.export(format="engine", half=True)
        print(f"Engine TensorRT généré : {engine_path}")
        return 0

    if not args.data:
        ap.error("--data est requis (fichier yaml du dataset YOLO)")

    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics non installé : pip install ultralytics", file=sys.stderr)
        return 2

    model = YOLO(args.model)
    results = model.train(data=args.data, epochs=args.epochs, imgsz=args.imgsz)
    print(f"Entraînement terminé. Meilleur modèle : {results.save_dir}/weights/best.pt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
