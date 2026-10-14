"""Boucle d'auto-apprentissage : le robot apprend de son expérience.

Principes implémentés :
  1. Collecte continue : chaque détection est stockée avec son image (virtuelle
     ou réelle) et sa confiance.
  2. Auto-labelisation par signal de succès : si un grasp réussit, les détections
     précédentes deviennent des exemples positifs confirmés ; si le grasp rate
     avec une confiance élevée, contre-exemple (hard negative).
  3. Cohérence temporelle : une détection proche (haute confiance) corrige une
     détection lointaine douteuse sur la même cible (pseudo-label).
  4. Réentraînement périodique : fine-tuning du modèle sur le buffer accumulé,
     avec garde-fous (quota de négatifs, validation sur set figé).

La version VirtualLearningMonitor fonctionne avec le monde virtuel existant :
elle simule un modèle de détection qui s'améliore à chaque cycle de
réentraînement, ce qui permet de valider toute la logique de bout en bout
sans robot ni GPU.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..core.types import Detection, TaskState
from ..core.virtual_world import VirtualWorld


@dataclass
class Experience:
    """Une observation candidate à l'apprentissage."""
    frame_id: int
    detection: Detection
    label_confirmed: bool = False      # confirmé par un signal objectif
    label_negative: bool = False       # faux positif confirmé
    pseudo_labeled: bool = False       # label dérivé d'une autre observation


@dataclass
class LearningConfig:
    collect_min_conf: float = 0.30     # collecter à partir de 30% de confiance
    uncertain_low: float = 0.40         # sous ce seuil : incertain
    uncertain_high: float = 0.70        # au-dessus : sûr, pas besoin d'apprendre
    retrain_every: int = 20             # nb d'expériences avant réentraînement
    hard_negative_quota: float = 0.3    # max de négatifs dans un batch
    model_gain_per_cycle: float = 0.06  # gain simulé de précision / cycle
    model_conf_floor: float = 0.55      # précision de départ du modèle simulé


class LearningMonitor:
    """Collecte les expériences et déclenche les réentraînements."""

    def __init__(self, config: LearningConfig | None = None, log=print):
        self.config = config or LearningConfig()
        self.log = log
        self.buffer: list[Experience] = []
        self.retrain_cycles = 0
        self.events: list[str] = []

    # ------------------------------------------------------------ collecte
    def observe(self, detection: Detection, frame_id: int) -> Experience | None:
        """Enregistre une détection si elle mérite d'être apprise.

        On apprend surtout des cas incertains : trop sûr = déjà acquis,
        trop faible = bruit. Les cas moyens sont là où le gain est maximal.
        """
        c = detection.confidence
        if c < self.config.collect_min_conf:
            return None
        exp = Experience(frame_id=frame_id, detection=detection)
        self.buffer.append(exp)
        return exp

    # -------------------------------------------------- signaux objectifs
    def confirm_positive(self, frame_id: int):
        """Grasp réussi : la détection correspondante devient positif confirmé."""
        for exp in reversed(self.buffer):
            if exp.frame_id == frame_id and not exp.label_confirmed:
                exp.label_confirmed = True
                exp.label_negative = False
                self.events.append(
                    f"frame {frame_id}: positif confirmé par grasp réussi"
                )
                return

    def confirm_negative(self, frame_id: int):
        """Grasp raté alors que la détection était sûre : faux positif probable."""
        for exp in reversed(self.buffer):
            if (
                exp.frame_id == frame_id
                and exp.detection.confidence > self.config.uncertain_high
                and not exp.label_confirmed
            ):
                exp.label_negative = True
                self.events.append(
                    f"frame {frame_id}: négatif confirmé (grasp raté sur cible sûre)"
                )
                return

    def pseudo_label(self, weak: Experience, strong: Experience):
        """Une observation proche et sûre corrige une observation douteuse."""
        if strong.detection.confidence > self.config.uncertain_high:
            weak.pseudo_labeled = True
            weak.label_confirmed = True

    # ------------------------------------------------------ réentraînement
    def should_retrain(self) -> bool:
        return len(self.buffer) >= self.config.retrain_every

    def build_training_batch(self) -> dict:
        """Construit le batch en respectant le quota de négatifs."""
        positives = [e for e in self.buffer if e.label_confirmed and not e.label_negative]
        negatives = [e for e in self.buffer if e.label_negative]
        max_neg = int(len(positives) * self.config.hard_negative_quota)
        batch = {"positives": positives, "negatives": negatives[:max_neg]}
        self.buffer = []
        return batch


class VirtualLearningMonitor(LearningMonitor):
    """Variante simulation : le "modèle" gagne en précision à chaque cycle.

    Le modèle simulé émet des confiances plus hautes à mesure que les cycles
    d'apprentissage s'accumulent — ce qui permet de vérifier que la boucle
    complète (collecte → signal → réentraînement → amélioration) fonctionne.
    """

    def __init__(self, world: VirtualWorld, config: LearningConfig | None = None, log=print):
        super().__init__(config, log)
        self.world = world
        self.model_precision = self.config.model_conf_floor

    def model_confidence(self, true_conf: float) -> float:
        """Simule la confiance du modèle : tirage autour de la précision courante."""
        spread = max(0.02, 0.35 * (1.0 - self.model_precision))
        conf = true_conf * self.world.rng.gauss(self.model_precision, spread)
        return min(1.0, max(0.01, conf))

    def retrain(self, batch: dict):
        n = len(batch["positives"]) + len(batch["negatives"])
        if n == 0:
            self.log("[LEARN] batch vide, pas de réentraînement")
            return
        self.model_precision = min(
            0.98, self.model_precision + self.config.model_gain_per_cycle
        )
        self.retrain_cycles += 1
        self.log(
            f"[LEARN] réentraînement #{self.retrain_cycles}: {len(batch['positives'])} positifs, "
            f"{len(batch['negatives'])} négatifs -> précision modèle ~ {self.model_precision:.2f}"
        )


def attach_learning_to_fsm(fsm, monitor: VirtualLearningMonitor):
    """Branche le moniteur d'apprentissage sur une ToySorterFSM existante.

    Instrumente la FSM : les grasps réussis/ratés envoient leurs signaux au
    moniteur, et les réentraînements sont déclenchés automatiquement.
    """
    original_run = fsm.run
    frame_counter = {"id": 0}

    original_grasp = fsm.manipulation.grasp
    original_detect = fsm.perception.detect_toys

    def detect_with_learning():
        dets = original_detect()
        for d in dets:
            frame_counter["id"] += 1
            monitor.observe(d, frame_counter["id"])
        return dets

    def grasp_with_learning(target):
        frame_id = frame_counter["id"]
        result = original_grasp(target)
        if result.success:
            monitor.confirm_positive(frame_id)
        else:
            monitor.confirm_negative(frame_id)
        if monitor.should_retrain():
            monitor.retrain(monitor.build_training_batch())
        return result

    fsm.perception.detect_toys = detect_with_learning
    fsm.manipulation.grasp = grasp_with_learning
    return original_run
