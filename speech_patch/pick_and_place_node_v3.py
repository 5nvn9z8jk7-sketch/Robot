#!/usr/bin/env python3
# encoding: utf-8
"""
pick_and_place_node_v3 — Pick-and-place 360° avec positionnement intelligent.

Améliorations par rapport à v2:
  - Scan 360° pour trouver le cube (rotation par paliers de 30°)
  - Estimation de distance par taille apparente du cube dans l'image
  - Ajustement automatique de la distance (avance/recule jusqu'à bonne taille)
  - Positionnement face au cube (centrage horizontal)
  - Vérification que le cube est au sol (partie basse image)
  - Tentative de préhension dans toutes les directions

Principe de l'estimation de distance:
  - La caméra voit le cube avec une certaine taille en pixels (width x height)
  - Plus le cube est proche, plus il est grand dans l'image
  - On calibre: target_size_px = taille du cube à la distance de préhension
  - Le robot avance/recule jusqu'à ce que la taille détectée = target_size_px

Paramètres ROS2:
  - target_size_px: taille cible du cube en pixels (défaut: 80 = ~20cm)
  - gripper_reach: distance caméra-cube pour préhension (défaut: 0.18m)
  - linear_speed: vitesse avance/recule (défaut: 0.12 m/s)
  - angular_speed: vitesse rotation (défaut: 0.6 rad/s)
  - scan_step_deg: angle de scan par palier (défaut: 30°)
  - min_y_pixel: seuil Y minimum pour détection au sol (défaut: 200)
  - size_tolerance: tolérance taille en % (défaut: 15%)
"""

import math
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist

from interfaces.msg import ColorsInfo
from servo_controller_msgs.msg import ServosPosition
from servo_controller.action_group_controller import ActionGroupController

ACTION_GROUPS_PATH = '/home/ubuntu/software/arm_pc/ActionGroups'

# Paramètres par défaut
DEFAULT_TARGET_SIZE_PX = 80      # taille cible cube en pixels (~20cm de distance)
DEFAULT_GRIPPER_REACH = 0.18     # distance caméra-cube pour préhension (m)
DEFAULT_LINEAR_SPEED = 0.12      # m/s (plus lent pour précision)
DEFAULT_ANGULAR_SPEED = 0.6      # rad/s (plus lent pour précision)
DEFAULT_SCAN_STEP_DEG = 30       # degrés par palier de scan
DEFAULT_MIN_Y_PIXEL = 200        # seuil Y (partie basse = sol)
DEFAULT_SIZE_TOLERANCE = 0.15    # 15% de tolérance sur la taille

DEFAULT_FX = 423.376
DEFAULT_CX = 319.504

CMD_VEL_RATE = 0.05       # 20 Hz
ANGLE_DEADZONE = 0.03     # rad (~1.7°)
DISTANCE_DEADZONE = 0.02  # m
SCAN_TIMEOUT = 30.0       # secondes max pour le scan 360°
DETECT_TIMEOUT = 5.0
MAX_POSITIONING_ITER = 5  # iterations max pour ajuster la distance

TRIGGER_VERBS = ['attrape', 'attraper', 'ramasse', 'ramasser', 'prends', 'prendre',
                 'saisis', 'saisir', 'cherche', 'chercher', 'trouve', 'trouver',
                 'va chercher', 'va ramasser', 'pick', 'grab', 'scan', 'scane',
                 'cherche autour', 'cherche le cube']
TRIGGER_OBJECTS = ['cube', 'objet', 'balle', 'rouge', 'red', 'block', 'bloc']

TARGET_COLOR = 'red'


class PickAndPlaceNodeV3(Node):
    def __init__(self):
        super().__init__('pick_and_place_node_v3')

        # Paramètres ROS2
        self.declare_parameter('target_size_px', DEFAULT_TARGET_SIZE_PX)
        self.declare_parameter('gripper_reach', DEFAULT_GRIPPER_REACH)
        self.declare_parameter('linear_speed', DEFAULT_LINEAR_SPEED)
        self.declare_parameter('angular_speed', DEFAULT_ANGULAR_SPEED)
        self.declare_parameter('scan_step_deg', DEFAULT_SCAN_STEP_DEG)
        self.declare_parameter('min_y_pixel', DEFAULT_MIN_Y_PIXEL)
        self.declare_parameter('size_tolerance', DEFAULT_SIZE_TOLERANCE)
        self.declare_parameter('fx', DEFAULT_FX)
        self.declare_parameter('cx', DEFAULT_CX)

        self._lock = threading.Lock()
        self._busy = False
        self._abort = False
        self._latest_color_info = None

        self.cmd_vel_pub = self.create_publisher(Twist, '/controller/cmd_vel', 1)
        self.tts_pub = self.create_publisher(String, '/tts_node/tts_text', 1)

        self.arm_controller = ActionGroupController(
            self.create_publisher(ServosPosition, 'servo_controller', 1),
            ACTION_GROUPS_PATH
        )

        self.create_subscription(
            String, '/vocal_detect/asr_result', self._asr_callback, 1)
        self.create_subscription(
            ColorsInfo, '/color_detect_node/color_info', self._color_callback, 1)

        self.get_logger().info(
            f'pick_and_place_node_v3 pret (360 scan + auto-distance) — '
            f'target_size={self._get_param("target_size_px")}px, '
            f'scan_step={self._get_param("scan_step_deg")}deg')

    def _get_param(self, name):
        return self.get_parameter(name).value

    def _asr_callback(self, msg):
        text = msg.data.strip().lower()
        if not text:
            return
        self.get_logger().info(f'ASR: "{text}"')

        if not self._is_trigger(text):
            return

        with self._lock:
            if self._busy:
                self.get_logger().info('Deja en cours, ignore')
                return
            self._busy = True
            self._abort = False

        self.get_logger().info(f'Commande: "{text}"')
        threading.Thread(target=self._run_sequence, args=(text,), daemon=True).start()

    def _color_callback(self, msg):
        with self._lock:
            self._latest_color_info = msg

    def _is_trigger(self, text):
        if 'va chercher' in text or 'va ramasser' in text:
            return True
        if 'cherche' in text and ('autour' in text or 'cube' in text or 'rouge' in text):
            return True
        has_verb = any(v in text for v in TRIGGER_VERBS)
        has_object = any(o in text for o in TRIGGER_OBJECTS)
        return has_verb and has_object

    def _say(self, text):
        self.get_logger().info(f'TTS: {text}')
        msg = String()
        msg.data = text
        self.tts_pub.publish(msg)

    def _stop_robot(self):
        self.cmd_vel_pub.publish(Twist())

    # ─── Détection ───

    def _get_red_cube(self, timeout=3.0):
        """Retourne le cube rouge le plus prometteur (partie basse = sol)."""
        min_y = int(self._get_param('min_y_pixel'))
        deadline = time.time() + timeout
        best = None
        best_size = 0
        while time.time() < deadline and not self._abort:
            with self._lock:
                info = self._latest_color_info
            if info and len(info.data) > 0:
                ground_cubes = [ci for ci in info.data
                                if ci.color == TARGET_COLOR and ci.y >= min_y]
                for c in ground_cubes:
                    size = c.width * c.height
                    if size > best_size:
                        best = c
                        best_size = size
                if best is not None:
                    return best
            time.sleep(0.05)
        return best

    def _get_cube_size(self, cube):
        """Retourne la taille du cube en pixels (largeur moyenne)."""
        return (cube.width + cube.height) / 2.0

    # ─── Mouvement ───

    def _turn_to(self, angle_rad):
        """Tourne de angle_rad radians. Positif = droite."""
        angular_speed = float(self._get_param('angular_speed'))
        if abs(angle_rad) < ANGLE_DEADZONE:
            return
        duration = abs(angle_rad) / angular_speed
        self.get_logger().info(f'  Rotation {math.degrees(angle_rad):+.1f}° ({duration:.2f}s)')
        twist = Twist()
        twist.angular.z = -math.copysign(angular_speed, angle_rad)
        start = time.time()
        while time.time() - start < duration and not self._abort:
            self.cmd_vel_pub.publish(twist)
            time.sleep(CMD_VEL_RATE)
        self._stop_robot()
        time.sleep(0.2)

    def _scan_step(self, angle_deg):
        """Tourne d'un palier de scan (pour chercher le cube)."""
        angle_rad = math.radians(angle_deg)
        self._turn_to(angle_rad)

    def _drive(self, distance_m):
        """Avance (négatif) ou recule (positif) de distance_m metres."""
        linear_speed = float(self._get_param('linear_speed'))
        if abs(distance_m) < DISTANCE_DEADZONE:
            return
        duration = abs(distance_m) / linear_speed
        direction = "Avance" if distance_m < 0 else "Recule"
        self.get_logger().info(f'  {direction} {abs(distance_m):.2f}m ({duration:.2f}s)')
        twist = Twist()
        twist.linear.x = -linear_speed if distance_m < 0 else linear_speed
        start = time.time()
        while time.time() - start < duration and not self._abort:
            self.cmd_vel_pub.publish(twist)
            time.sleep(CMD_VEL_RATE)
        self._stop_robot()
        time.sleep(0.2)

    # ─── Séquence principale ───

    def _scan_for_cube(self):
        """
        Scan 360° pour trouver un cube rouge.
        Retourne le cube trouvé ou None.
        """
        scan_step = float(self._get_param('scan_step_deg'))
        self._say("Je cherche le cube rouge autour de moi.")
        self.get_logger().info(f'Scan 360° (paliers de {scan_step}°)')

        # 12 paliers de 30° = 360°
        num_steps = int(360 / scan_step)
        for step in range(num_steps):
            if self._abort:
                return None

            cube = self._get_red_cube(timeout=1.0)
            if cube is not None:
                self.get_logger().info(
                    f'  Cube trouve au scan {step+1}/{num_steps} '
                    f'({cube.x},{cube.y}, {cube.width}x{cube.height})')
                self._say("J'ai trouve le cube !")
                return cube

            self.get_logger().info(f'  Scan {step+1}/{num_steps}: rien, je continue...')
            self._scan_step(scan_step)

        self.get_logger().warn('Scan 360° termine, aucun cube trouve')
        return None

    def _center_cube(self, cube):
        """Tourne pour centrer le cube horizontalement dans l'image."""
        fx = float(self._get_param('fx'))
        cx = float(self._get_param('cx'))
        angle_rad = math.atan2(cube.x - cx, fx)
        angle_deg = math.degrees(angle_rad)
        self.get_logger().info(f'Centrage: cube a {angle_deg:+.1f}° de l\'axe')

        if abs(angle_rad) >= ANGLE_DEADZONE:
            self._say("Je me tourne vers le cube.")
            self._turn_to(angle_rad)
            time.sleep(0.3)
            # Re-detecter
            new_cube = self._get_red_cube(timeout=2.0)
            if new_cube is not None:
                cube = new_cube
                # Re-centrer si nécessaire
                angle_rad = math.atan2(cube.x - cx, fx)
                if abs(angle_rad) >= ANGLE_DEADZONE:
                    self._turn_to(angle_rad)
                    time.sleep(0.3)
                    cube = self._get_red_cube(timeout=2.0) or cube
        return cube

    def _adjust_distance(self, cube):
        """
        Ajuste la distance au cube en fonction de sa taille apparente.
        Avance si le cube est trop petit (loin), recule s'il est trop grand (proche).
        Retourne le cube à la bonne distance ou None si échec.
        """
        target_size = float(self._get_param('target_size_px'))
        tolerance = float(self._get_param('size_tolerance'))
        linear_speed = float(self._get_param('linear_speed'))

        for iteration in range(MAX_POSITIONING_ITER):
            if self._abort:
                return None

            cube = self._get_red_cube(timeout=2.0)
            if cube is None:
                self.get_logger().warn('Cube perdu pendant ajustement')
                return None

            current_size = self._get_cube_size(cube)
            ratio = current_size / target_size
            self.get_logger().info(
                f'  Iteration {iteration+1}: taille={current_size:.0f}px '
                f'(cible={target_size:.0f}px, ratio={ratio:.2f})')

            # Dans la zone de tolérance ?
            if 1.0 - tolerance <= ratio <= 1.0 + tolerance:
                self.get_logger().info('  Distance OK !')
                return cube

            # Calculer le déplacement nécessaire
            # Hypothèse: taille ~ 1/distance (plus proche = plus gros)
            # Si ratio > 1 (trop gros/proche) → reculer
            # Si ratio < 1 (trop petit/loin) → avancer
            # Déplacement estimé: proportionnel à l'écart
            if ratio > 1.0:
                # Trop proche, reculer
                # delta_distance ≈ gripper_reach * (ratio - 1) / ratio
                gripper_reach = float(self._get_param('gripper_reach'))
                delta = gripper_reach * (ratio - 1.0) / ratio
                delta = min(delta, 0.15)  # max 15cm par iteration
                self._say("Je recule un peu.")
                self._drive(delta)  # positif = reculer
            else:
                # Trop loin, avancer
                gripper_reach = float(self._get_param('gripper_reach'))
                delta = gripper_reach * (1.0 - ratio)
                delta = min(delta, 0.15)  # max 15cm par iteration
                self._say("J'avance vers le cube.")
                self._drive(-delta)  # négatif = avancer

            time.sleep(0.3)

        self.get_logger().warn('Ajustement distance: max iterations atteint')
        # On tente quand même
        return self._get_red_cube(timeout=2.0)

    def _run_sequence(self, voice_text):
        """
        Séquence complète v3:
        1. Scan 360° pour trouver le cube
        2. Centrer le cube (rotation)
        3. Ajuster la distance (avance/recule selon taille apparente)
        4. Vérifier alignement final
        5. Préhension
        """
        try:
            is_scan = 'cherche' in voice_text and ('autour' in voice_text or 'cube' in voice_text)

            # 1. Trouver le cube (scan 360° si demandé, sinon détection directe)
            if is_scan:
                cube = self._scan_for_cube()
            else:
                self._say("Je cherche le cube rouge.")
                cube = self._get_red_cube(timeout=DETECT_TIMEOUT)

            if cube is None:
                self._say("Je ne vois pas de cube rouge. Place-le devant moi et reessaie.")
                return

            self.get_logger().info(
                f'Cube detecte: ({cube.x},{cube.y}), {cube.width}x{cube.height}px')

            # 2. Centrer le cube
            cube = self._center_cube(cube)
            if cube is None:
                self._say("J'ai perdu le cube. Reessaie.")
                return

            # 3. Ajuster la distance
            cube = self._adjust_distance(cube)
            if cube is None:
                self._say("Je n'arrive pas a me placer correctement. Reessaie.")
                return

            # 4. Vérification finale
            final_size = self._get_cube_size(cube)
            target_size = float(self._get_param('target_size_px'))
            self.get_logger().info(
                f'Position finale: cube ({cube.x},{cube.y}), '
                f'taille={final_size:.0f}px (cible={target_size:.0f}px)')

            # 5. Préhension
            self._say("J'attrape le cube !")
            self.get_logger().info('Execution action voice_pick...')
            self.arm_controller.run_action('voice_pick')
            time.sleep(5.0)

            self._say("Voila, j'ai attrape le cube !")
            self.get_logger().info('Sequence terminee avec succes')

        except Exception as e:
            self.get_logger().error(f'Erreur: {e}')
            import traceback
            traceback.print_exc()
            self._say("Desole, il y a eu un probleme.")
        finally:
            self._stop_robot()
            with self._lock:
                self._busy = False
                self._abort = False

    def request_abort(self):
        with self._lock:
            self._abort = True


def main(args=None):
    rclpy.init(args=args)
    node = PickAndPlaceNodeV3()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
