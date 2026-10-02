#!/usr/bin/env python3
"""CLI du package : lance la simulation virtuelle (identique à sim/run_virtual_demo.py)."""
import argparse
import sys

from ..core import (
    SimConfig,
    ToySorterFSM,
    VirtualManipulation,
    VirtualNavigation,
    VirtualPerception,
    VirtualWorld,
)


def main(args=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--toys", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(args)

    world = VirtualWorld(config=SimConfig(n_toys=args.toys, seed=args.seed))
    fsm = ToySorterFSM(
        perception=VirtualPerception(world),
        navigation=VirtualNavigation(world),
        manipulation=VirtualManipulation(world),
        bin_pos_getter=lambda: world.bin.pos,
    )
    fsm.run()
    remaining = world.remaining_toys()
    print(f"Jouets restants : {remaining}")
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
