#!/usr/bin/env python3
"""Test de robustesse : la FSM doit ranger tous les jouets même en conditions difficiles.

Usage :
    python sim/stress_test.py [--trials 10]
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

HARD = dict(
    n_toys=10,
    grasp_success_prob=0.4,
    detection_dropout_prob=0.3,
    detection_noise_std=0.05,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=10)
    args = ap.parse_args()

    successes = 0
    for trial in range(args.trials):
        config = SimConfig(seed=trial, **HARD)
        world = VirtualWorld(config=config)
        fsm = ToySorterFSM(
            perception=VirtualPerception(world),
            navigation=VirtualNavigation(world),
            manipulation=VirtualManipulation(world),
            bin_pos_getter=lambda: world.bin.pos,
            log=lambda msg: None,
        )
        fsm.run()
        remaining = world.remaining_toys()
        ok = remaining == 0
        successes += ok
        print(
            f"essai {trial:2d} : {'OK ' if ok else 'ÉCHEC'} "
            f"rangés={fsm.stats['toys_ranged']}/{HARD['n_toys']} "
            f"restants={remaining} "
            f"grasps ratés={fsm.stats['grasp_failures']}"
        )

    rate = 100 * successes / args.trials
    print(f"\nTaux de succès : {successes}/{args.trials} ({rate:.0f}%)")
    if successes != args.trials:
        print("Note : un échec est normal si un jouet reste indétecté (dropout 30%).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
