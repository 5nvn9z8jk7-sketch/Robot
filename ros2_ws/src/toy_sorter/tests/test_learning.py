import os
import sys

sys.path.insert(0, os.path.dirname(__file__) + "/..")

from toysorter.core.types import Detection, Vec3
from toysorter.core.virtual_world import SimConfig, VirtualWorld
from toysorter.learning.learning import (
    LearningConfig,
    LearningMonitor,
    VirtualLearningMonitor,
)


def make_detection(conf):
    return Detection(label="toy", confidence=conf, pos_3d=Vec3(1.0, 0.5, 0.05))


def test_collect_only_informative():
    m = LearningMonitor(config=LearningConfig(collect_min_conf=0.3), log=lambda msg: None)
    assert m.observe(make_detection(0.1), 1) is None     # trop faible : bruit
    assert m.observe(make_detection(0.5), 2) is not None # incertain : à apprendre
    assert len(m.buffer) == 1


def test_grasp_signals():
    m = LearningMonitor(log=lambda msg: None)
    m.observe(make_detection(0.8), 10)
    m.confirm_positive(10)
    assert m.buffer[-1].label_confirmed

    m.observe(make_detection(0.9), 11)
    m.confirm_negative(11)
    assert m.buffer[-1].label_negative


def test_negative_quota():
    m = LearningMonitor(config=LearningConfig(retrain_every=5), log=lambda msg: None)
    for i in range(10):
        m.observe(make_detection(0.6), i)
        m.confirm_positive(i)
    for i in range(10, 20):
        m.observe(make_detection(0.9), i)
        m.confirm_negative(i)
    batch = m.build_training_batch()
    assert len(batch["negatives"]) <= int(len(batch["positives"]) * 0.3)


def test_virtual_model_improves():
    w = VirtualWorld(config=SimConfig(n_toys=2, seed=0))
    m = VirtualLearningMonitor(world=w, log=lambda msg: None)
    before = m.model_precision
    batch = {"positives": [1] * 10, "negatives": []}
    m.retrain(batch)
    assert m.model_precision > before
    assert m.retrain_cycles == 1
