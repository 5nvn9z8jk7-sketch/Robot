#!/usr/bin/env python3
"""pick_and_place_servo.py - Asservissement visuel PBVS pour attraper le cube rouge."""
import math, time, threading
import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Image, CameraInfo
from interfaces.msg import ColorsInfo
from servo_controller_msgs.msg import ServosPosition
from servo_controller.bus_servo_control import set_servo_position

MIN_DEPTH_MM = 100
MAX_DEPTH_MM = 4000
CMD_VEL_RATE = 0.05
TARGET_COLOR = 'red'
TRIGGER_VERBS = ['attrape', 'attraper', 'ramasse', 'ramasser', 'prends', 'prendre',
                 'saisis', 'saisir', 'cherche', 'chercher', 'trouve', 'trouver',
                 'va chercher', 'va ramasser', 'pick', 'grab']
TRIGGER_OBJECTS = ['cube', 'objet', 'balle', 'rouge', 'red', 'block', 'bloc']


class VisualServoNode(Node):
    def __init__(self):
        super().__init__('pick_and_place_servo')
        self.declare_parameter('target_z', 0.22)
        self.declare_parameter('kp_linear', 0.8)
        self.declare_parameter('kp_angular', 2.5)
        self.declare_parameter('tol_x', 0.05)
        self.declare_parameter('tol_z', 0.03)
        self.declare_parameter('max_iter', 400)
        self.declare_parameter('linear_speed_max', 0.15)
        self.declare_parameter('angular_speed_max', 0.6)
        self.declare_parameter('min_y_pixel', 0)
        self.declare_parameter('fx', 423.376)
        self.declare_parameter('fy', 424.174)
        self.declare_parameter('cx', 319.5)
        self.declare_parameter('cy', 201.7)
        self._lock = threading.Lock()
        self._busy = False
        self._abort = False
        self._latest_color = None
        self._latest_depth = None
        self.cmd_vel_pub = self.create_publisher(Twist, '/controller/cmd_vel', 1)
        self.tts_pub = self.create_publisher(String, '/tts_node/tts_text', 1)
        self.create_subscription(String, '/vocal_detect/asr_result', self._asr_cb, 1)
        self.create_subscription(ColorsInfo, '/color_detect_node/color_info', self._color_cb, 1)
        self.create_subscription(Image, '/depth_cam/depth0/image_raw', self._depth_cb, 1)
        self.create_subscription(CameraInfo, '/depth_cam/depth0/camera_info', self._caminfo_cb, 1)
        self._msg_count = {'asr': 0, 'color': 0, 'depth': 0}
        self.create_timer(2.0, self._heartbeat)
        self.get_logger().info('Visual servo node pret')

    def _get_param(self, name):
        return self.get_parameter(name).value

    def _heartbeat(self):
        c = self._msg_count
        self.get_logger().info(
            f"♥ alive | msgs: asr={c['asr']} color={c['color']} depth={c['depth']} "
            f"busy={self._busy}")

    def _asr_cb(self, msg):
        self._msg_count['asr'] += 1
        text = msg.data.strip().lower()
        if not text:
            return
        self.get_logger().info(f'ASR: {text}')
        if not self._is_trigger(text):
            return
        with self._lock:
            if self._busy:
                return
            self._busy = True
            self._abort = False
        threading.Thread(target=self._run_sequence, daemon=True).start()

    def _color_cb(self, msg):
        self._msg_count['color'] += 1
        with self._lock:
            self._latest_color = msg

    def _depth_cb(self, msg):
        self._msg_count['depth'] += 1
        try:
            depth = np.frombuffer(msg.data, dtype=np.uint16).reshape(msg.height, msg.width)
            with self._lock:
                self._latest_depth = depth.copy()
        except Exception as e:
            self.get_logger().error(f'Depth error: {e}')

    def _caminfo_cb(self, msg):
        if len(msg.k) >= 9:
            self.set_parameters([
                rclpy.parameter.Parameter('fx', rclpy.Parameter.Type.DOUBLE, msg.k[0]),
                rclpy.parameter.Parameter('fy', rclpy.Parameter.Type.DOUBLE, msg.k[4]),
                rclpy.parameter.Parameter('cx', rclpy.Parameter.Type.DOUBLE, msg.k[2]),
                rclpy.parameter.Parameter('cy', rclpy.Parameter.Type.DOUBLE, msg.k[5]),
            ])

    def _is_trigger(self, text):
        has_verb = any(v in text for v in TRIGGER_VERBS)
        has_object = any(o in text for o in TRIGGER_OBJECTS)
        return has_verb and has_object

    def _say(self, text):
        self.get_logger().info(f'TTS: {text}')
        msg = String()
        msg.data = text
        self.tts_pub.publish(msg)

    def _stop(self):
        self.cmd_vel_pub.publish(Twist())

    def _get_red_cube(self, timeout=3.0):
        min_y = int(self._get_param('min_y_pixel'))
        deadline = time.time() + timeout
        best = None
        best_size = 0
        while time.time() < deadline and not self._abort:
            with self._lock:
                info = self._latest_color
            if info and len(info.data) > 0:
                reds = [c for c in info.data if c.color == TARGET_COLOR and c.y >= min_y]
                for c in reds:
                    size = c.width * c.height
                    if size > best_size:
                        best = c
                        best_size = size
                if best is not None:
                    return best
            time.sleep(0.05)
        return best

    def _get_depth_at(self, x, y, window=5):
        with self._lock:
            depth_img = self._latest_depth
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

    def _get_cube_3d(self, cube):
        fx = float(self._get_param('fx'))
        fy = float(self._get_param('fy'))
        cx = float(self._get_param('cx'))
        cy = float(self._get_param('cy'))
        depth_mm = self._get_depth_at(cube.x, cube.y)
        if depth_mm is None:
            return None
        Z = depth_mm / 1000.0
        X = (cube.x - cx) * Z / fx
        Y = (cube.y - cy) * Z / fy
        return (X, Y, Z)

    def _speed_for_distance(self, Z):
        """Vitesse d'avance dégressive selon la distance au cube."""
        if Z > 0.40:
            return 0.15   # loin : vitesse max
        elif Z > 0.30:
            return 0.10   # moyen-loin
        elif Z > 0.25:
            return 0.06   # moyen
        elif Z > 0.20:
            return 0.03   # proche
        else:
            return 0.015  # très proche : très lent

    def _rotation_for_error(self, err_x):
        """Vitesse de rotation dégressive selon l'erreur latérale."""
        a = abs(err_x)
        if a > 0.15:
            return 0.6    # très décalé
        elif a > 0.10:
            return 0.4    # bien décalé
        elif a > 0.05:
            return 0.2    # légèrement décalé
        else:
            return 0.1    # fin centrage

    def _visual_servo(self, cube):
        """
        Asservissement visuel progressif :
        1. Centrage prioritaire (rotation seule)
        2. Approche par petits pas (vitesse dégressive)
        3. Arrêt quand dans la zone (|X|<tol_x et |Z-target|<tol_z)
        """
        target_z = float(self._get_param('target_z'))
        kp_lin = float(self._get_param('kp_linear'))
        kp_ang = float(self._get_param('kp_angular'))
        tol_x = float(self._get_param('tol_x'))
        tol_z = float(self._get_param('tol_z'))
        max_iter = int(self._get_param('max_iter'))

        self.get_logger().info(f'🎯 Servo progressif: cible Z={target_z*100:.0f}cm, tol X={tol_x*100:.0f}cm Z={tol_z*100:.0f}cm')

        for iteration in range(max_iter):
            if self._abort:
                self._stop()
                return None

            cube = self._get_red_cube(timeout=2.0)
            if cube is None:
                self.get_logger().warn('⚠️ Cube perdu pendant le servo')
                self._stop()
                return None

            pos3d = self._get_cube_3d(cube)
            if pos3d is None:
                self.get_logger().warn('  depth indisponible, retry...')
                time.sleep(0.2)
                continue

            X, Y, Z = pos3d
            err_x = X
            err_z = Z - target_z

            # ─── 1. CENTRAGE PRIORITAIRE ───
            if abs(err_x) > tol_x:
                rot_speed = self._rotation_for_error(err_x)
                omega = kp_ang * err_x
                omega = max(-rot_speed, min(rot_speed, omega))
                twist = Twist()
                twist.angular.z = omega  # +err_x = cube à droite → tourne à droite (+)
                self.cmd_vel_pub.publish(twist)
                self.get_logger().info(
                    f'  [{iteration+1}] CENTRAGE X={X*100:+.1f}cm Z={Z*100:.1f}cm '
                    f'→ rotation {math.degrees(omega):+.1f}°/s')
                time.sleep(CMD_VEL_RATE)
                continue

            # ─── 2. DANS LA ZONE → STOP ───
            if abs(err_z) < tol_z:
                self.get_logger().info(
                    f'  [{iteration+1}] ✅ ZONE ATTEINTE! X={X*100:+.1f}cm Z={Z*100:.1f}cm')
                self._stop()
                time.sleep(0.3)
                return cube

            # ─── 3. APPROCHE / RECUL ───
            lin_speed = self._speed_for_distance(Z)
            v_x = kp_lin * err_z
            v_x = max(-lin_speed, min(lin_speed, v_x))
            direction = "AVANCE" if v_x > 0 else "RECULE"
            twist = Twist()
            twist.linear.x = v_x  # err_z>0 = trop loin → avance (v_x > 0)
            self.cmd_vel_pub.publish(twist)
            self.get_logger().info(
                f'  [{iteration+1}] {direction} X={X*100:+.1f}cm Z={Z*100:.1f}cm '
                f'err_z={err_z*100:+.1f}cm → v={v_x:.3f}m/s (max={lin_speed:.3f})')
            time.sleep(CMD_VEL_RATE)

        self.get_logger().warn('⏱️ Max iterations atteint')
        self._stop()
        return self._get_red_cube(timeout=2.0)

    def _grip_sequence(self):
        pub = self.create_publisher(ServosPosition, '/servo_controller', 1)

        def set_servos(duration, positions):
            set_servo_position(pub, duration, positions)
            time.sleep(duration + 0.3)

        self.get_logger().info('  Prehension: ouverture')
        set_servos(1.0, ((1, 500), (2, 100), (3, 450), (4, 230), (5, 500), (10, 200)))
        self.get_logger().info('  Prehension: fermeture')
        set_servos(0.8, ((10, 560),))
        self.get_logger().info('  Prehension: remontee')
        set_servos(1.5, ((1, 500), (2, 700), (3, 15), (4, 180), (5, 500), (10, 560)))
        self.get_logger().info('  Prehension terminee')

    def _run_sequence(self):
        try:
            self._say("Je cherche le cube rouge.")
            cube = self._get_red_cube(timeout=5.0)
            if cube is None:
                self._say("Je ne vois pas de cube rouge.")
                return
            pos3d = self._get_cube_3d(cube)
            if pos3d:
                X, Y, Z = pos3d
                self.get_logger().info(
                    f'Cube: X={X*100:+.1f}cm Y={Y*100:+.1f}cm Z={Z*100:.1f}cm')
            self._say("J'avance vers le cube.")
            cube = self._visual_servo(cube)
            if cube is None:
                self._say("J'ai perdu le cube.")
                return
            pos3d = self._get_cube_3d(cube)
            if pos3d:
                X, Y, Z = pos3d
                self.get_logger().info(
                    f'Final: X={X*100:+.1f}cm Y={Y*100:+.1f}cm Z={Z*100:.1f}cm')
            self._say("J'attrape le cube!")
            self._grip_sequence()
            self._say("Voila!")
        except Exception as e:
            self.get_logger().error(f'Erreur: {e}')
            import traceback
            traceback.print_exc()
        finally:
            self._stop()
            with self._lock:
                self._busy = False
                self._abort = False

    def request_abort(self):
        with self._lock:
            self._abort = True


def main(args=None):
    rclpy.init(args=args)
    node = VisualServoNode()
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
