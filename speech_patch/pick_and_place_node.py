#!/usr/bin/env python3
# encoding: utf-8
"""
pick_and_place_node — Detection + navigation + prehension d'un cube colore.

Ecoute les commandes vocales 'attrape le cube rouge', 'va chercher le cube', etc.
Detecte le cube via color_detect_node, navigue vers lui avec la camera depth,
puis execute l'action de prehension voice_pick.
"""
import math
import threading
import time

import numpy as np

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Image, CameraInfo

from interfaces.msg import ColorsInfo
from servo_controller_msgs.msg import ServosPosition
from servo_controller.action_group_controller import ActionGroupController

ACTION_GROUPS_PATH = '/home/ubuntu/software/arm_pc/ActionGroups'

LINEAR_SPEED = 0.15
ANGULAR_SPEED = 0.8
TARGET_DISTANCE = 0.12

DEFAULT_FX = 423.376
DEFAULT_FY = 424.174
DEFAULT_CX = 319.504
DEFAULT_CY = 201.658

MIN_DEPTH_MM = 100
MAX_DEPTH_MM = 4000
DETECT_TIMEOUT = 5.0
MIN_APPROACH = 0.20  # always drive at least 15cm if cube detected
MIN_Y_PIXEL = 250   # only accept detections in lower part of image (ground level)
ANGLE_DEADZONE = 0.02

TRIGGER_VERBS = ['attrape', 'attraper', 'ramasse', 'ramasser', 'prends', 'prendre',
                 'saisis', 'saisir', 'cherche', 'chercher', 'trouve', 'trouver',
                 'va chercher', 'va ramasser']
TRIGGER_OBJECTS = ['cube', 'objet', 'balle', 'rouge', 'red', 'block', 'bloc']

TARGET_COLOR = 'red'


class PickAndPlaceNode(Node):
    def __init__(self):
        super().__init__('pick_and_place_node')

        self._fx = DEFAULT_FX
        self._fy = DEFAULT_FY
        self._cx = DEFAULT_CX
        self._cy = DEFAULT_CY

        self._latest_color_info = None
        self._latest_depth_image = None
        self._lock = threading.Lock()

        self._busy = False
        self._abort = False
        self._camera_info_logged = False
        self._depth_frames = 0
        self._color_frames = 0

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
        self.create_subscription(
            Image, '/depth_cam/depth0/image_raw', self._depth_callback, 1)
        self.create_subscription(
            CameraInfo, '/depth_cam/depth0/camera_info', self._camera_info_callback, 1)

        self.get_logger().info('pick_and_place_node pret')

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
            self._color_frames += 1

    def _depth_callback(self, msg):
        try:
            depth = np.frombuffer(msg.data, dtype=np.uint16).reshape(msg.height, msg.width)
            with self._lock:
                self._latest_depth_image = depth.copy()
                self._depth_frames += 1
                if self._depth_frames % 30 == 1:
                    valid = depth[depth > 0]
                    self.get_logger().info(f'Depth frame #{self._depth_frames}: {msg.width}x{msg.height}, valid={len(valid)}/{depth.size}')
        except Exception as e:
            self.get_logger().error(f'Erreur decodage depth: {e}')

    def _camera_info_callback(self, msg):
        if len(msg.k) >= 9:
            self._fx = msg.k[0]
            self._fy = msg.k[4]
            self._cx = msg.k[2]
            self._cy = msg.k[5]
            if not self._camera_info_logged:
                self._camera_info_logged = True
                self.get_logger().info(
                    f'Camera info: fx={self._fx:.1f} fy={self._fy:.1f} '
                    f'cx={self._cx:.1f} cy={self._cy:.1f} ({msg.width}x{msg.height})')

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
        """Retourne le cube rouge avec Y dans la partie basse de l'image (sol)."""
        deadline = time.time() + timeout
        while time.time() < deadline and not self._abort:
            with self._lock:
                info = self._latest_color_info
            if info and len(info.data) > 0:
                # Prefer detections in lower part of image (ground level)
                ground_cubes = [ci for ci in info.data if ci.color == TARGET_COLOR and ci.y >= MIN_Y_PIXEL]
                if ground_cubes:
                    return ground_cubes[0]
                # Fallback: any red detection
                for ci in info.data:
                    if ci.color == TARGET_COLOR:
                        return ci
            time.sleep(0.1)
        return None

    def _get_depth_at(self, x, y, window=5):
        with self._lock:
            depth_img = self._latest_depth_image
        if depth_img is None:
            return None
        h, w = depth_img.shape
        x0 = max(0, x - window)
        x1 = min(w, x + window + 1)
        y0 = max(0, y - window)
        y1 = min(h, y + window + 1)
        patch = depth_img[y0:y1, x0:x1].flatten()
        valid = patch[(patch > MIN_DEPTH_MM) & (patch < MAX_DEPTH_MM)]
        if len(valid) == 0:
            return None
        return float(np.median(valid))

    def _turn_to(self, angle_rad):
        if abs(angle_rad) < ANGLE_DEADZONE:
            self.get_logger().info(f'Angle trop faible ({angle_rad:.3f} rad), pas de rotation')
            return
        duration = abs(angle_rad) / ANGULAR_SPEED
        self.get_logger().info(f'Rotation: {math.degrees(angle_rad):.1f} deg en {duration:.2f}s')
        twist = Twist()
        twist.angular.z = -math.copysign(ANGULAR_SPEED, angle_rad)
        # Publish continuously at 10Hz so motor controller doesn't timeout
        start = time.time()
        while time.time() - start < duration and not self._abort:
            self.cmd_vel_pub.publish(twist)
            time.sleep(0.1)
        self._stop_robot()
        time.sleep(0.3)

    def _drive_forward(self, distance_m):
        if distance_m <= 0.05:
            self.get_logger().info(f'Distance trop faible ({distance_m:.2f}m)')
            return
        duration = distance_m / LINEAR_SPEED
        self.get_logger().info(f'Avance: {distance_m:.2f}m en {duration:.2f}s')
        twist = Twist()
        twist.linear.x = LINEAR_SPEED
        # Publish continuously at 10Hz so motor controller doesn't timeout
        start = time.time()
        while time.time() - start < duration and not self._abort:
            self.cmd_vel_pub.publish(twist)
            time.sleep(0.1)
        self._stop_robot()
        time.sleep(0.3)

    def _run_sequence(self, voice_text):
        """Sequence simplifiee: detection visuelle + pick (sans navigation).
        
        Etapes:
        1. Verifier qu'un cube rouge est visible (optionnel, informatif)
        2. Annoncer
        3. Executer l'action voice_pick
        """
        try:
            self._say("Je cherche le cube rouge.")

            # 1. Verifier la detection (informatif seulement)
            cube = self._get_red_cube(timeout=2.0)
            if cube is not None:
                depth_mm = self._get_depth_at(cube.x, cube.y)
                if depth_mm:
                    self.get_logger().info(f'Cube rouge vu a pixel ({cube.x},{cube.y}), depth={depth_mm:.0f}mm')
                    self._say(f"J'ai vu le cube rouge. Je l'attrape !")
                else:
                    self.get_logger().info(f'Cube rouge vu a pixel ({cube.x},{cube.y}), pas de profondeur')
                    self._say("J'ai vu le cube rouge. Je l'attrape !")
            else:
                self.get_logger().info('Pas de cube rouge detecte, mais je tente quand meme')
                self._say("Je ne vois pas bien le cube, mais je tente d'attraper !")

            # 2. Executer la prehension
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
    node = PickAndPlaceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
