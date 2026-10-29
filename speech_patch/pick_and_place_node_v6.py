#!/usr/bin/env python3
# encoding: utf-8
"""
pick_and_place_node_v6 — Pick par asservissement visuel sur une cible apprise.

Pourquoi une v6 ? Problemes de fond de la v5 :
  1. La camera est montee SUR LE BRAS. La v5 ne remettait jamais le bras dans
     une pose fixe avant de regarder : apres un premier pick (bras laisse en
     pose "remontee") ou un reglage clavier (T/G/F/H/N), la camera ne regardait
     plus au meme endroit => toute la calibration devenait fausse.
     "camera_to_gripper_offset" n'a pas de sens physique sur ce robot.
  2. simple_grip=True par defaut : l'ajustement de distance etait SAUTE.
     Le robot attrapait a la distance ou il se trouvait, + 5 cm en aveugle.
  3. Mouvements en boucle ouverte (duree x vitesse). Pour 5 cm a 0.10 m/s
     (0.5 s), l'acceleration des moteurs mange une grosse partie du trajet.
  4. Le dernier cube detecte restait en memoire indefiniment : si le cube
     sortait du champ, le robot continuait a viser une position perimee.
  5. La phrase "attrape cube" declenchait AUSSI autonomous_mission_node :
     deux programmes pilotaient les roues et le bras en meme temps.

Methode v6 (identique dans l'esprit a la calibration officielle Hiwonder) :
  - teach_pick_v6.py enregistre la position (x, y) du cube DANS L'IMAGE quand
    il est pile sous la pince, bras en pose d'observation.
  - Ici, le bras se met toujours en pose d'observation, puis le robot se
    deplace en continu (20 Hz) jusqu'a ce que le cube soit a cette position
    (tolerance +/- quelques pixels). Pas d'offset a mesurer, pas de distance.
  - Puis meme sequence de prehension que pendant la calibration.
  - Verification : si le cube est encore au sol apres la prise -> nouvel essai.

Topics :
  /color_detect_node/color_info  (ColorsInfo, 320x200) <- simple_color_detect_v3
  /vocal_detect/asr_result       (String)  "attrape cube", "cherche le cube"...
  /controller/cmd_vel            (Twist)   -> roues (mecanum)
  servo_controller               (ServosPosition) -> bras
"""

import math
import threading
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist

from interfaces.msg import ColorsInfo
from servo_controller_msgs.msg import ServosPosition
from servo_controller.bus_servo_control import set_servo_position

from pick_calib import load_calib, pose, CALIB_FILE

TARGET_COLOR = 'red'
CONTROL_PERIOD = 0.05  # 20 Hz

TRIGGER_VERBS = ['attrape', 'attraper', 'ramasse', 'ramasser', 'prends', 'prendre',
                 'saisis', 'saisir', 'cherche', 'chercher', 'trouve', 'trouver',
                 'pick', 'grab', 'scan']
TRIGGER_OBJECTS = ['cube', 'objet', 'rouge', 'red', 'block', 'bloc']
# Ces phrases sont pour autonomous_mission_node, pas pour nous
EXCLUDE = ['tous', 'tout', 'mission', 'collecte', 'patrouille']


class PickAndPlaceNodeV6(Node):
    def __init__(self):
        super().__init__('pick_and_place_node_v6')

        p = self.declare_parameter
        p('tol_px', 5.0)            # tolerance position cube dans l'image (px, 320x200)
        p('kx', 0.0025)             # gain lateral (m/s par pixel)
        p('ky', 0.0025)             # gain avant/arriere (m/s par pixel)
        p('kw', 0.008)              # gain rotation (rad/s par pixel)
        p('max_lin', 0.12)          # vitesse lineaire max (m/s)
        p('min_lin', 0.025)         # vitesse min (sinon les moteurs ne bougent pas)
        p('max_ang', 0.6)           # vitesse rotation max (rad/s)
        p('min_ang', 0.15)
        p('rotate_above_px', 50.0)  # si cube tres decentre : rotation, sinon crabe
        p('use_strafe', True)       # False si chassis non mecanum
        p('invert_x', False)        # a mettre a True si le robot s'eloigne lateralement du cube
        p('invert_y', False)        # a mettre a True si le robot recule au lieu d'avancer
        p('approach_timeout', 25.0)
        p('lost_timeout', 1.0)
        p('scan_step_deg', 30.0)
        p('max_attempts', 2)
        p('verify_grip', True)

        self._lock = threading.Lock()
        self._busy = False
        self._abort = False
        self._cube = None
        self._cube_t = 0.0

        self.cmd_vel_pub = self.create_publisher(Twist, '/controller/cmd_vel', 1)
        self.tts_pub = self.create_publisher(String, '/tts_node/tts_text', 1)
        self.servo_pub = self.create_publisher(ServosPosition, 'servo_controller', 1)
        self.create_subscription(String, '/vocal_detect/asr_result', self._asr_cb, 1)
        self.create_subscription(ColorsInfo, '/color_detect_node/color_info', self._color_cb, 1)

        self.calib = load_calib()
        if self.calib['target_x'] is None:
            self.get_logger().warn(
                f'PAS DE CALIBRATION dans {CALIB_FILE} : lance teach_pick_v6.py d\'abord !')
        else:
            self.get_logger().info(
                f'pick v6 pret — cible image x={self.calib["target_x"]:.0f} '
                f'y={self.calib["target_y"]:.0f}')

    def P(self, name):
        return self.get_parameter(name).value

    # ─── Callbacks ───

    def _asr_cb(self, msg):
        text = msg.data.strip().lower()
        if not text:
            return
        if any(w in text for w in ['stop', 'arrete', 'arrête', 'annule']):
            self._abort = True
            self._stop()
            return
        if any(e in text for e in EXCLUDE):
            return
        if not (any(v in text for v in TRIGGER_VERBS) and any(o in text for o in TRIGGER_OBJECTS)):
            return
        with self._lock:
            if self._busy:
                self.get_logger().info('Deja en cours, ignore')
                return
            self._busy = True
            self._abort = False
        scan = 'cherche' in text or 'trouve' in text or 'scan' in text
        threading.Thread(target=self._run, args=(scan,), daemon=True).start()

    def _color_cb(self, msg):
        reds = [c for c in msg.data if c.color == TARGET_COLOR]
        with self._lock:
            # message vide = pas de cube -> on oublie l'ancien
            self._cube = max(reds, key=lambda c: c.width * c.height) if reds else None
            self._cube_t = time.time()

    def _fresh_cube(self, max_age=0.3):
        with self._lock:
            if self._cube is not None and time.time() - self._cube_t < max_age:
                return self._cube
        return None

    def _wait_cube(self, timeout):
        end = time.time() + timeout
        while time.time() < end and not self._abort:
            c = self._fresh_cube()
            if c is not None:
                return c
            time.sleep(0.05)
        return None

    # ─── Utilitaires ───

    def _say(self, text):
        self.get_logger().info(f'TTS: {text}')
        self.tts_pub.publish(String(data=text))

    def _stop(self):
        self.cmd_vel_pub.publish(Twist())

    def _arm(self, positions, duration):
        set_servo_position(self.servo_pub, duration, positions)
        time.sleep(duration + 0.3)

    def _observe_pose(self, gripper):
        self._arm(pose(self.calib, 'observe_pose', gripper), 1.5)
        time.sleep(0.5)  # laisser la camera se stabiliser

    def _check_cmd_vel_conflicts(self):
        try:
            infos = self.get_publishers_info_by_topic('/controller/cmd_vel')
            others = sorted({i.node_name for i in infos if i.node_name != self.get_name()})
            if others:
                self.get_logger().warn(
                    f'Autres noeuds qui publient sur /controller/cmd_vel : {others}. '
                    f'S\'ils publient en continu (ex: joystick_control), ils perturbent le pick.')
        except Exception:
            pass

    @staticmethod
    def _sat(v, vmin, vmax):
        """Limite |v| entre vmin et vmax, en gardant le signe."""
        if v == 0.0:
            return 0.0
        return math.copysign(min(vmax, max(vmin, abs(v))), v)

    # ─── Recherche ───

    def _scan(self):
        step = math.radians(float(self.P('scan_step_deg')))
        speed = 0.5
        for _ in range(int(2 * math.pi / step)):
            if self._abort:
                return None
            c = self._wait_cube(1.0)
            if c is not None:
                return c
            tw = Twist()
            tw.angular.z = speed
            t0 = time.time()
            while time.time() - t0 < step / speed and not self._abort:
                self.cmd_vel_pub.publish(tw)
                time.sleep(CONTROL_PERIOD)
            self._stop()
            time.sleep(0.4)
        return None

    # ─── Asservissement visuel ───

    def _approach(self):
        """Deplace le robot jusqu'a ce que le cube soit sur la cible image."""
        tx, ty = float(self.calib['target_x']), float(self.calib['target_y'])
        tol = float(self.P('tol_px'))
        kx, ky, kw = float(self.P('kx')), float(self.P('ky')), float(self.P('kw'))
        max_lin, min_lin = float(self.P('max_lin')), float(self.P('min_lin'))
        max_ang, min_ang = float(self.P('max_ang')), float(self.P('min_ang'))
        rot_px = float(self.P('rotate_above_px'))
        strafe = bool(self.P('use_strafe'))
        sx = -1.0 if self.P('invert_x') else 1.0
        sy = -1.0 if self.P('invert_y') else 1.0

        t_start = time.time()
        last_seen = time.time()
        last_log = 0.0
        while not self._abort:
            if time.time() - t_start > float(self.P('approach_timeout')):
                self.get_logger().warn('Approche : timeout')
                self._stop()
                return False

            c = self._fresh_cube()
            if c is None:
                self._stop()
                if time.time() - last_seen > float(self.P('lost_timeout')):
                    self.get_logger().warn('Cube perdu pendant l\'approche')
                    return False
                time.sleep(CONTROL_PERIOD)
                continue
            last_seen = time.time()

            ex = c.x - tx   # >0 : cube trop a droite dans l'image
            ey = c.y - ty   # <0 : cube trop haut = trop loin

            if abs(ex) <= tol and abs(ey) <= tol:
                self._stop()
                time.sleep(0.5)  # le robot s'arrete, nouvelle mesure
                c2 = self._wait_cube(1.0)
                if c2 and abs(c2.x - tx) <= tol * 1.5 and abs(c2.y - ty) <= tol * 1.5:
                    self.get_logger().info(
                        f'  En position : cube ({c2.x},{c2.y}) cible ({tx:.0f},{ty:.0f})')
                    return True
                continue

            tw = Twist()
            # Avant / arriere : cube trop haut dans l'image -> avancer
            if abs(ey) > tol:
                tw.linear.x = sy * self._sat(-ky * ey, min_lin, max_lin)
            # Gauche / droite
            if abs(ex) > tol:
                if strafe and abs(ex) < rot_px:
                    # +y ROS = gauche ; cube a droite (ex>0) -> aller a droite
                    tw.linear.y = sx * self._sat(-kx * ex, min_lin, max_lin)
                else:
                    tw.angular.z = sx * self._sat(-kw * ex, min_ang, max_ang)
                    tw.linear.x *= 0.5  # on tourne d'abord, on avance moins
            self.cmd_vel_pub.publish(tw)

            if time.time() - last_log > 0.5:
                last_log = time.time()
                self.get_logger().info(
                    f'  cube=({c.x},{c.y}) err=({ex:+.0f},{ey:+.0f})px '
                    f'cmd vx={tw.linear.x:+.3f} vy={tw.linear.y:+.3f} wz={tw.angular.z:+.2f}')
            time.sleep(CONTROL_PERIOD)
        self._stop()
        return False

    # ─── Prehension ───

    def _grip(self):
        g_open, g_close = self.calib['gripper_open'], self.calib['gripper_close']
        self.get_logger().info('  Descente pince ouverte')
        self._arm(pose(self.calib, 'grip_pose', g_open), 1.5)
        self.get_logger().info('  Fermeture pince')
        self._arm(((10, g_close),), 0.8)
        time.sleep(0.3)
        self.get_logger().info('  Remontee')
        self._observe_pose(g_close)

    def _cube_still_on_floor(self):
        """Vrai si un cube est encore vu a l'endroit de la cible (= prise ratee)."""
        tx, ty = self.calib['target_x'], self.calib['target_y']
        tw_, th_ = self.calib.get('target_w') or 0, self.calib.get('target_h') or 0
        c = self._wait_cube(1.0)
        if c is None:
            return False
        near = abs(c.x - tx) < 30 and abs(c.y - ty) < 30
        if tw_ and th_:
            ratio = (c.width * c.height) / float(tw_ * th_)
            near = near and 0.5 < ratio < 2.0
        return near

    # ─── Sequence ───

    def _run(self, scan):
        try:
            self.calib = load_calib()  # relit le fichier (recalibration sans redemarrer)
            if self.calib['target_x'] is None:
                self._say("Je ne suis pas calibre. Lance la calibration d'abord.")
                return
            self._check_cmd_vel_conflicts()

            g_open = self.calib['gripper_open']
            for attempt in range(1, int(self.P('max_attempts')) + 1):
                self._observe_pose(g_open)  # TOUJOURS la meme vue camera
                cube = self._wait_cube(2.0)
                if cube is None and scan:
                    self._say("Je cherche le cube rouge autour de moi.")
                    cube = self._scan()
                if cube is None:
                    self._say("Je ne vois pas de cube rouge.")
                    return

                self._say("Je me place devant le cube.")
                if not self._approach():
                    self._say("Je n'arrive pas a me placer.")
                    return

                self._say("J'attrape le cube.")
                self._grip()

                if not self.P('verify_grip') or not self._cube_still_on_floor():
                    self._say("C'est bon, j'ai le cube.")
                    self.get_logger().info('Sequence terminee')
                    return
                self.get_logger().warn(f'Prise ratee (essai {attempt})')
                self._say("Rate, je reessaie.")
            self._say("Je n'ai pas reussi a attraper le cube.")
        except Exception as e:
            self.get_logger().error(f'Erreur: {e}')
            import traceback
            traceback.print_exc()
            self._say("Desole, il y a eu un probleme.")
        finally:
            self._stop()
            with self._lock:
                self._busy = False
                self._abort = False


def main(args=None):
    rclpy.init(args=args)
    node = PickAndPlaceNodeV6()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            node._stop()
        except Exception:
            pass
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
