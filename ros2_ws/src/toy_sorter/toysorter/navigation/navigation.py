"""Navigation : interface commune + backend virtuel.

Backend réel : Nav2 (action nav2_msgs/action/NavigateToPose) ou navigation
Hiwonder. En simulation, on déplace le robot dans VirtualWorld.
"""
from __future__ import annotations

from ..core.types import Vec3
from ..core.virtual_world import VirtualWorld


class NavigationBackend:
    def goto(self, target: Vec3) -> bool:
        raise NotImplementedError


class VirtualNavigation(NavigationBackend):
    def __init__(self, world: VirtualWorld, tol: float = 0.05):
        self.world = world
        self.tol = tol

    def goto(self, target: Vec3) -> bool:
        while not self.world.drive_to(target, tol=self.tol):
            pass
        return True
