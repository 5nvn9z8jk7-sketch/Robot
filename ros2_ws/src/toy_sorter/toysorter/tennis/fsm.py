"""Mission tennis : ramasser des balles sur un terrain par balayage systématique.

Différences avec la mission jouets :
  - le monde est un terrain rectangulaire aux limites connues
  - le robot balaie en lignes (comme une tondeuse) pour couvrir le terrain
  - les balles sont saisies par le dessus (scoop/vertical grasp)
  - pas de déplacement vers un bac : les balles tombent dans un panier EMBARQUÉ
  - la cadence est optimisée (grasp → balle suivante)

Testable en simulation sans matériel, comme le reste du projet.
"""
from __future__ import annotations

from ..core.types import TaskState, Vec3


class TennisSweeperFSM:
    """FSM spécialisée terrain : SCAN → LIGNE → ALIGN → GRASP → STOCK.

    Le balayage se fait en couloirs parallèles ; quand une balle est détectée,
    le robot s'aligne dessus, la saisit par le dessus, la stocke dans son
    panier embarqué, puis reprend le balayage où il s'était arrêté.
    """

    GRASP_APPROACH_DIST = 0.18
    MAX_GRASP_RETRIES = 3
    LINE_WIDTH = 0.5

    def __init__(self, perception, navigation, manipulation, world, log=print):
        self.perception = perception
        self.navigation = navigation
        self.manipulation = manipulation
        self.world = world
        self.log = log
        self.state = TaskState.IDLE
        self.stats = {
            "balls_collected": 0,
            "grasp_attempts": 0,
            "grasp_failures": 0,
            "lines_swept": 0,
        }

    # ------------------------------------------------------------------ helpers
    def _goto_state(self, s: TaskState):
        self.state = s
        self.log(f"[TENNIS] état = {s.name}")

    def _sweep_waypoints(self):
        """Génère les points de passage du balayage (lignes en zigzag)."""
        w = self.world
        margin = 0.3
        half_x = w.config.width / 2 - margin
        y = -w.config.height / 2 + margin
        waypoints = []
        left_to_right = True
        while y <= w.config.height / 2 - margin:
            x = half_x if left_to_right else -half_x
            waypoints.append(Vec3(x, y, 0.0))
            waypoints.append(Vec3(-x, y, 0.0))
            left_to_right = not left_to_right
            y += self.LINE_WIDTH
        return waypoints

    def _approach_pose(self, ball_pos):
        d = (ball_pos.x**2 + ball_pos.y**2) ** 0.5
        if d == 0:
            return Vec3(0.0, 0.0, 0.0)
        scale = max(0.0, d - self.GRASP_APPROACH_DIST) / d
        return Vec3(ball_pos.x * scale, ball_pos.y * scale, 0.0)

    # ------------------------------------------------------------------ main loop
    def run(self) -> bool:
        waypoints = self._sweep_waypoints()
        self._goto_state(TaskState.SEARCHING)
        grasp_retries = 0

        for wp in waypoints:
            # avancer vers le point de passage en guettant les balles
            while not self.world.drive_to(wp, tol=0.15):
                det = self._closest_ball()
                if det is None:
                    continue
                # balle repérée : interruption et séquence de saisie
                self.stats["nav_toys"] = self.stats.get("nav_toys", 0) + 1
                self._goto_state(TaskState.NAVIGATING_TO_TOY)
                self.navigation.goto(self._approach_pose(det.pos_3d))
                self._goto_state(TaskState.GRASPING)
                det = self._closest_ball() or det
                self.stats["grasp_attempts"] += 1
                result = self.manipulation.grasp(det.pos_3d)
                if result.success:
                    grasp_retries = 0
                    self.stats["balls_collected"] += 1
                    self._goto_state(TaskState.LIFTING)
                else:
                    self.stats["grasp_failures"] += 1
                    grasp_retries += 1
                    if grasp_retries >= self.MAX_GRASP_RETRIES:
                        grasp_retries = 0
                        self.log("[TENNIS] balle abandonnée (enherbée/ombre ?)")
                self._goto_state(TaskState.SEARCHING)

            if abs(self.world.robot_pos.y - wp.y) < 0.2:
                self.stats["lines_swept"] += 1

        self._goto_state(TaskState.DONE)
        remaining = self.world.remaining_balls()
        self.log(
            f"[TENNIS] balayage terminé : {self.stats['balls_collected']} balles "
            f"collectées, {remaining} restantes, {self.stats['lines_swept']} lignes"
        )
        return remaining == 0

    def _closest_ball(self):
        dets = self.perception.detect_toys()
        if not dets:
            return None
        here = self.world.robot_pos
        return min(dets, key=lambda d: d.pos_3d.flat_dist(here))
