#!/usr/bin/env python3
"""Simulation bout-en-bout : le robot virtuel range tous les jouets dans le bac.

Usage :
    python3 sim/run_virtual_demo.py [--toys 8] [--seed 7] [--quiet]
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ros2_ws", "src", "toy_sorter"))

from toysorter import (
    SimConfig,
    ToySorterFSM,
    VirtualManipulation,
    VirtualNavigation,
    VirtualPerception,
    VirtualWorld,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--toys", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    logs = [] if args.quiet else None
    log = (lambda msg: logs.append(msg)) if args.quiet else print

    config = SimConfig(n_toys=args.toys, seed=args.seed)
    world = VirtualWorld(config=config)

    fsm = ToySorterFSM(
        perception=VirtualPerception(world),
        navigation=VirtualNavigation(world),
        manipulation=VirtualManipulation(world),
        bin_pos_getter=lambda: world.bin.pos,
        log=log,
    )

    ok = fsm.run()

    remaining = world.remaining_toys()
    stats = fsm.stats
    if not args.quiet or not ok or remaining > 0:
        print(f"Durée simulée : {stats['elapsed_s']}s")
        print(f"Jouets rangés   : {stats['toys_ranged']}/{args.toys}")
        print(f"Grasps tentés   : {stats['grasp_attempts']}")
        print(f"Grasps ratés   : {stats['grasp_failures']}")
        print(f"Jouets restants: {remaining}")
        if logs:
            print("\n".join(logs))

    if remaining != 0 or not ok:
        sys.exit(1)
    print("SUCCÈS : tous les jouets sont rangés.")


if __name__ == "__main__":
    main()
