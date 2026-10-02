"""Monde virtuel : jouets, bac, robot, physique simplifiée.

Sert de banc d'essai au pipeline complet sans matériel.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .types import Bin, Toy, Vec3


@dataclass
class SimConfig:
    arena_size: float = 4.0
    n_toys: int = 5
    toy_labels: tuple = ("teddy", "cube", "car")
    seed: int = 42
    grasp_success_prob: float = 0.85
    detection_noise_std: float = 0.02
    detection_dropout_prob: float = 0.1
    missed_grasp_slack: float = 0.03


@dataclass
class VirtualWorld:
    """État du monde : positions réelles (cachées au robot) + robot simulé."""

    config: SimConfig = field(default_factory=SimConfig)
    toys: list = field(default_factory=list)
    bin: Bin = None
    robot_pos: Vec3 = field(default_factory=Vec3)
    robot_yaw: float = 0.0
    gripper_holding: Toy = None
    rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self):
        if self.rng is None:
            self.rng = random.Random(self.config.seed)
        if not self.toys:
            self._spawn()

    def _spawn(self):
        self.bin = Bin(pos=Vec3(self.config.arena_size / 2, self.config.arena_size / 2, 0.0))
        half = self.config.arena_size / 2 - 0.3
        for i in range(self.config.n_toys):
            pos = Vec3(
                self.rng.uniform(-half, half),
                self.rng.uniform(-half, half),
                0.05,
            )
            label = self.rng.choice(self.config.toy_labels)
            self.toys.append(Toy(id=i, label=label, pos=pos))

    # ---------------------------------------------------------------- perception
    def visible_toys(self) -> list:
        """Retourne les jouets visibles avec bruit de détection simulé."""
        out = []
        for toy in self.toys:
            if toy.grasped or toy.in_bin:
                continue
            if self.rng.random() < self.config.detection_dropout_prob:
                continue
            out.append(toy)
        return out

    def noisy_pose(self, toy: Toy) -> Vec3:
        s = self.config.detection_noise_std
        return Vec3(
            toy.pos.x + self.rng.gauss(0, s),
            toy.pos.y + self.rng.gauss(0, s),
            toy.pos.z + self.rng.gauss(0, s),
        )

    # ---------------------------------------------------------------- robot motion
    def drive_to(self, target: Vec3, tol: float = 0.05) -> bool:
        import math

        dx, dy = target.x - self.robot_pos.x, target.y - self.robot_pos.y
        d = (dx * dx + dy * dy) ** 0.5
        if d < tol:
            return True
        step = min(0.3, d)
        self.robot_pos.x += dx / d * step
        self.robot_pos.y += dy / d * step
        self.robot_yaw = math.atan2(dy, dx)
        return self.robot_pos.flat_dist(target) < tol

    # ---------------------------------------------------------------- manipulation
    def attempt_grasp(self, target: Vec3) -> tuple:
        """Retourne (success, holding_toy). Échoue si la cible est trop loin."""
        if self.gripper_holding is not None:
            return False, None
        candidates = [
            t for t in self.toys if not t.grasped and not t.in_bin
        ]
        nearest = min(
            candidates,
            key=lambda t: t.pos.flat_dist(target),
            default=None,
        )
        if nearest is None:
            return False, None
        if nearest.pos.flat_dist(target) > self.config.missed_grasp_slack:
            return False, None
        success = self.rng.random() < self.config.grasp_success_prob
        if success:
            nearest.grasped = True
            self.gripper_holding = nearest
            return True, nearest
        return False, None

    def release_in_bin(self) -> bool:
        if self.gripper_holding is None:
            return False
        if self.robot_pos.flat_dist(self.bin.pos) > self.bin.radius + 0.2:
            return False
        toy = self.gripper_holding
        toy.grasped = False
        toy.in_bin = True
        toy.pos = Vec3(self.bin.pos.x, self.bin.pos.y, 0.1)
        self.gripper_holding = None
        return True

    def remaining_toys(self) -> int:
        return sum(1 for t in self.toys if not t.in_bin)
