"""Démo simulation : le robot virtuel balaie le terrain et ramasse les balles.

Usage :
    python sim/tennis_demo.py [--balls 12] [--small] [--seed 3]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ros2_ws", "src", "toy_sorter"))

from toysorter import VirtualManipulation, VirtualNavigation, VirtualPerception
from toysorter.tennis import TennisSweeperFSM, TennisWorld, TennisWorldConfig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--balls", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--small", action="store_true", help="terrain réduit pour démo rapide")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    logs = [] if args.quiet else None
    log = (lambda m: logs.append(m)) if args.quiet else print

    config = TennisWorldConfig(
        n_balls=args.balls,
        seed=args.seed,
        width=4.0 if args.small else 11.0,
        height=6.0 if args.small else 24.0,
    )
    world = TennisWorld(config=config)

    from toysorter.core.types import GraspResult

    class BasketManipulation2(VirtualManipulation):
        def grasp(self, target):
            ok, ball = self.world.attempt_grasp(target)
            if ok:
                self.world.release_in_bin()
            return GraspResult(success=ok, message="ball scooped" if ok else "missed")

    fsm = TennisSweeperFSM(
        perception=VirtualPerception(world),
        navigation=VirtualNavigation(world),
        manipulation=BasketManipulation2(world),
        world=world,
        log=log,
    )
    ok = fsm.run()

    remaining = world.remaining_balls()
    print(f"Balles collectées : {fsm.stats['balls_collected']}/{args.balls}")
    print(f"Grasps tentés/ratés : {fsm.stats['grasp_attempts']}/{fsm.stats['grasp_failures']}")
    print(f"Lignes balayées : {fsm.stats['lines_swept']}")
    if remaining:
        print(f"Balles restantes : {remaining} (dropout de détection simulé)")
    if logs:
        print("\n".join(logs[-5:]))
    if fsm.stats["balls_collected"] == 0:
        sys.exit(1)
    print("SUCCÈS : le robot a balayé le terrain et rempli son panier.")


if __name__ == "__main__":
    main()
