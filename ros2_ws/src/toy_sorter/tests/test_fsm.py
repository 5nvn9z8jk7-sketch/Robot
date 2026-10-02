import os
import sys

sys.path.insert(0, os.path.dirname(__file__) + "/..")

from toysorter import (
    SimConfig,
    ToySorterFSM,
    VirtualManipulation,
    VirtualNavigation,
    VirtualPerception,
    VirtualWorld,
)


def run(n_toys, seed):
    world = VirtualWorld(config=SimConfig(n_toys=n_toys, seed=seed))
    fsm = ToySorterFSM(
        perception=VirtualPerception(world),
        navigation=VirtualNavigation(world),
        manipulation=VirtualManipulation(world),
        bin_pos_getter=lambda: world.bin.pos,
        log=lambda msg: None,
    )
    assert fsm.run(), "la FSM doit terminer sans erreur"
    assert world.remaining_toys() == 0, f"tous les jouets doivent être rangés (reste {world.remaining_toys()})"
    assert fsm.stats["toys_ranged"] == n_toys
    return fsm.stats


def test_all_toys_sorted_5():
    stats = run(5, seed=1)
    assert stats["grasp_attempts"] >= 5


def test_all_toys_sorted_10():
    run(10, seed=2)


def test_grasp_failures_retried():
    """Avec un taux d'échec élevé, la FSM doit retenter puis abandonner proprement."""
    world = VirtualWorld(config=SimConfig(n_toys=3, seed=3, grasp_success_prob=0.3))
    fsm = ToySorterFSM(
        perception=VirtualPerception(world),
        navigation=VirtualNavigation(world),
        manipulation=VirtualManipulation(world),
        bin_pos_getter=lambda: world.bin.pos,
        log=lambda msg: None,
    )
    fsm.run()
    assert fsm.stats["grasp_failures"] > 0
