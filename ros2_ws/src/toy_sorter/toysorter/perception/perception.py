"""Perception : interface commune + backend virtuel.

Backend réel (à activer sur le robot) : node ROS2 qui reçoit les détections
YOLO/TensorRT et les transforme en pose 3D via la caméra de profondeur.
"""
from __future__ import annotations

from ..core.types import Detection, Vec3
from ..core.virtual_world import VirtualWorld


class PerceptionBackend:
    def detect_toys(self) -> list:
        raise NotImplementedError


class VirtualPerception(PerceptionBackend):
    """Simule YOLO + caméra profondeur : détections avec bruit et dropout."""

    def __init__(self, world: VirtualWorld):
        self.world = world

    def detect_toys(self) -> list:
        detections = []
        for toy in self.world.visible_toys():
            pose = self.world.noisy_pose(toy)
            detections.append(
                Detection(
                    label=toy.label,
                    confidence=self.world.rng.uniform(0.72, 0.99),
                    pos_3d=pose,
                )
            )
        return detections

    def detect_bin(self) -> Vec3 | None:
        return self.world.bin.pos
