# encoding: utf-8
"""Calibration partagee entre teach_pick_v6.py et pick_and_place_node_v6.py.

IMPORTANT : la camera du ROSOrin Pro est montee SUR LE BRAS.
=> Ce que voit la camera depend de la position du bras. Toute calibration
   n'a de sens que si le bras est TOUJOURS dans la meme "pose d'observation"
   au moment de regarder le cube. C'est ce que garantit ce fichier.

Fichier : /home/ubuntu/speech_patch/pick_calib.json
"""

import json
import os

CALIB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pick_calib.json')

# Servo IDs : 1=base, 2/3/4=articulations, 5=poignet, 10=pince
DEFAULT_CALIB = {
    # Pose d'observation = pose "tracking and grasping" officielle Hiwonder
    'observe_pose': [[1, 500], [2, 720], [3, 100], [4, 120], [5, 500]],
    # Pose de prehension au sol (pince ouverte). A ajuster avec teach_pick_v6.py
    'grip_pose': [[1, 500], [2, 100], [3, 450], [4, 230], [5, 500]],
    'gripper_open': 200,
    'gripper_close': 560,   # Hiwonder utilise 600. NE JAMAIS depasser 700 (butee).
    # Position du cube dans l'image (320x200) quand il est pile sous la pince.
    # Rempli par teach_pick_v6.py. None = pas encore calibre.
    'target_x': None,
    'target_y': None,
    'target_w': None,
    'target_h': None,
}


def load_calib():
    calib = dict(DEFAULT_CALIB)
    if os.path.exists(CALIB_FILE):
        with open(CALIB_FILE) as f:
            calib.update(json.load(f))
    return calib


def save_calib(calib):
    with open(CALIB_FILE, 'w') as f:
        json.dump(calib, f, indent=2)


def pose(calib, name, gripper=None):
    """Retourne la pose sous forme de tuple ((id, pos), ...) pour set_servo_position."""
    p = [tuple(x) for x in calib[name]]
    if gripper is not None:
        p.append((10, int(gripper)))
    return tuple(p)
