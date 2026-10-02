# Robot — Toy Sorter (Hiwonder ROSOrin Pro)

Projet : le robot **Hiwonder ROSOrin Pro (Jetson Orin NX Super 16GB)** ramasse des jouets
au sol et les range dans un bac, de façon autonome.

Le projet est développé **virtuellement sur PC** : toute la logique (détection, navigation,
préhension, orchestration) est écrite et testée en simulation. Au reçu du robot, il suffit
de brancher les backends ROS2 réels.

## Structure

```
├── training/                    # Entraînement YOLO (à exécuter sur PC avec GPU)
│   ├── generate_virtual_dataset.py   # Dataset synthétique de test
│   ├── prepare_dataset.py            # Fusion/normalisation de datasets (publics + perso)
│   ├── train_yolo.py                 # Entraînement réel + export TensorRT
│   └── toys.yaml.example             # Format de dataset attendu
├── sim/
│   └── run_virtual_demo.py      # Simulation bout-en-bout sans robot
└── ros2_ws/src/toy_sorter/      # Package ROS2 (à installer sur le robot)
    ├── package.xml
    ├── setup.py
    ├── toysorter/
    │   ├── core/                # Types, monde virtuel, state machine
    │   ├── perception/          # Interface + backend virtuel + backend ROS2
    │   ├── navigation/          # Interface + backend virtuel + backend Nav2
    │   ├── manipulation/        # Interface + backend virtuel + backend bras
    │   └── tools/               # CLI simulation
    └── tests/                   # Tests unitaires et d'intégration
```

## Démarrage rapide (sans robot)

```bash
# 1. Tests
python3 -m pytest ros2_ws/src/toy_sorter/tests -q

# 2. Simulation complète : le robot virtuel range N jouets
python3 sim/run_virtual_demo.py --toys 8 --seed 42

# 3. Entraînement YOLO simulé (valide la chaîne, sans GPU)
python3 training/train_yolo.py --dry-run

# 4. Dataset synthétique (images + labels YOLO)
python3 training/generate_virtual_dataset.py --n 200
```

## Datasets publics annotés

Des datasets de jouets annotés existent sur [Roboflow Universe](https://universe.roboflow.com) :

- [Toy Dataset TIPS (~3000 images)](https://universe.roboflow.com/tips-wis6y/toy-dataset-bfq0d)
- [kid-toys (~1000 images)](https://universe.roboflow.com/flektest/kid-toys/dataset/16)
- [Soft-toy (peluches)](https://universe.roboflow.com/felipe-guimaraes/soft-toy/dataset/1)

Téléchargez-les au **format YOLOv8**, puis fusionnez-les avec `prepare_dataset.py` :

```bash
# Tous les jouets vers une classe unique "toy"
python training/prepare_dataset.py \
    --sources ../datasets/roboflow_tips ../datasets/roboflow_kidtoys \
    --classes toy \
    --class-map ../datasets/roboflow_tips/data.yaml:*:toy \
    --class-map ../datasets/roboflow_kidtoys/data.yaml:*:toy \
    --out ../datasets/toys_merged

# Puis entraîner
python training/train_yolo.py --data ../datasets/toys_merged/data.yaml --epochs 100
```

Stratégie recommandée : entraîner d'abord sur les datasets publics (modèle
générique), puis **fine-tuner** avec 50-100 photos de vos propres jouets —
le modèle générique peut aussi pré-annoter vos photos dans Roboflow pour
'accélérer l'annotation manuelle.

## Entraînement réel (sur votre PC, GPU recommandé)

1. Prendre **200–500 photos** de vos jouets (angles/lumières/fonds variés)
2. Annoter sur [Roboflow](https://roboflow.com) ou Label Studio (classes : `teddy`, `cube`, `car`)
3. Exporter au format YOLO, créer `training/toys.yaml` (voir `toys.yaml.example`)
4. Entraîner :
   ```bash
   pip install ultralytics
   python3 training/train_yolo.py --data toys.yaml --epochs 100
   ```
5. Exporter pour la Jetson (à faire sur le robot) :
   ```bash
   python3 training/train_yolo.py --export best.pt   # → TensorRT engine FP16
   ```

## Installation sur le robot (à la réception)

```bash
# Sur la Jetson (ROS2 Humble/Jazzy déjà installé par Hiwonder)
cd ~/ros2_ws/src
git clone <ce dépôt> Robot
cp -r Robot/ros2_ws/src/toy_sorter .
cd ~/ros2_ws
rosdep install --from-paths src --ignore-src -y
colcon build --packages-select toy_sorter
source install/setup.bash

# Simulation sur le robot (vérifie l'installation)
ros2 run toy_sorter toy_sorter_sim --toys 5
```

Puis connecter les backends réels (chaque fichier contient le pseudo-code guide) :
- `toysorter/perception/ros2_backend.py` → caméra RGB-D + YOLO TensorRT + TF
- `toysorter/navigation/ros2_backend.py` → Nav2 `NavigateToPose`
- `toysorter/manipulation/ros2_backend.py` → SDK bras Hiwonder

## Auto-apprentissage : le robot s'améliore de son expérience

Le module `toysorter/learning/` implémente une boucle d'apprentissage continu :

```
[Robot range les jouets] → détections incertaines collectées
        ↓
Grasp réussi → positif confirmé    Grasp raté (cible sûre) → négatif confirmé
        ↓
Buffer d'expériences → réentraînement périodique → modèle déployé mis à jour
```

- **Collecte ciblée** : seules les détections *incertaines* sont apprises (les
  cas sûrs n'apportent rien, les cas trop faibles sont du bruit)
- **Signaux objectifs** : le succès/échec du grasp sert de label — aucune
  annotation humaine nécessaire pour les cas courants
- **Pseudo-labels** : une observation proche et sûre corrige une observation
  douteuse de la même cible
- **Garde-fous** : quota de négatifs par batch pour éviter le collapse du modèle

En simulation :

```bash
python3 sim/learning_demo.py
# → les échecs de grasp diminuent round après round
```

Sur le robot : le backend perception réelle (`ros2_backend.py`) enverra ses
frames au même `LearningMonitor` ; le réentraînement s'effectuera sur votre PC
GPU (fine-tuning de `best.pt`, ~5 min par cycle) puis le modèle sera recopié
sur la Jetson.

## Architecture

```
Perception (YOLO + profondeur) → cible 3D
        ↓
FSM : SEARCHING → NAV_TO_TOY → GRASPING → LIFTING → NAV_TO_BIN → PLACING ↺
        ↓
Navigation (Nav2)      Manipulation (bras + pince)
```

- Les **interfaces** (`PerceptionBackend`, `NavigationBackend`, `ManipulationBackend`)
  sont communes aux deux mondes.
- Les **backends virtuels** simulent bruit de détection, dropout, échecs de grasp.
- Les **backends ROS2** s'activent sur le robot sans changer la FSM.
- La FSM gère les retries (max 3 par jouet) et repasse en recherche après abandon.
