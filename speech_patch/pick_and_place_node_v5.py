#!/usr/bin/env python3
# encoding: utf-8
"""
pick_and_place_node_v5 — Pick-and-place 360° avec caméra DEPTH + préhension au sol corrigée.

Améliorations par rapport à v3:
  - Utilise la vraie caméra depth (/depth_cam/depth0/image_raw)
  - Distance mesurée au millimètre près (vs estimation par taille en v3)
  - Fallback sur estimation par taille si pas de depth disponible
  - Même scan 360° + centrage + ajustement

La caméra depth donne une image où chaque pixel = distance en mm.
Le robot lit la profondeur au centre du cube détecté et avance/recule
jusqu'à atteindre exactement gripper_reach (±2cm).

Topics utilisés:
  - /depth_cam/depth0/image_raw  (sensor_msgs/Image, uint16, mm)
  - /depth_cam/depth0/camera_info (pour focale fx, fy, cx, cy)
  - /color_detect_node/color_info (détection couleur rouge)
  - /vocal_detect/asr_result     (commandes vocales)

Paramètres ROS2:
  - gripper_reach: distance cible caméra-cube (défaut: 0.18m = 18cm)
  - linear_speed: vitesse avance/recule (défaut: 0.10 m/s, lent pour précision)
  - angular_speed: vitesse rotation (défaut: 0.5 rad/s)
  - scan_step_deg: angle scan par palier (défaut: 30°)
  - min_y_pixel: seuil Y détection sol (défaut: 200)
  - target_size_px: taille cible fallback si pas de depth (défaut: 80px)
  - distance_tolerance: tolérance distance en m (défaut: 0.02 = 2cm)
  - use_depth: utiliser depth si disponible (défaut: true)
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
from servo_controller.bus_servo_control import set_servo_position
from servo_controller_msgs.msg import ServoPosition

ACTION_GROUPS_PATH = '/home/ubuntu/software/arm_pc/ActionGroups'

# Paramètres par défaut
DEFAULT_GRIPPER_REACH = 0.18     # distance cible caméra-cube (m)
DEFAULT_LINEAR_SPEED = 0.10      # m/s (lent pour précision)
DEFAULT_ANGULAR_SPEED = 0.5      # rad/s
DEFAULT_SCAN_STEP_DEG = 30       # degrés
DEFAULT_MIN_Y_PIXEL = 0          # seuil Y min (0 = accepte tous les cubes)
DEFAULT_TARGET_SIZE_PX = 80      # fallback: taille cible en pixels
DEFAULT_DISTANCE_TOLERANCE = 0.02  # ±2cm
DEFAULT_USE_DEPTH = True         # utiliser depth si disponible
DEFAULT_CAM_TO_GRIPPER = 0.10    # offset camera -> pince (m)

DEFAULT_FX = 211.688
DEFAULT_FY = 212.087
DEFAULT_CX = 159.752
DEFAULT_CY = 100.829

MIN_DEPTH_MM = 100       # profondeur min valide (10cm)
MAX_DEPTH_MM = 4000      # profondeur max valide (4m)

CMD_VEL_RATE = 0.05       # 20 Hz
ANGLE_DEADZONE = 0.02     # rad (~1.1°)
DISTANCE_DEADZONE = 0.015 # m (1.5cm)
SCAN_TIMEOUT = 30.0
DETECT_TIMEOUT = 5.0
MAX_POSITIONING_ITER = 8  # plus d'itérations car ajustements fins

TRIGGER_VERBS = ['attrape', 'attraper', 'ramasse', 'ramasser', 'prends', 'prendre',
                 'saisis', 'saisir', 'cherche', 'chercher', 'trouve', 'trouver',
                 'va chercher', 'va ramasser', 'pick', 'grab', 'scan', 'scane']
TRIGGER_OBJECTS = ['cube', 'objet', 'balle', 'rouge', 'red', 'block', 'bloc']

TARGET_COLOR = 'red'


class PickAndPlaceNodeV4(Node):
    def __init__(self):
        super().__init__('pick_and_place_node_v5')

        # Paramètres ROS2
        self.declare_parameter('gripper_reach', DEFAULT_GRIPPER_REACH)
        self.declare_parameter('linear_speed', DEFAULT_LINEAR_SPEED)
        self.declare_parameter('angular_speed', DEFAULT_ANGULAR_SPEED)
        self.declare_parameter('scan_step_deg', DEFAULT_SCAN_STEP_DEG)
        self.declare_parameter('min_y_pixel', DEFAULT_MIN_Y_PIXEL)
        self.declare_parameter('target_size_px', DEFAULT_TARGET_SIZE_PX)
        self.declare_parameter('distance_tolerance', DEFAULT_DISTANCE_TOLERANCE)
        self.declare_parameter('use_depth', DEFAULT_USE_DEPTH)
        self.declare_parameter('camera_to_gripper_offset', 0.10)  # distance camera -> pince (m)
        self.declare_parameter('use_custom_grip', True)  # sequence servo directe au lieu de voice_pick
        self.declare_parameter('fx', DEFAULT_FX)
        self.declare_parameter('fy', DEFAULT_FY)
        self.declare_parameter('cx', DEFAULT_CX)
        self.declare_parameter('cy', DEFAULT_CY)

        self._lock = threading.Lock()
        self._busy = False
        self._abort = False
        self._latest_color_info = None
        self._latest_depth_image = None
        self._depth_frames = 0
        self._depth_available = False

        self.cmd_vel_pub = self.create_publisher(Twist, '/controller/cmd_vel', 1)
        self.tts_pub = self.create_publisher(String, '/tts_node/tts_text', 1)

        self.arm_controller = ActionGroupController(
            self.create_publisher(ServosPosition, 'servo_controller', 1),
            ACTION_GROUPS_PATH
        )

        # Subscriptions
        self.create_subscription(
            String, '/vocal_detect/asr_result', self._asr_callback, 1)
        self.create_subscription(
            ColorsInfo, '/color_detect_node/color_info', self._color_callback, 1)
        self.create_subscription(
            Image, '/depth_cam/depth0/image_raw', self._depth_callback, 1)
        self.create_subscription(
            CameraInfo, '/depth_cam/depth0/camera_info', self._camera_info_callback, 1)

        use_depth = self._get_param('use_depth')
        self.get_logger().info(
            f'pick_and_place_node_v5 pret (depth + 360 scan + grip sol) — '
            f'gripper_reach={self._get_param("gripper_reach")}m, '
            f'cam_offset={self._get_param("camera_to_gripper_offset")}m, '
            f'use_depth={use_depth}, custom_grip={self._get_param("use_custom_grip")}')

    def _get_param(self, name):
        return self.get_parameter(name).value

    # ─── Callbacks ───

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

    def _depth_callback(self, msg):
        try:
            depth = np.frombuffer(msg.data, dtype=np.uint16).reshape(msg.height, msg.width)
            with self._lock:
                self._latest_depth_image = depth.copy()
                self._depth_frames += 1
                if not self._depth_available:
                    self._depth_available = True
                    self.get_logger().info(
                        f'✅ Depth camera active: {msg.width}x{msg.height}')
        except Exception as e:
            self.get_logger().error(f'Erreur depth: {e}')

    def _camera_info_callback(self, msg):
        if len(msg.k) >= 9:
            self.set_parameters([
                rclpy.parameter.Parameter('fx', rclpy.Parameter.Type.DOUBLE, msg.k[0]),
                rclpy.parameter.Parameter('fy', rclpy.Parameter.Type.DOUBLE, msg.k[4]),
                rclpy.parameter.Parameter('cx', rclpy.Parameter.Type.DOUBLE, msg.k[2]),
                rclpy.parameter.Parameter('cy', rclpy.Parameter.Type.DOUBLE, msg.k[5]),
            ])

    def _is_trigger(self, text):
        if 'va chercher' in text or 'va ramasser' in text:
            return True
        if 'cherche' in text and ('autour' in text or 'cube' in text):
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
                if not ground_cubes and info.data:
                    c0 = info.data[0]
                    self.get_logger().info(
                        f'  Filtre: {len(info.data)} objets, min_y={min_y}, '
                        f'premier y={c0.y} -> rejete={c0.y < min_y}')
                for c in ground_cubes:
                    size = c.width * c.height
                    if size > best_size:
                        best = c
                        best_size = size
                if best is not None:
                    return best
            time.sleep(0.05)
        return best

    def _get_depth_at(self, x, y, window=5):
        """Lit la profondeur (mm) au pixel (x,y) dans l'image depth."""
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

    def _get_distance(self, cube):
        """
        Retourne la distance au cube en mètres.
        Utilise depth si disponible, sinon estimation par taille.
        """
        use_depth = self._get_param('use_depth')

        # Essayer depth d'abord
        if use_depth:
            depth_mm = self._get_depth_at(cube.x, cube.y)
            if depth_mm is not None:
                return depth_mm / 1000.0, 'depth'

        # Fallback: estimation par taille
        target_size = float(self._get_param('target_size_px'))
        gripper_reach = float(self._get_param('gripper_reach'))
        current_size = (cube.width + cube.height) / 2.0
        if current_size > 0:
            # Estimation: distance ≈ gripper_reach * (target_size / current_size)
            est_dist = gripper_reach * (target_size / current_size)
            return est_dist, 'estimate'

        return None, 'none'

    # ─── Mouvement ───

    def _turn_to(self, angle_rad):
        angular_speed = float(self._get_param('angular_speed'))
        if abs(angle_rad) < ANGLE_DEADZONE:
            return
        duration = abs(angle_rad) / angular_speed
        self.get_logger().info(f'  Rotation {math.degrees(angle_rad):+.1f}°')
        twist = Twist()
        twist.angular.z = math.copysign(angular_speed, angle_rad)
        start = time.time()
        while time.time() - start < duration and not self._abort:
            self.cmd_vel_pub.publish(twist)
            time.sleep(CMD_VEL_RATE)
        self._stop_robot()
        time.sleep(0.2)

    def _drive(self, distance_m):
        """Avance (négatif) ou recule (positif)."""
        linear_speed = float(self._get_param('linear_speed'))
        if abs(distance_m) < DISTANCE_DEADZONE:
            return
        duration = abs(distance_m) / linear_speed
        direction = "Avance" if distance_m < 0 else "Recule"
        self.get_logger().info(f'  {direction} {abs(distance_m)*100:.1f}cm')
        twist = Twist()
        twist.linear.x = linear_speed if distance_m < 0 else -linear_speed
        start = time.time()
        while time.time() - start < duration and not self._abort:
            self.cmd_vel_pub.publish(twist)
            time.sleep(CMD_VEL_RATE)
        self._stop_robot()
        time.sleep(0.15)

    # ─── Séquence principale ───

    def _scan_for_cube(self):
        scan_step = float(self._get_param('scan_step_deg'))
        self._say("Je cherche le cube rouge autour de moi.")
        self.get_logger().info(f'Scan 360° (paliers de {scan_step}°)')

        num_steps = int(360 / scan_step)
        for step in range(num_steps):
            if self._abort:
                return None
            cube = self._get_red_cube(timeout=1.0)
            if cube is not None:
                self.get_logger().info(
                    f'  ✅ Cube trouvé au scan {step+1}/{num_steps} '
                    f'({cube.x},{cube.y}, {cube.width}x{cube.height})')
                self._say("J'ai trouve le cube !")
                return cube
            self.get_logger().info(f'  Scan {step+1}/{num_steps}...')
            self._turn_to(math.radians(scan_step))

        self.get_logger().warn('Scan 360° terminé, aucun cube')
        return None

    def _center_cube(self, cube):
        fx = float(self._get_param('fx'))
        cx = float(self._get_param('cx'))
        angle_rad = math.atan2(cube.x - cx, fx)
        if abs(angle_rad) >= ANGLE_DEADZONE:
            self._say("Je me tourne vers le cube.")
            self._turn_to(angle_rad)
            time.sleep(0.3)
            new_cube = self._get_red_cube(timeout=2.0)
            if new_cube:
                cube = new_cube
                angle_rad = math.atan2(cube.x - cx, fx)
                if abs(angle_rad) >= ANGLE_DEADZONE:
                    self._turn_to(angle_rad)
                    time.sleep(0.3)
                    cube = self._get_red_cube(timeout=2.0) or cube
        return cube

    def _adjust_distance(self, cube):
        """
        Ajuste la distance au cube avec précision.
        Utilise depth (mm) si disponible, sinon estimation par taille.
        """
        gripper_reach = float(self._get_param('gripper_reach'))
        cam_offset = float(self._get_param('camera_to_gripper_offset'))
        target_dist = gripper_reach + cam_offset  # cible camera = pince + offset
        tolerance = float(self._get_param('distance_tolerance'))
        self.get_logger().info(f'  Cible camera: {target_dist*100:.1f}cm (pince: {gripper_reach*100:.1f}cm + offset: {cam_offset*100:.1f}cm)')

        for iteration in range(MAX_POSITIONING_ITER):
            if self._abort:
                return None

            cube = self._get_red_cube(timeout=2.0)
            if cube is None:
                self.get_logger().warn('Cube perdu')
                return None

            dist, source = self._get_distance(cube)
            if dist is None:
                self.get_logger().warn('Distance indisponible, nouvelle détection...')
                time.sleep(0.3)
                continue

            error = dist - target_dist
            self.get_logger().info(
                f'  [{source}] distance={dist*100:.1f}cm '
                f'(cible={target_dist*100:.1f}cm, erreur={error*100:+.1f}cm)')

            if abs(error) <= tolerance:
                self.get_logger().info('  ✅ Distance OK !')
                return cube

            # Ajuster: si trop loin (error > 0) → avancer (négatif)
            # si trop proche (error < 0) → reculer (positif)
            delta = -error  # négatif = avancer, positif = reculer
            delta = max(-0.10, min(0.10, delta))  # clamp ±10cm

            if delta < 0:
                self._say("J'avance un peu.")
            else:
                self._say("Je recule un peu.")
            self._drive(delta)
            time.sleep(0.2)

        self.get_logger().warn('Max itérations atteint, on tente quand même')
        return self._get_red_cube(timeout=2.0)

    def _custom_grip_sequence(self):
        """Sequence de prehension au sol avec controle servo direct.
        Servo IDs (from automatic_pick.py):
          1=base, 2=epaule(haut/bas), 3=coude, 4=poignet, 5=rotation, 10=pince(200=ouvert,560=ferme)
        """
        pub = self.create_publisher(ServosPosition, 'servo_controller', 1)
        import time as _time

        def set_servos(duration, positions):
            set_servo_position(pub, duration, positions)
            _time.sleep(duration + 0.3)

        # 1. Ouvrir la pince et preparer
        self.get_logger().info('  Prehension: ouverture pince + position basse')
        set_servos(1.0, ((1, 500), (2, 100), (3, 450), (4, 230), (5, 500), (10, 200)))

        # 2. Avancer legerement pour amener la pince sur le cube
        self.get_logger().info('  Prehension: avance 5cm')
        self._drive(-0.05)

        # 3. Fermer la pince
        self.get_logger().info('  Prehension: fermeture pince')
        set_servos(0.8, ((10, 560),))

        # 4. Reculer legerement avec le cube
        self.get_logger().info('  Prehension: recule 5cm')
        self._drive(0.05)

        # 5. Remonter le bras avec le cube
        self.get_logger().info('  Prehension: remontee bras')
        set_servos(1.5, ((1, 500), (2, 700), (3, 15), (4, 180), (5, 500), (10, 560)))

        self.get_logger().info('  ✅ Prehension terminee')

    def _run_sequence(self, voice_text):
        try:
            is_scan = 'cherche' in voice_text and ('autour' in voice_text or 'cube' in voice_text)

            # 1. Trouver le cube
            if is_scan:
                cube = self._scan_for_cube()
            else:
                self._say("Je cherche le cube rouge.")
                cube = self._get_red_cube(timeout=DETECT_TIMEOUT)

            if cube is None:
                self._say("Je ne vois pas de cube rouge. Place-le devant moi.")
                return

            dist, source = self._get_distance(cube)
            self.get_logger().info(
                f'Cube: ({cube.x},{cube.y}) {cube.width}x{cube.height}px, '
                f'distance={dist*100:.1f}cm ({source})' if dist else 'distance inconnue')

            # 2. Centrer
            cube = self._center_cube(cube)
            if cube is None:
                self._say("J'ai perdu le cube.")
                return

            # 3. Ajuster distance
            cube = self._adjust_distance(cube)
            if cube is None:
                self._say("Je n'arrive pas a me placer. Reessaie.")
                return

            # 4. Vérification finale
            dist, source = self._get_distance(cube)
            target = float(self._get_param('gripper_reach'))
            self.get_logger().info(
                f'Position finale: distance={dist*100:.1f}cm '
                f'(cible={target*100:.1f}cm, source={source})')

            # 5. Préhension
            self._say("J'attrape le cube !")
            use_custom = self._get_param('use_custom_grip')
            if use_custom:
                self._custom_grip_sequence()
            else:
                self.arm_controller.run_action('voice_pick')
                time.sleep(5.0)

            self._say("Voila, j'ai attrape le cube !")
            self.get_logger().info('✅ Séquence terminée')

        except Exception as e:
            self.get_logger().error(f'Erreur: {e}')
            import traceback
            traceback.print_exc()
            self._say("Désolé, il y a eu un problème.")
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
    node = PickAndPlaceNodeV4()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
