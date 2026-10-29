#!/usr/bin/env python3
# encoding: utf-8
"""pick_calib - bibliotheque de calibration partagee entre teach_pick_v6
et pick_and_place_node_v6.

Le fichier pick_calib.json contient:
  {
    "servo_positions": {"1": 500, "2": 100, ...},  # position du bras POSE (grip point au sol)
    "gripper_open": 200,
    "gripper_close": 560,
    "arm_up": {"1": 500, "2": 700, ...},           # position remontee apres grip
    "target_x": 180,     # x du cube (pixels, repere depth 640x400) a la POSITION DE REFERENCE
    "target_y": 170,
    "target_size": 95,    # (width+height)/2 en pixels a la position de reference
    "extra_forward_m": 0.12,  # distance a l'aveugle: reference -> point de grip (m)
    "noise_px": 1.5,      # bruit de mesure observe pendant la calibration
    "measured_samples": 30,
    "created": "2026-..."
  }

Le point de grip (cube entre les doigts) est INVISIBLE pour la camera
(sous le bord du champ). La calibration mesure donc une POSITION DE
REFERENCE visible, et v6 avance ensuite de extra_forward_m a l'aveugle
pour amener la pince sur le cube.
"""

import json
import os
import time

CALIB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pick_calib.json')

DEFAULT_DOWN = {1: 500, 2: 100, 3: 450, 4: 230, 5: 500, 10: 200}
DEFAULT_UP = {1: 500, 2: 700, 3: 15, 4: 180, 5: 500}
DEFAULT_GRIPPER_OPEN = 200
DEFAULT_GRIPPER_CLOSE = 560
GRIPPER_MIN = 200
GRIPPER_MAX = 700   # NE JAMAIS DEPASSER 700

KEY_SERVO = 'servo_positions'
KEY_GRIPPER_OPEN = 'gripper_open'
KEY_GRIPPER_CLOSE = 'gripper_close'
KEY_ARM_UP = 'arm_up'
KEY_TARGET_X = 'target_x'
KEY_TARGET_Y = 'target_y'
KEY_TARGET_SIZE = 'target_size'
KEY_EXTRA = 'extra_forward_m'
KEY_NOISE = 'noise_px'
KEY_SAMPLES = 'measured_samples'
KEY_CREATED = 'created'


def save_calib(target_x, target_y, target_size, extra_forward_m, noise_px, samples,
               servo_positions, gripper_close, gripper_open=DEFAULT_GRIPPER_OPEN,
               arm_up=None, path=CALIB_PATH):
    data = {
        KEY_SERVO: {str(k): int(v) for k, v in servo_positions.items()},
        KEY_GRIPPER_OPEN: int(gripper_open),
        KEY_GRIPPER_CLOSE: int(gripper_close),
        KEY_ARM_UP: {str(k): int(v) for k, v in (arm_up or DEFAULT_UP).items()},
        KEY_TARGET_X: float(target_x),
        KEY_TARGET_Y: float(target_y),
        KEY_TARGET_SIZE: float(target_size),
        KEY_EXTRA: float(extra_forward_m),
        KEY_NOISE: float(noise_px),
        KEY_SAMPLES: int(samples),
        KEY_CREATED: time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    return path


def load_calib(path=CALIB_PATH):
    """Retourne le dict de calibration, ou None si absent/invalide."""
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if KEY_TARGET_X not in data or KEY_SERVO not in data:
            return None
        return data
    except (ValueError, OSError):
        return None


def calib_path(path=CALIB_PATH):
    return path
