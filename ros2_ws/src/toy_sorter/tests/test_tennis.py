import os
import sys

sys.path.insert(0, os.path.dirname(__file__) + "/..")

from toysorter import VirtualManipulation, VirtualNavigation, VirtualPerception
from toysorter.core.types import GraspResult
from toysorter.tennis import (
    TennisSweeperFSM,
    TennisWorld,
    TennisWorldConfig,
)


def make_fsm(config=None):
    world = TennisWorld(config=config or TennisWorldConfig(width=4.0, height=6.0, n_balls=6, seed=1))

    class BasketManipulation(VirtualManipulation):
        def grasp(self, target):
            ok, ball = self.world.attempt_grasp(target)
            if ok:
                self.world.release_in_bin()
            return GraspResult(success=ok, message="" if ok else "missed")

    fsm = TennisSweeperFSM(
        perception=VirtualPerception(world),
        navigation=VirtualNavigation(world),
        manipulation=BasketManipulation(world),
        world=world,
        log=lambda msg: None,
    )
    return fsm, world


def test_all_balls_collected():
    fsm, world = make_fsm()
    assert fsm.run()
    assert world.remaining_balls() == 0
    assert fsm.stats["balls_collected"] == 6


def test_sweep_covers_court():
    fsm, world = make_fsm()
    fsm.run()
    assert fsm.stats["lines_swept"] >= 8
    assert fsm.stats["grasp_attempts"] >= 6


def test_basket_accumulates():
    world = TennisWorld(config=TennisWorldConfig(width=2.0, height=2.0, n_balls=1, seed=0))
    ball = world.toys[0]
    ok, _ = world.attempt_grasp(ball.pos)
    assert ok
    assert world.release_in_bin()
    assert world.balls_in_basket == 1
    assert world.remaining_balls() == 0
