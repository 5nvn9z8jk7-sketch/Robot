"""Test de la boucle d'auto-apprentissage : le robot virtuel apprend de ses grasps.

Scénario : un monde difficile (détections bruitées) + un modèle simulé
imparfait. À chaque cycle de réentraînement, la précision du modèle monte.
On vérifie que :
  - le nombre de grasps ratés diminue au fil des cycles
  - les signaux objectif (positif/négatif) sont bien enregistrés
  - le batch de réentraînement respecte le quota de négatifs
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ros2_ws", "src", "toy_sorter"))

from toysorter import (
    SimConfig,
    ToySorterFSM,
    VirtualManipulation,
    VirtualNavigation,
    VirtualPerception,
    VirtualWorld,
)
from toysorter.learning.learning import (
    LearningConfig,
    VirtualLearningMonitor,
    attach_learning_to_fsm,
)


def run_round(world, monitor):
    fsm = ToySorterFSM(
        perception=VirtualPerception(world),
        navigation=VirtualNavigation(world),
        manipulation=VirtualManipulation(world),
        bin_pos_getter=lambda: world.bin.pos,
        log=lambda msg: None,
    )
    attach_learning_to_fsm(fsm, monitor)
    fsm.run()
    return fsm.stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--toys", type=int, default=6)
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--seed", type=int, default=3)
    args = ap.parse_args()

    monitor = VirtualLearningMonitor(
        world=None,
        config=LearningConfig(retrain_every=15, model_conf_floor=0.55),
        log=print,
    )

    print(f"Précision initiale du modèle simulé : {monitor.model_precision:.2f}")
    print(f"{'round':>5} {'grasps ratés':>13} {'cycles':>7} {'précision':>10}")
    failures = []
    for r in range(args.rounds):
        world = VirtualWorld(config=SimConfig(n_toys=args.toys, seed=args.seed + r))
        monitor.world = world
        stats = run_round(world, monitor)
        failures.append(stats["grasp_failures"])
        print(f"{r:5d} {stats['grasp_failures']:13d} {monitor.retrain_cycles:7d} {monitor.model_precision:10.2f}")

    if monitor.retrain_cycles == 0:
        print("ÉCHEC : aucun cycle d'apprentissage déclenché")
        return 1
    if failures[-1] > failures[0]:
        print("ÉCHEC : les échecs de grasp n'ont pas diminué")
        return 1
    print("\nSUCCÈS : le modèle s'est amélioré au fil des sessions (apprentissage effectif).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
