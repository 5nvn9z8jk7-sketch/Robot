#!/usr/bin/env python3
# encoding: utf-8
"""essai_survol.py — Essai (lecture seule pour les roues) : la caméra du poignet
voit-elle le cube quand la pince est en SURVOL, quelques cm au-dessus de lui ?

Ne bouge QUE le bras (jamais les roues). Rien n'est enregistré dans pick_calib.json.

Départ : position de prise apprise (pince au sol, ouverte), épaule remontée.
Commandes :
  2 +20 / 2 -20   épaule : monte / descend tout le bras
  3 +10 / 3 -10   coude
  4 +10 / 4 -10   poignet (oriente la caméra)
  v               ce que voit la détection pendant 2 s (x, y, taille du cube)
  p               affiche la position actuelle des servos
  q               termine : bras remis en position de regard, position notée
                  dans /tmp/survol_pose.json
Lancer : ssh -t robot, puis python3 essai_survol.py (ROS sourcé).
"""
import json
import sys
import threading
import time

import rclpy
from rclpy.node import Node

from interfaces.msg import ColorsInfo
from servo_controller_msgs.msg import ServosPosition
from servo_controller.bus_servo_control import set_servo_position

sys.path.insert(0, '/home/ubuntu/speech_patch')
import pick_calib  # noqa: E402

LIMITES = {2: (20, 750), 3: (10, 600), 4: (150, 400)}   # prudence : petits pas
MONTEE_DEPART = 120                                      # épaule au-dessus de la prise


class EssaiSurvol(Node):
    def __init__(self):
        super().__init__('essai_survol')
        self.pub = self.create_publisher(ServosPosition, 'servo_controller', 1)
        self.vus = []
        self.lock = threading.Lock()
        self.create_subscription(ColorsInfo, '/color_detect_node/color_info', self._cb, 1)

    def _cb(self, msg):
        rouges = [c for c in msg.data if c.color == 'red']
        with self.lock:
            self.vus.append((time.monotonic(), max(rouges, key=lambda c: c.width * c.height)
                             if rouges else None))
            self.vus = self.vus[-50:]

    def bouger(self, pos, duree=1.0):
        set_servo_position(self.pub, duree, tuple((int(k), int(v)) for k, v in pos.items()))
        time.sleep(duree + 0.3)

    def regarder(self, secondes=2.0):
        t0 = time.monotonic()
        time.sleep(secondes)
        with self.lock:
            v = [c for t, c in self.vus if t >= t0]
        cubes = [c for c in v if c is not None]
        if not v:
            print('  AUCUNE image analysée (caméra ou détection arrêtée ?)')
        elif not cubes:
            print(f'  Cube NON vu ({len(v)} images analysées)')
        else:
            xs = sorted(c.x for c in cubes); ys = sorted(c.y for c in cubes)
            ws = sorted(c.width for c in cubes); hs = sorted(c.height for c in cubes)
            m = len(cubes) // 2
            print(f'  Cube vu {len(cubes)}/{len(v)} images : x={xs[m]} y={ys[m]} '
                  f'taille={ws[m]}x{hs[m]} px (image 640x400 ; centre x=320)')


def main():
    rclpy.init()
    n = EssaiSurvol()
    threading.Thread(target=rclpy.spin, args=(n,), daemon=True).start()
    calib = pick_calib.load_calib() or {}
    pos = {int(k): v for k, v in calib.get(pick_calib.KEY_SERVO, pick_calib.DEFAULT_DOWN).items()}
    ouvert = int(calib.get(pick_calib.KEY_GRIPPER_OPEN, pick_calib.DEFAULT_GRIPPER_OPEN))
    regard = {int(k): v for k, v in calib.get(pick_calib.KEY_ARM_UP, pick_calib.DEFAULT_UP).items()}
    pos[10] = ouvert
    pos[2] = min(LIMITES[2][1], pos[2] + MONTEE_DEPART)

    print('=' * 60)
    print('ESSAI SURVOL — seul le bras bouge, les roues restent immobiles')
    print('=' * 60)
    print('Posez le cube au sol, juste devant la pince (là où elle le saisirait).')
    try:
        input('Entrée pour placer le bras en survol... ')
    except EOFError:
        print('Lancer avec : ssh -t robot')
        return
    n.bouger(pos, 1.5)
    print(f'Survol : {pos}')
    n.regarder()
    print('Commandes : 2 +20 | 2 -20 | 3 +10 | 3 -10 | 4 +10 | 4 -10 | v | p | q')
    while True:
        try:
            cmd = input('> ').strip()
        except EOFError:
            cmd = 'q'
        if cmd == 'q':
            break
        if cmd == 'v':
            n.regarder()
            continue
        if cmd == 'p':
            print(f'  {pos}')
            continue
        parts = cmd.split()
        try:
            s, d = int(parts[0]), int(parts[1])
            assert s in LIMITES and len(parts) == 2
        except (ValueError, IndexError, AssertionError):
            print('Commande invalide. Exemples : 2 +20, 4 -10, v, q')
            continue
        bas, haut = LIMITES[s]
        nouveau = max(bas, min(haut, pos[s] + d))
        if nouveau != pos[s] + d:
            print(f'  limite de prudence atteinte pour le servo {s} ({bas}-{haut})')
        pos[s] = nouveau
        n.bouger({s: nouveau}, 0.5)
        print(f'  servo {s} = {nouveau}')
        n.regarder(1.0)

    with open('/tmp/survol_pose.json', 'w') as f:
        json.dump(pos, f)
    print(f'Position de survol notée : {pos}  (/tmp/survol_pose.json)')
    regard[10] = ouvert
    n.bouger(regard, 1.5)
    print('Bras remis en position de regard. Fin.')
    rclpy.shutdown()


if __name__ == '__main__':
    main()
