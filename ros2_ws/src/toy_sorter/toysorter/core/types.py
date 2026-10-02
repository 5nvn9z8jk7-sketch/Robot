"""Types de base partagés par le robot virtuel et le robot réel."""
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class TaskState(Enum):
    IDLE = auto()
    SEARCHING = auto()
    NAVIGATING_TO_TOY = auto()
    GRASPING = auto()
    LIFTING = auto()
    NAVIGATING_TO_BIN = auto()
    PLACING = auto()
    DONE = auto()
    ERROR = auto()


@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def dist(self, other: "Vec3") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2) ** 0.5

    def flat_dist(self, other: "Vec3") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


@dataclass
class Toy:
    id: int
    label: str
    pos: Vec3
    grasped: bool = False
    in_bin: bool = False


@dataclass
class Bin:
    pos: Vec3
    radius: float = 0.25


@dataclass
class Detection:
    label: str
    confidence: float
    center_2d: tuple = (0.0, 0.0)
    bbox: tuple = (0.0, 0.0, 0.0, 0.0)
    pos_3d: Optional[Vec3] = None


@dataclass
class GraspResult:
    success: bool
    message: str = ""
