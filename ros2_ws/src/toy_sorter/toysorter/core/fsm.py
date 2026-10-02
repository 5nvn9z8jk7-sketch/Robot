"""State machine d'orchestration : RECHERCHE → APPROCHE → GRASP → BAC → DÉPÔT.

Fonctionne avec n'importe quelle combinaison de backends (virtuels ou ROS2).
"""
from __future__ import annotations

import time

from ..core.types import TaskState
from ..manipulation.manipulation import ManipulationBackend
from ..navigation.navigation import NavigationBackend
from ..perception.perception import PerceptionBackend


class ToySorterFSM:
    GRASP_APPROACH_DIST = 0.25
    MAX_GRASP_RETRIES = 3
    MAX_SEARCH_SCANS = 20

    def __init__(
        self,
        perception: PerceptionBackend,
        navigation: NavigationBackend,
        manipulation: ManipulationBackend,
        bin_pos_getter=None,
        log=print,
    ):
        self.perception = perception
        self.navigation = navigation
        self.manipulation = manipulation
        self.bin_pos_getter = bin_pos_getter or (lambda: None)
        self.log = log
        self.state = TaskState.IDLE
        self.stats = {
            "toys_ranged": 0,
            "grasp_attempts": 0,
            "grasp_failures": 0,
            "nav_toys": 0,
            "t_start": None,
        }

    # ------------------------------------------------------------------ helpers
    def _goto_state(self, s: TaskState):
        self.state = s
        self.log(f"[FSM] état = {s.name}")

    def _approach_pose(self, toy_pos):
        """Point de stationnement à GRASP_APPROACH_DIST du jouet."""
        from ..core.types import Vec3

        d = (toy_pos.x**2 + toy_pos.y**2) ** 0.5
        if d == 0:
            return Vec3(0.0, 0.0, 0.0)
        scale = max(0.0, d - self.GRASP_APPROACH_DIST) / d
        return Vec3(toy_pos.x * scale, toy_pos.y * scale, 0.0)

    def _bin_pos(self):
        pos = self.bin_pos_getter()
        if pos is None:
            raise RuntimeError("position du bac inconnue")
        return pos

    # ------------------------------------------------------------------ main loop
    def run(self) -> bool:
        """Boucle principale. Retourne True si tous les jouets sont rangés."""
        self.stats["t_start"] = time.time()
        self._goto_state(TaskState.SEARCHING)
        scans = 0
        grasp_retries = 0

        while True:
            if self.state == TaskState.SEARCHING:
                if scans >= self.MAX_SEARCH_SCANS:
                    self._goto_state(TaskState.DONE)
                    break
                detections = self.perception.detect_toys()
                if not detections:
                    scans += 1
                    continue
                best = max(detections, key=lambda d: d.confidence)
                self.current_target = best.pos_3d
                self.stats["nav_toys"] += 1
                scans = 0
                self._goto_state(TaskState.NAVIGATING_TO_TOY)

            elif self.state == TaskState.NAVIGATING_TO_TOY:
                approach = self._approach_pose(self.current_target)
                self.navigation.goto(approach)
                self._goto_state(TaskState.GRASPING)

            elif self.state == TaskState.GRASPING:
                # re-détecter pour compenser le bruit / objet déplacé
                det = self._closest_detection(self.current_target)
                if det is None:
                    self._goto_state(TaskState.SEARCHING)
                    continue
                self.current_target = det.pos_3d
                self.stats["grasp_attempts"] += 1
                result = self.manipulation.grasp(self.current_target)
                if result.success:
                    grasp_retries = 0
                    self._goto_state(TaskState.LIFTING)
                else:
                    self.stats["grasp_failures"] += 1
                    grasp_retries += 1
                    if grasp_retries >= self.MAX_GRASP_RETRIES:
                        grasp_retries = 0
                        self.log("[FSM] abandon de cette cible, retour à la recherche")
                        self._goto_state(TaskState.SEARCHING)
                    # sinon : reste en GRASPING pour retenter

            elif self.state == TaskState.LIFTING:
                # en réel : trajectoire de remontée du bras ; en virtuel : rien à faire
                self._goto_state(TaskState.NAVIGATING_TO_BIN)

            elif self.state == TaskState.NAVIGATING_TO_BIN:
                self.navigation.goto(self._bin_pos())
                self._goto_state(TaskState.PLACING)

            elif self.state == TaskState.PLACING:
                result = self.manipulation.place_in_bin()
                if result.success:
                    self.stats["toys_ranged"] += 1
                    self.log(f"[FSM] jouet rangé ({self.stats['toys_ranged']})")
                    self._goto_state(TaskState.SEARCHING)
                else:
                    self._goto_state(TaskState.ERROR)
                    return False

            elif self.state == TaskState.DONE:
                break

        self.stats["elapsed_s"] = round(time.time() - self.stats["t_start"], 2)
        return self._goto_done()

    def _goto_done(self) -> bool:
        self._goto_state(TaskState.DONE)
        return True

    def _closest_detection(self, target):
        dets = self.perception.detect_toys()
        if not dets:
            return None
        return min(dets, key=lambda d: d.pos_3d.flat_dist(target))
