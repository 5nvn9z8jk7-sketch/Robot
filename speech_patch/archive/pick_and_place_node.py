#!/usr/bin/env python3
# encoding: utf-8
"""
pick_and_place_node — Detection + navigation + prehension d'un cube colore.

Ecoute les commandes vocales 'attrape le cube rouge', 'va chercher le cube', etc.
Detecte le cube via color_detect_node, recupere la profondeur via la camera depth,
navigue vers le cube (rotation + avance), puis execute l'action de prehension voice_pick.
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

LINEAR_SPEED = 0.15       # m/s
ANGULAR_SPEED = 0.8       # rad/s
CMD_VEL_RATE = 0.05       # 20 Hz
GRIPPER_REACH = 0.18      # distance cible camera-cube pour la prehension (m)
TARGET_DISTANCE = 0.18    # idem

DEFAULT_FX = 423.376
DEFAULT_FY = 424.174
DEFAULT_CX = 319.504
DEFAULT_CY = 201.658

MIN_DEPTH_MM = 250
MAX_DEPTH_MM = 4000
DETECT_TIMEOUT = 5.0
MIN_Y_PIXEL = 250         # only accept detections in lower part of image (ground level)
MIN_CUBE_DEPTH_MM = 250   # reject detections closer than 25cm (robot's own body)
ANGLE_DEADZONE = 0.03     # rad (~1.7 deg)
DISTANCE_DEADZONE = 0.03  # m

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

        self.get_logger().info('pick_and_place_node pret (avec navigation)')

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

    def _depth_callback(self, msg):
        try:
            depth = np.frombuffer(msg.data, dtype=np.uint16).reshape(msg.height, msg.width)
            with self._lock:
                self._latest_depth_image = depth.copy()
                self._depth_frames += 1
                if self._depth_frames % 60 == 1:
                    valid = depth[depth > 0]
                    self.get_logger().info(
                        f'Depth #{self._depth_frames}: {msg.width}x{msg.height}, '
                        f'valid={len(valid)}/{depth.size}')
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
                    f'Camera: fx={self._fx:.1f} fy={self._fy:.1f} '
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
        """Retourne le cube rouge avec Y dans la partie basse de l'image (sol).
        Rejette les detections trop proches (corps du robot) et trop hautes (pas au sol)."""
        deadline = time.time() + timeout
        while time.time() < deadline and not self._abort:
            with self._lock:
                info = self._latest_color_info
            if info and len(info.data) > 0:
                # Only accept ground-level detections (lower part of image)
                ground_cubes = [ci for ci in info.data
                                if ci.color == TARGET_COLOR and ci.y >= MIN_Y_PIXEL]
                if ground_cubes:
                    cube = ground_cubes[0]
                    # Reject detections too close (robot's own body)
                    depth_mm = self._get_depth_at(cube.x, cube.y)
                    if depth_mm is not None and depth_mm < MIN_CUBE_DEPTH_MM:
                        self.get_logger().info(
                            f'Detection rouge a ({cube.x},{cube.y}) trop proche '
                            f'({depth_mm:.0f}mm), probablement le robot — ignore')
                        time.sleep(0.2)
                        continue
                    return cube
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
        """Tourne le robot de angle_rad radians. Positif = tourner a droite."""
        if abs(angle_rad) < ANGLE_DEADZONE:
            self.get_logger().info(f'Angle trop faible ({math.degrees(angle_rad):.1f} deg)')
            return
        duration = abs(angle_rad) / ANGULAR_SPEED
        self.get_logger().info(
            f'Rotation: {math.degrees(angle_rad):.1f} deg en {duration:.2f}s')
        twist = Twist()
        # Positif angle_rad = cube a droite = tourner a droite = angular.z negatif
        twist.angular.z = -math.copysign(ANGULAR_SPEED, angle_rad)
        start = time.time()
        while time.time() - start < duration and not self._abort:
            self.cmd_vel_pub.publish(twist)
            time.sleep(CMD_VEL_RATE)
        self._stop_robot()
        time.sleep(0.3)

    def _drive_forward(self, distance_m):
        """Avance le robot de distance_m metres."""
        if distance_m < DISTANCE_DEADZONE:
            self.get_logger().info(f'Distance trop faible ({distance_m:.2f}m)')
            return
        duration = distance_m / LINEAR_SPEED
        self.get_logger().info(f'Avance: {distance_m:.2f}m en {duration:.2f}s')
        twist = Twist()
        twist.linear.x = LINEAR_SPEED
        start = time.time()
        while time.time() - start < duration and not self._abort:
            self.cmd_vel_pub.publish(twist)
            time.sleep(CMD_VEL_RATE)
        self._stop_robot()
        time.sleep(0.3)

    def _navigate_to_cube(self, cube, max_iterations=5):
        """
        Navigue vers le cube detecte. Retourne True si le cube est a portee de prehension.
        Boucle: detecte -> centre -> avance -> re-evalue.
        """
        for iteration in range(max_iterations):
            if self._abort:
                return False

            # 1. Lire la profondeur au centre du cube (avec retry)
            depth_mm = None
            for retry in range(3):
                depth_mm = self._get_depth_at(cube.x, cube.y)
                if depth_mm is not None:
                    break
                time.sleep(0.2)

            if depth_mm is None:
                self.get_logger().warn(
                    f'Pas de profondeur au pixel ({cube.x},{cube.y}), nouvelle detection...')
                time.sleep(0.3)
                cube = self._get_red_cube(timeout=2.0)
                if cube is None:
                    self.get_logger().warn('Cube perdu, abandon navigation')
                    return False
                continue

            # Rejeter les detections trop proches (corps du robot)
            if depth_mm < MIN_CUBE_DEPTH_MM:
                self.get_logger().warn(
                    f'Cube a {depth_mm:.0f}mm, trop proche (corps du robot?), '
                    f'nouvelle detection...')
                time.sleep(0.3)
                cube = self._get_red_cube(timeout=2.0)
                if cube is None:
                    return False
                continue

            distance_m = depth_mm / 1000.0
            self.get_logger().info(
                f'Iteration {iteration+1}: cube a ({cube.x},{cube.y}), '
                f'distance={distance_m:.3f}m')

            # 2. Calculer l'angle horizontal pour centrer le cube
            # angle = atan2(x - cx, fx) : positif si le cube est a droite
            angle_rad = math.atan2(cube.x - self._cx, self._fx)
            self.get_logger().info(
                f'Angle horizontal: {math.degrees(angle_rad):.1f} deg')

            # 3. Tourner pour centrer le cube
            if abs(angle_rad) >= ANGLE_DEADZONE:
                self._say("Je tourne vers le cube.")
                self._turn_to(angle_rad)
                # Re-detecter apres le mouvement
                time.sleep(0.5)
                new_cube = self._get_red_cube(timeout=2.0)
                if new_cube is not None:
                    cube = new_cube

            # 4. Calculer la distance a parcourir
            # Re-lire la profondeur apres la rotation
            depth_mm = self._get_depth_at(cube.x, cube.y)
            if depth_mm is None:
                self.get_logger().warn('Profondeur perdue apres rotation, nouvelle detection...')
                cube = self._get_red_cube(timeout=2.0)
                if cube is None:
                    return False
                depth_mm = self._get_depth_at(cube.x, cube.y)
                if depth_mm is None:
                    return False

            distance_m = depth_mm / 1000.0
            distance_to_drive = distance_m - GRIPPER_REACH
            self.get_logger().info(
                f'Distance a parcourir: {distance_to_drive:.3f}m '
                f'(cube a {distance_m:.3f}m, cible {GRIPPER_REACH}m)')

            if distance_to_drive > DISTANCE_DEADZONE:
                self._say("J'avance vers le cube.")
                self._drive_forward(distance_to_drive)

            # 5. Re-evaluer apres le mouvement
            time.sleep(0.5)
            cube = self._get_red_cube(timeout=2.0)
            if cube is None:
                self.get_logger().warn('Cube perdu apres mouvement, on tente la prehension')
                return True  # on tente quand meme

            # Verifier si on est assez proche
            depth_mm = self._get_depth_at(cube.x, cube.y)
            if depth_mm is not None:
                new_distance = depth_mm / 1000.0
                self.get_logger().info(f'Nouvelle distance: {new_distance:.3f}m')
                if new_distance <= GRIPPER_REACH + 0.05:
                    self.get_logger().info('Cube a portee de prehension!')
                    return True

        self.get_logger().warn('Nombre max d iterations atteint')
        return True  # on tente quand meme la prehension

    def _run_sequence(self, voice_text):
        """
        Sequence complete: detection -> navigation -> prehension.
        """
        try:
            self._say("Je cherche le cube rouge.")

            # 1. Detecter le cube rouge
            cube = self._get_red_cube(timeout=DETECT_TIMEOUT)
            if cube is None:
                self.get_logger().warn('Aucun cube rouge detecte')
                self._say("Je ne vois pas de cube rouge. Place-le devant moi et reessaie.")
                return

            depth_mm = self._get_depth_at(cube.x, cube.y)
            if depth_mm:
                self.get_logger().info(
                    f'Cube rouge detecte a ({cube.x},{cube.y}), '
                    f'profondeur={depth_mm:.0f}mm ({depth_mm/1000:.2f}m)')
            else:
                self.get_logger().info(
                    f'Cube rouge detecte a ({cube.x},{cube.y}), pas de profondeur')

            # 2. Naviguer vers le cube
            self.get_logger().info('Debut de la navigation vers le cube...')
            reached = self._navigate_to_cube(cube)

            if self._abort:
                self._say("J'ai annule.")
                return

            # 3. Executer la prehension
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
