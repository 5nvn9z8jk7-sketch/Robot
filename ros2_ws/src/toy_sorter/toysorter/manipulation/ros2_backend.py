"""Backend ROS2 réel : bras robotique Hiwonder (servos via SDK série).

Sur le robot : utilise le SDK Python Hiwonder / le bus servos.
Le grasp top-down : position au-dessus de la cible, descente, pince, remontée.
"""
from __future__ import annotations

from ..core.types import GraspResult, Vec3


class Ros2Manipulation:
    """À câbler sur le robot : SDK bras Hiwonder (bus série, ex. /dev/ttyACM0)."""

    def __init__(self, port: str = "/dev/ttyACM0", gripper_closed: int = 140):
        self.port = port
        self.gripper_closed = gripper_closed

    def _ik_top_down(self, target: Vec3):
        """Cinématique inverse pour un grasp vertical : à adapter au modèle du bras."""
        raise NotImplementedError

    def grasp(self, target: Vec3) -> GraspResult:
        """ Boucle réelle (pseudo-code) :

        1. joints = self._ik_top_down(target) au-dessus (+5cm)
        2. ouvrir la pince, descendre, fermer la pince
        3. vérifier la charge moteur (capteur de courant) ou vérification visuelle
        4. remonter
        """
        raise NotImplementedError("à connecter au bras Hiwonder")

    def place_in_bin(self) -> GraspResult:
        raise NotImplementedError("à connecter au bras Hiwonder")
