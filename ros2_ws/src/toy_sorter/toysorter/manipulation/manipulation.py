"""Manipulation : interface commune + backend virtuel.

Backend réel : le bras Hiwonder (bus série/servos) via son SDK Python,
ou le node ROS2 du bras. Grasp top-down : approche au-dessus, descente,
fermeture pince, remontée.
"""
from __future__ import annotations

from ..core.types import GraspResult, Vec3
from ..core.virtual_world import VirtualWorld


class ManipulationBackend:
    def grasp(self, target: Vec3) -> GraspResult:
        raise NotImplementedError

    def place_in_bin(self) -> GraspResult:
        raise NotImplementedError


class VirtualManipulation(ManipulationBackend):
    def __init__(self, world: VirtualWorld):
        self.world = world

    def grasp(self, target: Vec3) -> GraspResult:
        ok, toy = self.world.attempt_grasp(target)
        return GraspResult(
            success=ok,
            message=f"grasped toy {toy.id} ({toy.label})" if ok else "missed / no toy at target",
        )

    def place_in_bin(self) -> GraspResult:
        ok = self.world.release_in_bin()
        return GraspResult(
            success=ok,
            message="released in bin" if ok else "not close enough to bin / gripper empty",
        )
