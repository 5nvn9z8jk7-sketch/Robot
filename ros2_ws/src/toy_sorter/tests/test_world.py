import os
import sys

sys.path.insert(0, os.path.dirname(__file__) + "/..")

from toysorter.core.types import Vec3
from toysorter.core.virtual_world import SimConfig, VirtualWorld


def test_spawn_respects_count():
    w = VirtualWorld(config=SimConfig(n_toys=7, seed=0))
    assert len(w.toys) == 7
    assert w.bin is not None


def test_drive_to():
    w = VirtualWorld(config=SimConfig(seed=0))
    target = Vec3(1.0, 1.0, 0.0)
    while not w.drive_to(target):
        pass
    assert w.robot_pos.flat_dist(target) < 0.1


def test_grasp_only_near_target():
    w = VirtualWorld(config=SimConfig(n_toys=1, seed=0, grasp_success_prob=1.0))
    toy = w.toys[0]
    ok, _ = w.attempt_grasp(Vec3(10, 10, 0))  # loin du jouet
    assert not ok
    ok, held = w.attempt_grasp(toy.pos)
    assert ok and held is toy


def test_release_in_bin():
    w = VirtualWorld(config=SimConfig(n_toys=1, seed=0, grasp_success_prob=1.0))
    toy = w.toys[0]
    w.attempt_grasp(toy.pos)
    while not w.drive_to(w.bin.pos):
        pass
    assert w.release_in_bin()
    assert toy.in_bin and w.gripper_holding is None
