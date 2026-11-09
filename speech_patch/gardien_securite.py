#!/usr/bin/env python3
# encoding: utf-8
"""gardien_securite.py — seul passage vers les roues pour NOS programmes.

Entrées :
  /robot/cmd_vel/manuel   (Twist)  keypad, joystick de la page
  /robot/cmd_vel/auto     (Twist)  pick v6, mission, pont vocal
  /robot/estop            (Bool)   True = arrêt général verrouillé, False = reprise
  /vocal_detect/asr_result (String) « stop / arrête… » -> verrou ; « reprends » -> reprise
  /scan                   (LaserScan) lidar filtré Hiwonder (avant + côtés)
Sorties :
  /controller/cmd_vel     (Twist)  vers les moteurs
  /robot/estop_etat       (Bool, transient local) état du verrou, pour les autres nœuds
  /robot/securite/etat    (String JSON, 2 Hz) pour la page Web
  /tts_node/tts_text      (String) annonces « Arrêt général », « Obstacle », « Je reprends »

Règles (logique dans securite_logique.py, testée hors robot) :
  arrêt verrouillé > manuel > auto ; commande > 0,3 s = arrêtée ;
  obstacle dans le sens de marche : ralenti dès 0,60 m, arrêt à 0,30 m (depuis le lidar) ;
  marche arrière (non surveillée) : 0,10 m/s maxi, 5 s maxi d'affilée ;
  lidar muet > 1 s : translations bloquées (rotations permises).

Les nœuds Hiwonder (self_driving, joystick_control, lidar_app, line_following,
object_tracking) publient encore directement sur /controller/cmd_vel. Pendant
un arrêt verrouillé, le gardien publie des zéros à 20 Hz pour les contrer.
"""
import json
import os
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy, qos_profile_sensor_data
from std_msgs.msg import Bool, String
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import securite_logique as sl  # noqa: E402

FREQ_HZ = 20.0
ZEROS_APRES_S = 0.5      # après la dernière commande : zéros pendant 0,5 s puis silence
ANNONCE_OBSTACLE_S = 5.0  # pas plus d'une annonce « obstacle » toutes les 5 s


class GardienSecurite(Node):
    def __init__(self):
        super().__init__('gardien_securite')
        reglages = {}
        for nom, defaut in [('dist_arret', sl.DIST_ARRET_M), ('dist_ralenti', sl.DIST_RALENTI_M),
                            ('demi_cone', sl.DEMI_CONE_DEG), ('vmax_lin', sl.VMAX_LIN),
                            ('vmax_ang', sl.VMAX_ANG), ('vmax_recul', sl.VMAX_RECUL),
                            ('duree_max_recul', sl.DUREE_MAX_RECUL_S)]:
            self.declare_parameter(nom, float(defaut))
            reglages[nom] = float(self.get_parameter(nom).value)
        self.g = sl.Gardien(**reglages)
        self.add_on_set_parameters_callback(self._params_cb)

        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.RELIABLE)
        self.pub_cmd = self.create_publisher(Twist, '/controller/cmd_vel', 1)
        self.pub_verrou = self.create_publisher(Bool, '/robot/estop_etat', latched)
        self.pub_etat = self.create_publisher(String, '/robot/securite/etat', 1)
        self.pub_tts = self.create_publisher(String, '/tts_node/tts_text', 1)

        self.create_subscription(Twist, '/robot/cmd_vel/manuel',
                                 lambda m: self._cmd('manuel', m), 1)
        self.create_subscription(Twist, '/robot/cmd_vel/auto',
                                 lambda m: self._cmd('auto', m), 1)
        self.create_subscription(Bool, '/robot/estop', self._estop_cb, 10)
        self.create_subscription(String, '/vocal_detect/asr_result', self._asr_cb, 10)
        self.create_subscription(LaserScan, '/scan', self._scan_cb, qos_profile_sensor_data)

        self._derniere_cmd = 0.0
        self._annonce_obstacle = 0.0
        self._motif_precedent = ''
        self._publier_verrou()
        self.create_timer(1.0 / FREQ_HZ, self._tick)
        self.create_timer(0.5, self._etat)
        self.get_logger().info('gardien_securite prêt (arrêt 0,30 m, ralenti 0,60 m, recul 0,10 m/s)')

    # ── entrées ──
    def _params_cb(self, params):
        from rcl_interfaces.msg import SetParametersResult
        for p in params:
            if p.name in self.g.r:
                self.g.r[p.name] = float(p.value)
                self.get_logger().info(f'réglage {p.name} = {p.value}')
        return SetParametersResult(successful=True)

    def _cmd(self, source, m):
        t = time.monotonic()
        self.g.commande(source, t, m.linear.x, m.linear.y, m.angular.z)
        self._derniere_cmd = t

    def _scan_cb(self, m):
        self.g.lidar(time.monotonic(), m.angle_min, m.angle_increment, m.ranges)

    def _estop_cb(self, m):
        self._verrouiller() if m.data else self._deverrouiller()

    def _asr_cb(self, m):
        if sl.est_arret(m.data):
            self._verrouiller()
        elif sl.est_reprise(m.data):
            self._deverrouiller()

    def _verrouiller(self):
        if self.g.arreter():
            self.get_logger().warn('🛑 ARRÊT GÉNÉRAL verrouillé')
            self._dire('Arrêt général.')
        self.pub_cmd.publish(Twist())
        self._publier_verrou()

    def _deverrouiller(self):
        if self.g.reprendre():
            self.get_logger().info('✅ Arrêt général levé')
            self._dire('Je reprends.')
        self._publier_verrou()

    # ── sorties ──
    def _dire(self, texte):
        self.pub_tts.publish(String(data=texte))

    def _publier_verrou(self):
        self.pub_verrou.publish(Bool(data=self.g.verrou))

    def _tick(self):
        t = time.monotonic()
        vx, vy, wz, source, motif = self.g.calculer(t)
        if source is None:
            # Plus de commande : quelques zéros pour finir proprement, puis on se tait
            # (pour ne pas bloquer la manette Hiwonder quand on ne fait rien).
            if t - self._derniere_cmd <= ZEROS_APRES_S:
                self.pub_cmd.publish(Twist())
        else:
            m = Twist()
            m.linear.x, m.linear.y, m.angular.z = float(vx), float(vy), float(wz)
            self.pub_cmd.publish(m)
        if motif and motif != self._motif_precedent:
            self.get_logger().warn(f'⚠️ {motif}')
            if motif.startswith('obstacle') and 'arrêt' in motif \
                    and t - self._annonce_obstacle > ANNONCE_OBSTACLE_S:
                self._annonce_obstacle = t
                self._dire('Obstacle.')
        self._motif_precedent = motif

    def _etat(self):
        self.pub_etat.publish(String(data=json.dumps({
            'verrou': self.g.verrou,
            'motif': self.g.dernier_motif,
            'lidar_ok': self.g.scan is not None and time.monotonic() - self.g.scan[0] < 1.0,
        }, ensure_ascii=False)))


def main():
    rclpy.init()
    node = GardienSecurite()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.pub_cmd.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
