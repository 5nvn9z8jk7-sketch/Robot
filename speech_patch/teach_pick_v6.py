#!/usr/bin/env python3
# encoding: utf-8
"""teach_pick_v6 - outil interactif de calibration de la pince (a lancer sur le robot).

Principe: on PLACE manuellement le bras (servos 2/3/4) pour que la pince
soit au sol, ouverte, autour du cube. Le script memorise les positions
servo, remonte le bras, puis mesure pendant 3 s ce que la camera voit
quand le cube est exactement au point de grip. Resultat -> pick_calib.json.

Commandes pendant le reglage:
  2 +20 / 2 -20   servo 2 (epaule): monte/descend tout le bras
  3 +10 / 3 -10   servo 3 (coude): avance/recule la pince
  4 +10 / 4 -10   servo 4 (poignet): incline la pince
  f               ferme la pince (test de prise)
  o               rouvre la pince
  ok              valide la position -> mesure
  q               quitte sans sauvegarder

A lancer avec un terminal interactif (ssh -t), la detection couleur
(simple_color_detect_v3.py) doit tourner.
"""

import math
import sys
import threading
import time

import rclpy
from rclpy.node import Node

from interfaces.msg import ColorsInfo
from servo_controller_msgs.msg import ServosPosition
from servo_controller.bus_servo_control import set_servo_position

sys.path.insert(0, '/home/ubuntu/speech_patch')
import pick_calib

MEASURE_SECONDS = 3.0
MIN_SAMPLES = 10      # sur ~30 messages a 10 Hz
MEASURE_ATTEMPTS = 8  # retries si la camera est en panne (watchdog la restaure)
RETRY_WAIT_S = 15.0


def collect_with_retry(node):
    """Mesure 3 s; si 0 donnee, attend le watchdog camera et reessaie."""
    for attempt in range(1, MEASURE_ATTEMPTS + 1):
        print(f'Mesure {attempt}/{MEASURE_ATTEMPTS} (3 s)...')
        ok, n, stats = collect_measurements(node)
        if ok:
            return True, n, stats
        print(f'  {n} echantillons. Camera en panne ou cube invisible.')
        print('  Attente du watchdog camera (~15 s)...')
        time.sleep(RETRY_WAIT_S)
    return False, n, None


class TeachPickV6(Node):
    def __init__(self):
        super().__init__('teach_pick_v6')
        self.servo_pub = self.create_publisher(ServosPosition, 'servo_controller', 1)
        self.color_sub = self.create_subscription(
            ColorsInfo, '/color_detect_node/color_info', self._color_cb, 1)
        self._collecting = False
        self._samples = []
        self.get_logger().info('teach_pick_v6 pret')

    def _color_cb(self, msg):
        if not self._collecting:
            return
        for c in msg.data:
            if c.color == 'red' and c.width * c.height > 0:
                self._samples.append((c.x, c.y, c.width, c.height))
                break  # premier cube rouge seulement

    def move_servos(self, positions, duration=1.0, wait=True):
        set_servo_position(
            self.servo_pub, duration,
            tuple((int(k), int(v)) for k, v in positions.items()))
        if wait:
            time.sleep(duration + 0.3)


def collect_measurements(node, seconds=MEASURE_SECONDS, min_samples=MIN_SAMPLES):
    """Mesure la position du cube pendant `seconds`, retourne (ok, stats)."""
    node._collecting = True
    node._samples = []
    time.sleep(seconds)
    node._collecting = False
    samples = node._samples
    n = len(samples)
    if n < min_samples:
        return False, n, None
    xs = [s[0] for s in samples]
    ys = [s[1] for s in samples]
    sizes = [(s[2] + s[3]) / 2.0 for s in samples]
    mean = lambda v: sum(v) / len(v)
    std = lambda v: math.sqrt(sum((x - mean(v)) ** 2 for x in v) / len(v))
    stats = {
        'x': mean(xs), 'y': mean(ys), 'size': mean(sizes),
        'noise': max(std(xs), std(ys)),
        'w': mean([s[2] for s in samples]),
        'h': mean([s[3] for s in samples]),
        'n': n,
    }
    return True, n, stats


def parse_adjust(cmd):
    """'2 +20' -> (2, +20). Retourne None si invalide."""
    parts = cmd.split()
    if len(parts) != 2:
        return None
    try:
        servo = int(parts[0])
        delta = int(parts[1])
    except ValueError:
        return None
    if servo not in (2, 3, 4):
        return None
    return servo, delta


def main():
    rclpy.init()
    node = TeachPickV6()
    spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_thread.start()

    # Repart des positions deja apprises si une calibration existe
    calib = pick_calib.load_calib()
    if calib:
        positions = {int(k): v for k, v in calib[pick_calib.KEY_SERVO].items()}
        print('(Reprise des positions servos de la calibration existante)')
    else:
        positions = dict(pick_calib.DEFAULT_DOWN)   # copie modifiable
    gripper_open = pick_calib.DEFAULT_GRIPPER_OPEN
    gripper_close = min(pick_calib.GRIPPER_MAX, int(calib.get(
        pick_calib.KEY_GRIPPER_CLOSE, pick_calib.DEFAULT_GRIPPER_CLOSE))) if calib \
        else pick_calib.DEFAULT_GRIPPER_CLOSE

    print('=' * 60)
    print('CALIBRATION PINCE - teach_pick_v6')
    print('=' * 60)
    print('Le robot ne doit pas bouger. Cube rouge a portee de main.')
    try:
        input('Appuyez sur Entrée pour descendre le bras (pince ouverte)... ')
    except EOFError:
        print('Pas de terminal interactif. Lancez avec: ssh -t robot')
        rclpy.shutdown()
        return
    node.move_servos(positions, 1.5)

    print()
    print('Reglez la pince: doigts ouverts ~1 cm du sol, cube au centre.')
    print('Commandes: 2 +20 | 2 -20 | 3 +10 | 3 -10 | 4 +10 | 4 -10')
    print('            f = fermer pince, o = rouvrir, ok = valider, q = quitter')
    while True:
        try:
            cmd = input('> ').strip()
        except EOFError:
            cmd = 'q'
        if not cmd:
            continue
        if cmd == 'q':
            print('Abandon, rien n\'a ete sauvegarde.')
            rclpy.shutdown()
            return
        if cmd == 'ok':
            break
        if cmd == 'f':
            node.move_servos({10: gripper_close}, 0.8)
            print('Pince fermee (test de prise). Tapez o pour rouvrir.')
            continue
        if cmd == 'o':
            node.move_servos({10: gripper_open}, 0.8)
            print('Pince ouverte.')
            continue
        adj = parse_adjust(cmd)
        if adj is None:
            print('Commande invalide. Exemples: 2 +20, 3 -10, f, o, ok')
            continue
        servo, delta = adj
        new_val = max(0, min(1000, positions[servo] + delta))
        positions[servo] = new_val
        node.move_servos({servo: new_val}, 0.4)
        print(f'Servo {servo} = {new_val}')

    # Mesure: le point de grip est INVISIBLE pour la camera (sous le champ).
    # Plan B: on mesure une POSITION DE REFERENCE visible + distance au mètre.
    print()
    print('Le point de grip (cube entre les doigts) est SOUS le champ de la camera.')
    print('Plan B: mesure d\'une POSITION DE REFERENCE visible.')
    print('Posez le cube a ~15-20 cm devant le robot (la ou il est bien vu),')
    print('aligne avec le point de grip (meme ligne, droit devant la pince).')
    try:
        input('Appuyez sur Entrée pour remonter le bras et mesurer (3 s)... ')
    except EOFError:
        pass
    node.move_servos({10: gripper_open}, 0.5)
    up = dict(pick_calib.DEFAULT_UP)
    up[10] = gripper_open
    node.move_servos(up, 1.5)

    ok, n, stats = collect_with_retry(node)
    if not ok:
        print()
        print(f'ECHEC : cube vu seulement {n} fois, meme apres {MEASURE_ATTEMPTS} essais.')
        print('Verifiez que simple_color_detect_v3.py tourne, que le watchdog')
        print('camera est actif, et que le cube est bien visible.')
        rclpy.shutdown()
        return

    print()
    print(f"Reference : x={stats['x']:.0f}  y={stats['y']:.0f}  "
          f"taille={stats['w']:.0f}x{stats['h']:.0f}  (bruit +-{stats['noise']:.1f} px)")

    # Distance au metre: reference -> point de grip
    extra_m = None
    while extra_m is None:
        try:
            raw = input('Distance en cm entre le cube (position de reference) '
                        'et le point de grip (au sol, entre les doigts) ? ').strip()
            extra_cm = float(raw.replace(',', '.'))
            if not (0 < extra_cm < 60):
                print('Valeur invraisemblable (0-60 cm attendus).')
                continue
            extra_m = extra_cm / 100.0
        except ValueError:
            print('Nombre invalide, ex: 12 ou 12.5')
        except EOFError:
            rclpy.shutdown()
            return

    path = pick_calib.save_calib(
        target_x=stats['x'], target_y=stats['y'], target_size=stats['size'],
        extra_forward_m=extra_m, noise_px=stats['noise'], samples=stats['n'],
        servo_positions=positions, gripper_close=gripper_close,
        gripper_open=gripper_open, arm_up=pick_calib.DEFAULT_UP)

    print()
    print(f'Calibration sauvegardee dans {path}')
    print(f'  - signature cube a la reference: x={stats["x"]:.0f}, taille={stats["size"]:.0f}px')
    print(f'  - avance a l\'aveugle finale: {extra_m*100:.1f} cm')
    print('Si besoin, ajustez gripper_close dans pick_calib.json (max 700).')
    rclpy.shutdown()


if __name__ == '__main__':
    main()
