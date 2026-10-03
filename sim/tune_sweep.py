"""Optimisation par simulation : compare des configurations et mesure l'efficacité.

Mesure la distance parcourue et les grasps tentés pour différentes valeurs de
paramètres (largeur de ligne de balayage, taux d'échec du grasp, bruit de
détection). Permet de choisir les réglages les plus efficaces AVANT de les
tester sur le robot réel.

Usage :
    python sim/tune_sweep.py [--balls 15] [--trials 5]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ros2_ws", "src", "toy_sorter"))

from toysorter import VirtualManipulation, VirtualNavigation, VirtualPerception
from toysorter.core.types import GraspResult
from toysorter.tennis import TennisSweeperFSM, TennisWorld, TennisWorldConfig

STEP_METERS = 0.3


class CountingWorld(TennisWorld):
    """Compte la distance parcourue par le robot (nombre de pas de drive_to)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.drive_steps = 0

    def drive_to(self, target, tol=0.05):
        before = (self.robot_pos.x, self.robot_pos.y)
        done = super().drive_to(target, tol=tol)
        moved = ((self.robot_pos.x - before[0]) ** 2 + (self.robot_pos.y - before[1]) ** 2) ** 0.5
        if moved > 1e-9:
            self.drive_steps += 1
        return done


def run_one(line_width, config, quiet=True):
    world = CountingWorld(config=config)
    fsm = TennisSweeperFSM(
        perception=VirtualPerception(world),
        navigation=VirtualNavigation(world),
        manipulation=VirtualManipulation(world),
        world=world,
        log=(lambda m: None) if quiet else print,
    )
    fsm.LINE_WIDTH = line_width
    # BasketManipulation : stocke la balle dans le panier embarqué après le grasp
    orig_manip = fsm.manipulation
    class BasketManipulation(type(orig_manip)):
        def grasp(self, target):
            ok, _ = self.world.attempt_grasp(target)
            if ok:
                self.world.release_in_bin()
            return GraspResult(success=ok)
    fsm.manipulation = BasketManipulation(world)
    fsm.run()
    return {
        "collected": fsm.stats["balls_collected"],
        "total": config.n_balls,
        "attempts": fsm.stats["grasp_attempts"],
        "distance_m": round(world.drive_steps * STEP_METERS, 1),
        "lines": fsm.stats["lines_swept"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--balls", type=int, default=15)
    ap.add_argument("--trials", type=int, default=3, help="essais par configuration (seeds différents)")
    args = ap.parse_args()

    line_widths = [0.6, 0.9, 1.2, 1.5, 2.0, 2.5, 3.0]
    print(f"{'ligne (m)':>10} {'collectées':>11} {'dist (m)':>9} {'grasps':>8} {'eff. (balle/m)':>15}")
    best = None
    for lw in line_widths:
        total_col, total_dist, total_att = 0, 0.0, 0
        for t in range(args.trials):
            config = TennisWorldConfig(
                width=6.0, height=10.0, n_balls=args.balls, seed=100 + t
            )
            r = run_one(lw, config)
            total_col += r["collected"]
            total_dist += r["distance_m"]
            total_att += r["attempts"]
        eff = total_col / total_dist if total_dist else 0
        print(f"{lw:10.1f} {total_col:8d}/{args.balls*args.trials:<3d} {total_dist/args.trials:9.1f} {total_att:8d} {eff:15.3f}")
        if best is None or eff > best[1]:
            best = (lw, eff)

    print(f"\nMeilleure largeur de ligne : {best[0]} m ({best[1]:.2f} balles/mètre parcouru)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
