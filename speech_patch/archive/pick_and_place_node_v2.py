#!/usr/bin/env python3
# encoding: utf-8
"""
pick_and_place_node_v2 — Version SANS caméra depth requise.

Utilise une distance fixe configurable pour avancer vers le cube.
Paramètres ROS2 ajustables en temps réel:
  - fixed_distance_m: distance à parcourir après centrage (défaut: 0.25m)
  - gripper_reach: distance cible caméra-cube pour préhension (défaut: 0.15m)
  - linear_speed: vitesse d'avance (défaut: 0.15 m/s)
  - angular_speed: vitesse de rotation (défaut: 0.8 rad/s)
  - min_y_pixel: seuil Y minimum pour accepter une détection (défaut: 200)

Usage:
  ros2 run speech_patch pick_and_place_node_v2 --ros-args -p fixed_distance_m:=0.30

Ou ajuster en temps réel:
  ros2 param set /pick_and_place_node_v2 fixed_distance_m 0.35
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

# Paramètres par défaut (modifiables via ROS2 params)
DEFAULT_FIXED_DISTANCE_M = 0.25   # distance fixe à avancer après centrage
DEFAULT_GRIPPER_REACH = 0.15      # distance caméra-cube pour préhension
DEFAULT_LINEAR_SPEED = 0.15       # m/s
DEFAULT_ANGULAR_SPEED = 0.8       # rad/s
DEFAULT_MIN_Y_PIXEL = 200         # seuil Y minimum (partie basse image = sol)

DEFAULT_FX = 423.376
DEFAULT_CX = 319.504

CMD_VEL_RATE = 0.05       # 20 Hz
ANGLE_DEADZONE = 0.03     # rad (~1.7 deg)
DISTANCE_DEADZONE = 0.03  # m
DETECT_TIMEOUT = 5.0

TRIGGER_VERBS = ['attrape', 'attraper', 'ramasse', 'ramasser', 'prends', 'prendre',
                 'saisis', 'saisir', 'cherche', 'chercher', 'trouve', 'trouver',
                 'va chercher', 'va ramasser', 'pick', 'grab']
TRIGGER_OBJECTS = ['cube', 'objet', 'balle', 'rouge', 'red', 'block', 'bloc', 'rouge']

TARGET_COLOR = 'red'


class PickAndPlaceNodeV2(Node):
    def __init__(self):
        super().__init__('pick_and_place_node_v2')

        # Paramètres ROS2 configurables
        self.declare_parameter('fixed_distance_m', DEFAULT_FIXED_DISTANCE_M)
        self.declare_parameter('gripper_reach', DEFAULT_GRIPPER_REACH)
        self.declare_parameter('linear_speed', DEFAULT_LINEAR_SPEED)
        self.declare_parameter('angular_speed', DEFAULT_ANGULAR_SPEED)
        self.declare_parameter('min_y_pixel', DEFAULT_MIN_Y_PIXEL)
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
            f'pick_and_place_node_v2 pret (sans depth) — '
            f'fixed_distance={self._get_param("fixed_distance_m")}m, '
            f'gripper_reach={self._get_param("gripper_reach")}m')

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

        self.get_logger().info(f'Commande pick and place: "{text}"')
        threading.Thread(target=self._run_sequence, args=(text,), daemon=True).start()

    def _color_callback(self, msg):
        with self._lock:
            self._latest_color_info = msg

    def _is_trigger(self, text):
        if 'va chercher' in text or 'va ramasser' in text:
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

    def _get_red_cube(self, timeout=5.0):
        """Retourne le cube rouge détecté en partie basse de l'image (sol)."""
        min_y = int(self._get_param('min_y_pixel'))
        deadline = time.time() + timeout
        while time.time() < deadline and not self._abort:
            with self._lock:
                info = self._latest_color_info
            if info and len(info.data) > 0:
                ground_cubes = [ci for ci in info.data
                                if ci.color == TARGET_COLOR and ci.y >= min_y]
                if ground_cubes:
                    # Prendre le plus grand (le plus proche généralement)
                    cube = max(ground_cubes, key=lambda c: c.width * c.height)
                    return cube
            time.sleep(0.1)
        return None

    def _turn_to(self, angle_rad):
        """Tourne le robot de angle_rad radians."""
        angular_speed = float(self._get_param('angular_speed'))
        if abs(angle_rad) < ANGLE_DEADZONE:
            self.get_logger().info(f'Angle trop faible ({math.degrees(angle_rad):.1f} deg)')
            return
        duration = abs(angle_rad) / angular_speed
        self.get_logger().info(
            f'Rotation: {math.degrees(angle_rad):.1f} deg en {duration:.2f}s')
        twist = Twist()
        twist.angular.z = -math.copysign(angular_speed, angle_rad)
        start = time.time()
        while time.time() - start < duration and not self._abort:
            self.cmd_vel_pub.publish(twist)
            time.sleep(CMD_VEL_RATE)
        self._stop_robot()
        time.sleep(0.3)

    def _drive_forward(self, distance_m):
        """Avance le robot de distance_m metres."""
        linear_speed = float(self._get_param('linear_speed'))
        if distance_m < DISTANCE_DEADZONE:
            self.get_logger().info(f'Distance trop faible ({distance_m:.2f}m)')
            return
        duration = distance_m / linear_speed
        self.get_logger().info(f'Avance: {distance_m:.2f}m en {duration:.2f}s')
        twist = Twist()
        twist.linear.x = linear_speed
        start = time.time()
        while time.time() - start < duration and not self._abort:
            self.cmd_vel_pub.publish(twist)
            time.sleep(CMD_VEL_RATE)
        self._stop_robot()
        time.sleep(0.3)

    def _run_sequence(self, voice_text):
        """
        Sequence complete sans depth: detection -> centrage -> avance fixe -> prehension.
        """
        try:
            self._say("Je cherche le cube rouge.")

            # 1. Detecter le cube rouge
            cube = self._get_red_cube(timeout=DETECT_TIMEOUT)
            if cube is None:
                self.get_logger().warn('Aucun cube rouge detecte')
                self._say("Je ne vois pas de cube rouge. Place-le devant moi et reessaie.")
                return

            self.get_logger().info(
                f'Cube rouge detecte a ({cube.x},{cube.y}), '
                f'taille={cube.width}x{cube.height}')

            # 2. Centrer le cube (rotation)
            fx = float(self._get_param('fx'))
            cx = float(self._get_param('cx'))
            angle_rad = math.atan2(cube.x - cx, fx)
            self.get_logger().info(
                f'Angle horizontal: {math.degrees(angle_rad):.1f} deg')

            if abs(angle_rad) >= ANGLE_DEADZONE:
                self._say("Je tourne vers le cube.")
                self._turn_to(angle_rad)
                time.sleep(0.5)
                # Re-detecter apres rotation
                cube = self._get_red_cube(timeout=2.0)
                if cube is not None:
                    angle_rad = math.atan2(cube.x - cx, fx)
                    if abs(angle_rad) >= ANGLE_DEADZONE:
                        self._turn_to(angle_rad)
                        time.sleep(0.3)

            # 3. Avancer d'une distance fixe
            fixed_distance = float(self._get_param('fixed_distance_m'))
            gripper_reach = float(self._get_param('gripper_reach'))
            distance_to_drive = fixed_distance - gripper_reach

            self.get_logger().info(
                f'Distance fixe: {fixed_distance:.2f}m, '
                f'gripper_reach: {gripper_reach:.2f}m, '
                f'a parcourir: {distance_to_drive:.2f}m')

            if distance_to_drive > DISTANCE_DEADZONE:
                self._say("J'avance vers le cube.")
                self._drive_forward(distance_to_drive)
            else:
                self.get_logger().info('Distance fixe deja atteinte ou negative')

            # 4. Executer la prehension
            self._say("J'attrape le cube !")
            self.get_logger().info('Execution action voice_pick...')
            self.arm_controller.run_action('voice_pick')
            time.sleep(5.0)

            self._say("Voila, j'ai attrape le cube !")
            self.get_logger().info('Sequence terminee avec succes')

        except Exception as e:
            self.get_logger().error(f'Erreur sequence: {e}')
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
    node = PickAndPlaceNodeV2()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
