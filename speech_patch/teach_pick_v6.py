#!/usr/bin/env python3
# encoding: utf-8
"""teach_pick_v6 — Calibration "par demonstration" du pick-and-place.

Principe (le meme que la calibration officielle Hiwonder) :
  1. Le bras descend en pose de prehension, pince ouverte.
  2. Tu ajustes si besoin la pose pour que les doigts soient juste au-dessus du sol.
  3. Tu poses le cube PILE entre les doigts.
  4. Le bras remonte en pose d'observation (sans toucher au cube).
  5. Le script note OU se trouve le cube dans l'image => c'est la "cible".

Ensuite, pick_and_place_node_v6 deplace le robot jusqu'a ce que le cube soit
exactement a cette position dans l'image, puis refait la meme prehension.
Plus besoin de mesurer d'offset camera/pince ni de distance au metre.

Usage (sur le robot, en SSH, avec un terminal interactif : ssh -t robot) :
    source /opt/ros/humble/setup.bash
    source /home/ubuntu/ros2_ws/install/setup.bash
    python3 /home/ubuntu/speech_patch/teach_pick_v6.py

AVANT : arrete pick_and_place_node et le watchdog (voir GUIDE_PICK_V6.md).
"""

import statistics
import threading
import time

import rclpy
from rclpy.node import Node
from interfaces.msg import ColorsInfo
from servo_controller_msgs.msg import ServosPosition
from servo_controller.bus_servo_control import set_servo_position

from pick_calib import load_calib, save_calib, pose, CALIB_FILE

SERVO_LIMITS = {1: (0, 1000), 2: (0, 1000), 3: (0, 1000), 4: (0, 1000), 5: (0, 1000), 10: (200, 700)}


class Teach(Node):
    def __init__(self):
        super().__init__('teach_pick_v6')
        self.pub = self.create_publisher(ServosPosition, 'servo_controller', 1)
        self.latest = None
        self.latest_t = 0.0
        self.create_subscription(ColorsInfo, '/color_detect_node/color_info', self._cb, 1)

    def _cb(self, msg):
        red = [c for c in msg.data if c.color == 'red']
        self.latest = max(red, key=lambda c: c.width * c.height) if red else None
        self.latest_t = time.time()

    def move(self, positions, duration=1.5):
        set_servo_position(self.pub, duration, positions)
        time.sleep(duration + 0.4)


def ask(prompt):
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return 'q'


def main():
    rclpy.init()
    node = Teach()
    threading.Thread(target=rclpy.spin, args=(node,), daemon=True).start()
    time.sleep(1.0)
    calib = load_calib()
    grip = {sid: pos for sid, pos in calib['grip_pose']}
    g_open, g_close = calib['gripper_open'], calib['gripper_close']

    print('\n=== Calibration pick v6 ===')
    print('Pose le robot au sol, sur la surface ou il ramassera les cubes.')
    print('Le robot ne doit PLUS bouger (roues) pendant toute la calibration.\n')

    if node.latest_t == 0.0:
        print('ATTENTION : aucun message sur /color_detect_node/color_info.')
        print('Lance simple_color_detect_v3.py avant ce script.\n')

    ask('Entree pour descendre le bras en pose de prehension (pince ouverte)...')
    node.move(tuple(grip.items()) + ((10, g_open),), 2.0)

    print('\nRegle la pose : les doigts ouverts doivent etre a ~0,5-1 cm du sol,')
    print('et un cube pose entre eux doit etre bien au centre.')
    print('Commandes : "2 +20"  "3 -15"  "4 +10"  (servo, increment)')
    print('            "f" = fermer la pince (tester la prise), "o" = ouvrir')
    print('            "ok" = pose validee      "q" = quitter sans sauver')
    while True:
        print('  pose actuelle : ' + ', '.join(f'{k}:{v}' for k, v in grip.items()))
        cmd = ask('> ')
        if cmd == 'ok':
            break
        if cmd == 'q':
            node.destroy_node()
            rclpy.shutdown()
            return
        if cmd == 'f':
            node.move(((10, g_close),), 0.8)
            continue
        if cmd == 'o':
            node.move(((10, g_open),), 0.8)
            continue
        try:
            sid, delta = cmd.split()
            sid, delta = int(sid), int(delta)
            if sid not in grip:
                print('  servo inconnu (1,2,3,4,5)')
                continue
            lo, hi = SERVO_LIMITS[sid]
            grip[sid] = max(lo, min(hi, grip[sid] + delta))
            node.move(((sid, grip[sid]),), 0.6)
        except ValueError:
            print('  format : "<servo> <increment>", ex : 3 -10')

    node.move(((10, g_open),), 0.8)
    ask('\nPose le cube PILE au centre entre les doigts ouverts, puis Entree...')
    print('Remontee du bras en pose d\'observation (pince ouverte, le cube reste au sol)...')
    node.move(pose(calib, 'observe_pose', g_open), 2.0)
    time.sleep(1.0)

    print('Mesure de la position du cube pendant 3 s...')
    xs, ys, ws, hs = [], [], [], []
    t_end = time.time() + 3.0
    while time.time() < t_end:
        c = node.latest
        if c is not None and time.time() - node.latest_t < 0.3:
            xs.append(c.x); ys.append(c.y); ws.append(c.width); hs.append(c.height)
        time.sleep(0.07)

    if len(xs) < 10:
        print(f'\nECHEC : cube vu seulement {len(xs)} fois. Causes possibles :')
        print(' - le cube est hors champ dans la pose d\'observation')
        print('   (bord bas de l\'image) -> modifier "observe_pose" dans ' + CALIB_FILE)
        print(' - seuils de couleur : voir /color_detect_node/debug_image')
        node.destroy_node()
        rclpy.shutdown()
        return

    tx, ty = statistics.median(xs), statistics.median(ys)
    tw, th = statistics.median(ws), statistics.median(hs)
    jitter = max(statistics.pstdev(xs), statistics.pstdev(ys))
    print(f'\nCible : x={tx:.0f}  y={ty:.0f}  taille={tw:.0f}x{th:.0f}  (bruit +/-{jitter:.1f} px)')
    if ty > 185:
        print('ATTENTION : cube tout en bas de l\'image, il risque de sortir du champ.')
        print('Mieux : incliner la camera plus vers le bas dans "observe_pose".')

    calib['grip_pose'] = [[k, v] for k, v in grip.items()]
    calib.update({'target_x': tx, 'target_y': ty, 'target_w': tw, 'target_h': th})
    save_calib(calib)
    print(f'Calibration sauvegardee dans {CALIB_FILE}')
    print('\nTest : recule le cube de ~15 cm devant le robot, lance pick_and_place_node_v6')
    print('puis dis/envoie "attrape cube" (touche P de l\'interface).')

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
