"""Monde virtuel tennis : terrain rectangulaire, balles, panier embarqué.

Le panier est embarqué : quand le robot saisit une balle, elle est stockée
sur lui — pas de déplacement vers un bac externe.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.types import Vec3
from ..core.virtual_world import VirtualWorld


@dataclass
class TennisWorldConfig:
    width: float = 11.0     # largeur terrain (m) — terrain de tennis ~11m en simple
    height: float = 24.0    # longueur (m) — ~24m ; réduisez pour tester plus vite
    n_balls: int = 12
    seed: int = 7
    detection_noise_std: float = 0.03
    detection_dropout_prob: float = 0.15
    grasp_success_prob: float = 0.8
    detection_range: float = 1.2  # portée caméra (m) — limite la largeur de ligne utile


class TennisWorld(VirtualWorld):
    """Étend VirtualWorld : terrain borné + panier embarqué + balles."""

    def __init__(self, config: TennisWorldConfig | None = None):
        if config is None:
            config = TennisWorldConfig()
        self.config = config
        import random

        self.rng = random.Random(config.seed)
        self.toys = []
        self._spawn_balls()
        from ..core.types import Bin, Toy

        self.bin = Bin(pos=Vec3(0, 0, 0))  # inutilisé : panier embarqué
        self.robot_pos = Vec3(-config.width / 2 + 0.3, -config.height / 2 + 0.3, 0.0)
        self.robot_yaw = 0.0
        self.gripper_holding = None
        self.balls_in_basket = 0

    def _spawn_balls(self):
        from ..core.types import Toy

        half_w, half_h = self.config.width / 2 - 0.4, self.config.height / 2 - 0.4
        for i in range(self.config.n_balls):
            self.toys.append(
                Toy(
                    id=i,
                    label="ball",
                    pos=Vec3(
                        self.rng.uniform(-half_w, half_w),
                        self.rng.uniform(-half_h, half_h),
                        0.03,
                    ),
                )
            )

    # ---------------------------------------------------------------- perception
    def visible_toys(self):
        out = []
        for ball in self.toys:
            if ball.grasped or ball.in_bin:
                continue
            if self.rng.random() < self.config.detection_dropout_prob:
                continue
            if ball.pos.flat_dist(self.robot_pos) > self.config.detection_range:
                continue
            out.append(ball)
        return out

    def noisy_pose(self, ball):
        s = self.config.detection_noise_std
        return Vec3(
            ball.pos.x + self.rng.gauss(0, s),
            ball.pos.y + self.rng.gauss(0, s),
            0.03,
        )

    # ---------------------------------------------------------------- manipulation
    def attempt_grasp(self, target):
        if self.gripper_holding is not None:
            return False, None
        candidates = [t for t in self.toys if not t.grasped and not t.in_bin]
        nearest = min(candidates, key=lambda t: t.pos.flat_dist(target), default=None)
        if nearest is None or nearest.pos.flat_dist(target) > 0.04:
            return False, None
        if self.rng.random() < self.config.grasp_success_prob:
            nearest.grasped = True
            self.gripper_holding = nearest
            return True, nearest
        return False, None

    def release_in_bin(self):
        """Dépose la balle dans le panier EMBARQUÉ : toujours réussi si on tient une balle."""
        if self.gripper_holding is None:
            return False
        ball = self.gripper_holding
        ball.in_bin = True
        self.gripper_holding = None
        self.balls_in_basket += 1
        return True

    def remaining_balls(self):
        return sum(1 for t in self.toys if not t.in_bin)
