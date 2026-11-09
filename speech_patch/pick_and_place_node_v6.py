#!/usr/bin/env python3
# encoding: utf-8
"""pick_and_place_node_v6 - pick-and-place piloté par la calibration (teach_pick_v6).

Différence avec v5: plus aucun paramètre à deviner. La position du bras,
la position cible du cube dans l'image (x, y, taille) et la fermeture de la
pince viennent de pick_calib.json produit par teach_pick_v6.py.

Séquence:
  1. Cherche le cube rouge (/color_detect_node/color_info)
  2. Positionnement: centre le cube sur target_x (rotation) et avance
     jusqu'à ce que sa taille atteigne target_size. Les logs err=(x, taille)
     doivent baisser jusqu'à « En position ».
  3. Préhension: descend le bras aux positions servos apprises, ferme la
     pince à gripper_close, remonte le bras.

Déclencheurs: /vocal_detect/asr_result (voix ou touche P du keypad web).
Calibration: /home/ubuntu/speech_patch/pick_calib.json (rechargé à chaque run).
"""

import math
import sys
import threading
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from interfaces.msg import ColorsInfo
from servo_controller_msgs.msg import ServosPosition
from servo_controller.bus_servo_control import set_servo_position

sys.path.insert(0, '/home/ubuntu/speech_patch')
import pick_calib

# Optique du repère depth (640x400) - mêmes valeurs que pick_and_place_servo.py
DEFAULT_FX = 423.376

TARGET_COLOR = 'red'
CMD_VEL_RATE = 0.05
DETECT_TIMEOUT = 5.0
TOL_X_PX = 15          # tolérance centrage (pixels)
TOL_SIZE_PX = 8        # tolérance taille (pixels)
STEP_FORWARD_M = 0.04  # pas d'avance par itération
MAX_ITER = 60
MAX_LOST = 3           # itérations consécutives sans cube avant abandon
TURN_DEADZONE = 0.02   # rad

ODOM_STALE_S = 0.5     # odom considérée perdue si aucun message depuis ce délai
COLOR_SETTLE_S = 0.15  # ignore les détections reçues moins de 0.15 s après l'appel
                       # (images prises pendant le mouvement précédent)

# Déclenchement: un verbe d'action ET le mot « cube »/« bloc » (le seul objet que
# ce nœud sait attraper). Les mots trop vagues (objet, balle, rouge, cherche,
# trouve...) déclenchaient le bras en pleine conversation.
TRIGGER_VERBS = ['attrape', 'attraper', 'ramasse', 'ramasser', 'prends', 'prendre',
                 'saisis', 'saisir', 'va chercher', 'pick', 'grab']
TRIGGER_OBJECTS = ['cube', 'bloc', 'block']
# Ces phrases appartiennent à autonomous_mission_node (« attrape tous les cubes »):
# sans cette exclusion, les deux nœuds démarraient en même temps (conflit roues + bras).
MISSION_WORDS = ['tous', 'tout', 'mission', 'collecte', 'pick all']

# Arrêt d'urgence: un de ces mots sur /vocal_detect/asr_result interrompt
# immédiatement la séquence en cours (voix, ou touche 0/ESPACE du keypad web).
STOP_WORDS = ['stop', 'arrête', 'arrete', 'arrêtes', 'arretes', 'halte',
              'urgence', 'pas bouger', 'stoppe']


class PickAndPlaceV6(Node):
    def __init__(self):
        super().__init__('pick_and_place_node_v6')
        self._lock = threading.Lock()
        self._busy = False
        self._abort = False
        self._latest_color = None
        self._odom_x = 0.0
        self._odom_y = 0.0
        self._odom_yaw = 0.0
        self._odom_stamp = 0.0    # time.monotonic() du dernier message /odom
        self._color_stamp = 0.0   # time.monotonic() du dernier message couleur

        self.cmd_vel_pub = self.create_publisher(Twist, '/controller/cmd_vel', 1)
        self.tts_pub = self.create_publisher(String, '/tts_node/tts_text', 1)
        self.servo_pub = self.create_publisher(ServosPosition, 'servo_controller', 1)

        self.create_subscription(
            String, '/vocal_detect/asr_result', self._asr_cb, 1)
        self.create_subscription(
            ColorsInfo, '/color_detect_node/color_info', self._color_cb, 1)
        self.create_subscription(
            Odometry, '/odom', self._odom_cb, 1)

        calib = pick_calib.load_calib()
        if calib:
            self.get_logger().info(
                f'✅ Calibration chargee: target=({calib[pick_calib.KEY_TARGET_X]:.0f},'
                f'{calib[pick_calib.KEY_TARGET_Y]:.0f}) '
                f'taille={calib[pick_calib.KEY_TARGET_SIZE]:.0f}px '
                f'bruit=+-{calib[pick_calib.KEY_NOISE]:.1f}px')
        else:
            self.get_logger().warn(
                f'⚠️ PAS de calibration ({pick_calib.calib_path()}). '
                'Lancez teach_pick_v6.py d\'abord — valeurs de secours utilisees.')
        self.get_logger().info('pick_and_place_node_v6 pret (touche P ou voix pour lancer)')

    # ─── callbacks ───

    def _asr_cb(self, msg):
        text = msg.data.strip().lower()
        if not text:
            return
        self.get_logger().info(f'ASR: "{text}"')
        if self._is_stop(text):
            with self._lock:
                running = self._busy
                if running:
                    self._abort = True
            self._stop()
            if running:
                self.get_logger().warn('🛑 ARRET D\'URGENCE demandé - séquence interrompue')
            return
        if not self._is_trigger(text):
            return
        with self._lock:
            if self._busy:
                self.get_logger().info('Deja en cours, ignore')
                return
            self._busy = True
            self._abort = False
        threading.Thread(target=self._run_sequence, daemon=True).start()

    def _color_cb(self, msg):
        with self._lock:
            self._latest_color = msg
            self._color_stamp = time.monotonic()

    def _odom_cb(self, msg):
        with self._lock:
            self._odom_x = msg.pose.pose.position.x
            self._odom_y = msg.pose.pose.position.y
            q = msg.pose.pose.orientation
            self._odom_yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                                        1.0 - 2.0 * (q.y * q.y + q.z * q.z))
            self._odom_stamp = time.monotonic()

    @staticmethod
    def _is_stop(text):
        return any(w in text for w in STOP_WORDS)

    @staticmethod
    def _is_trigger(text):
        if any(w in text for w in MISSION_WORDS):
            return False
        has_verb = any(v in text for v in TRIGGER_VERBS)
        has_object = any(o in text for o in TRIGGER_OBJECTS)
        return has_verb and has_object

    # ─── helpers ───

    def _say(self, text):
        self.get_logger().info(f'TTS: {text}')
        msg = String()
        msg.data = text
        self.tts_pub.publish(msg)

    def _stop(self):
        self.cmd_vel_pub.publish(Twist())

    def _odom_alive(self):
        with self._lock:
            return time.monotonic() - self._odom_stamp < ODOM_STALE_S

    def _get_red_cube(self, timeout=2.0):
        """Renvoie le plus gros cube rouge d'une détection RÉCENTE.
        Les messages reçus avant l'appel (+ COLOR_SETTLE_S) sont ignorés: ils
        proviennent d'images prises pendant le mouvement précédent et faisaient
        sur-corriger le robot (oscillations)."""
        fresh_after = time.monotonic() + COLOR_SETTLE_S
        deadline = time.time() + timeout
        best = None
        best_size = 0
        while time.time() < deadline and not self._abort:
            with self._lock:
                info = self._latest_color
                stamp = self._color_stamp
            if stamp < fresh_after:
                time.sleep(0.02)
                continue
            if info and len(info.data) > 0:
                reds = [c for c in info.data if c.color == TARGET_COLOR]
                for c in reds:
                    size = c.width * c.height
                    if size > best_size:
                        best = c
                        best_size = size
                if best is not None:
                    return best
            time.sleep(0.05)
        return best

    def _turn_to(self, angle_rad, angular_speed=0.4):
        """Rotation: +angle = cube a droite -> tourne a droite (meme convention que v5).
        Rotation CHRONOMÉTRÉE (durée = angle / vitesse), comme la version validée
        le 30/10. La boucle sur le cap de l'odométrie (PR #3) a été essayée le
        09/11 : le robot tournait ~2,4x trop et oscillait sans jamais se centrer.
        L'odométrie est seulement mesurée et journalisée, pour diagnostic."""
        if abs(angle_rad) < TURN_DEADZONE:
            return
        duration = abs(angle_rad) / angular_speed
        twist = Twist()
        twist.angular.z = -math.copysign(angular_speed, angle_rad)
        odom_ok = self._odom_alive()
        with self._lock:
            prev_yaw = self._odom_yaw
        turned = 0.0
        start = time.time()
        while time.time() - start < duration and not self._abort:
            self.cmd_vel_pub.publish(twist)
            time.sleep(CMD_VEL_RATE)
            if odom_ok:
                with self._lock:
                    yaw = self._odom_yaw
                turned += abs(math.atan2(math.sin(yaw - prev_yaw), math.cos(yaw - prev_yaw)))
                prev_yaw = yaw
        self._stop()
        time.sleep(0.25)
        if odom_ok:
            with self._lock:
                yaw = self._odom_yaw
            turned += abs(math.atan2(math.sin(yaw - prev_yaw), math.cos(yaw - prev_yaw)))
            mesure = f'odom a mesuré {math.degrees(turned):.1f}°'
        else:
            mesure = 'odom absente'
        self.get_logger().info(
            f'  Rotation {math.degrees(angle_rad):+.1f}° (chrono {duration:.2f}s, {mesure})')

    def _drive(self, distance_m, linear_speed=0.08):
        """distance_m negatif = avance, positif = recule.
        Boucle fermee sur l'odometrie: la distance parcourue est EXACTE,
        independamment de la vitesse reelle des roues.
        Convention reellement observee (keypad web) : linear.x > 0 = AVANCE."""
        if abs(distance_m) < 0.005:
            return
        target = abs(distance_m)
        with self._lock:
            x0, y0 = self._odom_x, self._odom_y
        twist = Twist()
        twist.linear.x = linear_speed if distance_m < 0 else -linear_speed
        direction = 'Avance' if distance_m < 0 else 'Recule'
        self.get_logger().info(f'  {direction} {target*100:.1f}cm (boucle odom)')
        # marge x3 au cas ou l'odom decroche, + 2 s de securite
        nominal = target / linear_speed
        start = time.time()
        deadline = start + 3.0 * nominal + 2.0
        while time.time() < deadline and not self._abort:
            # Sans odom, la distance mesurée reste à 0: on roulerait jusqu'à
            # 3x la distance demandée. Repli sur la durée nominale.
            if not self._odom_alive() and time.time() - start >= nominal:
                self.get_logger().warn('  odom absente -> arret a la duree nominale')
                break
            with self._lock:
                x1, y1 = self._odom_x, self._odom_y
            traveled = math.hypot(x1 - x0, y1 - y0)
            if traveled >= target:
                break
            self.cmd_vel_pub.publish(twist)
            time.sleep(CMD_VEL_RATE)
        if not self._abort:
            with self._lock:
                x1, y1 = self._odom_x, self._odom_y
            traveled = math.hypot(x1 - x0, y1 - y0)
            self.get_logger().info(
                f'  odom: {traveled*100:.1f}cm parcourus (cible {target*100:.1f}cm)')
        self._stop()
        time.sleep(0.2)

    def _move_servos(self, positions, duration=1.0, wait=True):
        set_servo_position(
            self.servo_pub, duration,
            tuple((int(k), int(v)) for k, v in positions.items()))
        if wait:
            time.sleep(duration + 0.3)

    # ─── séquence ───

    def _position_and_grip(self, calib):
        target_x = float(calib[pick_calib.KEY_TARGET_X])
        target_size = float(calib[pick_calib.KEY_TARGET_SIZE])
        noise = max(2.0, float(calib.get(pick_calib.KEY_NOISE, 2.0)))
        tol_x = max(TOL_X_PX, noise * 4)
        tol_size = max(TOL_SIZE_PX, noise * 3)

        lost = 0
        for i in range(MAX_ITER):
            if self._abort:
                return False
            cube = self._get_red_cube(timeout=1.5)
            if cube is None:
                lost += 1
                if lost >= MAX_LOST:
                    self.get_logger().warn('⚠️ Cube perdu')
                    return False
                continue
            lost = 0

            size = (cube.width + cube.height) / 2.0
            err_x = cube.x - target_x
            err_size = target_size - size   # >0 : trop loin, il faut avancer

            if abs(err_x) <= tol_x and abs(err_size) <= tol_size:
                self.get_logger().info(
                    f'  [{i+1}] ✅ En position (x={cube.x}, taille={size:.0f}px)')
                return True

            # 1. Centrage prioritaire
            if abs(err_x) > tol_x:
                self.get_logger().info(
                    f'  [{i+1}] err=({err_x:+.0f}px, {err_size:+.0f}px) -> centrage')
                self._turn_to(math.atan2(cube.x - target_x, DEFAULT_FX))
                continue

            # 2. Approche
            self.get_logger().info(
                f'  [{i+1}] err=({err_x:+.0f}px, {err_size:+.0f}px) -> avance')
            step = max(0.02, min(STEP_FORWARD_M, err_size / 300.0))
            self._drive(-step)

        self.get_logger().warn('⏱️ Positionnement: max iterations')
        return False

    def _grip(self, calib):
        servo_down = {int(k): v for k, v in calib[pick_calib.KEY_SERVO].items()}
        arm_up = {int(k): v for k, v in calib.get(pick_calib.KEY_ARM_UP,
                                                   pick_calib.DEFAULT_UP).items()}
        gripper_open = int(calib.get(pick_calib.KEY_GRIPPER_OPEN,
                                     pick_calib.DEFAULT_GRIPPER_OPEN))
        gripper_close = min(pick_calib.GRIPPER_MAX,
                            int(calib.get(pick_calib.KEY_GRIPPER_CLOSE,
                                          pick_calib.DEFAULT_GRIPPER_CLOSE)))

        self.get_logger().info('  Prehension: descente aux positions apprises')
        down = dict(servo_down)
        down[10] = gripper_open
        self._move_servos(down, 1.5)
        if self._abort:
            return False

        time.sleep(0.4)   # stabilisation
        self.get_logger().info(f'  Prehension: fermeture pince ({gripper_close})')
        self._move_servos({10: gripper_close}, 0.8)
        if self._abort:
            return False

        self.get_logger().info('  Prehension: remontee')
        up = dict(arm_up)
        up[10] = gripper_close
        self._move_servos(up, 1.5)
        self.get_logger().info('  ✅ Prehension terminee')
        return True

    def _run_sequence(self):
        try:
            calib = pick_calib.load_calib()
            if not calib:
                calib = {
                    pick_calib.KEY_SERVO: dict(pick_calib.DEFAULT_DOWN),
                    pick_calib.KEY_TARGET_X: 320.0,
                    pick_calib.KEY_TARGET_Y: 200.0,
                    pick_calib.KEY_TARGET_SIZE: 90.0,
                    pick_calib.KEY_NOISE: 2.0,
                }
                self.get_logger().warn('Calibration absente: valeurs de secours (imprecis)')

            self._say("Je cherche le cube rouge.")
            cube = self._get_red_cube(timeout=DETECT_TIMEOUT)
            if cube is None:
                self._say("Je ne vois pas de cube rouge. Place-le devant moi.")
                return
            self.get_logger().info(
                f'Cube: ({cube.x},{cube.y}) {cube.width}x{cube.height}px')

            self._say("Je me place.")
            if not self._position_and_grip(calib):
                if self._abort:
                    self._say("Arrêt.")
                else:
                    self._say("Je n'ai pas reussi a me placer.")
                return

            # Avance a l'aveugle: reference -> point de grip (le point de grip
            # est sous le champ de la camera, voir pick_calib.py)
            extra = float(calib.get(pick_calib.KEY_EXTRA, 0.0))
            if extra > 0.005:
                self.get_logger().info(
                    f'Avance finale a l\'aveugle: {extra*100:.1f}cm (reference -> grip)')
                self._drive(-extra)
            if self._abort:
                self._say("Arrêt.")
                return

            self._say("J'y vais !")  # pas « attrape »/« cube »: le micro pourrait relancer la séquence
            if not self._grip(calib):
                self._say("Arrêt.")
                return
            self._say("Voilà, c'est fait !")
            self.get_logger().info('✅ Séquence terminée')
        except Exception as e:
            self.get_logger().error(f'Erreur: {e}')
            import traceback
            traceback.print_exc()
            self._say("Désolé, il y a eu un problème.")
        finally:
            self._stop()
            with self._lock:
                self._busy = False
                self._abort = False


def main(args=None):
    rclpy.init(args=args)
    node = PickAndPlaceV6()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
