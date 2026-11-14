#!/usr/bin/env python3
# encoding: utf-8
"""
llm_move_bridge_node v4 (étape 2) — exécuteur des DÉPLACEMENTS.

Ne comprend plus les phrases lui-même : c'est routeur_ordres.py qui le fait
(avant, ce nœud, le pick et la mission réagissaient chacun à leurs mots-clés).

Souscrit :
  /robot/ordre          (String JSON) {"id","action": avance|recule|crabe|tourne, ...}
  /robot/estop_etat     (Bool)   arrêt général -> interrompt le mouvement
  /robot/securite/etat  (String JSON) motif du gardien -> détecte « bloqué par un obstacle »
  /odom                 distance réellement parcourue
Publie :
  /robot/cmd_vel/auto   (Twist) -> gardien_securite (vitesses limitées, obstacles)
  /robot/ordre/fin      (String JSON) {"id","resultat": ok|echec|annule|refus,"detail"}

Mesure : avance / recule / crabe en boucle sur l'odométrie (distance exacte,
même méthode que le pick v6) ; rotation chronométrée (la boucle sur le cap
oscillait, essai E4 du 09/11) — à fiabiliser à l'étape 3.
"""
import json
import math
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from std_msgs.msg import String, Bool
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry

V_AVANCE = 0.20     # m/s
V_RECUL = 0.10      # m/s (= limite du gardien : 0,10 m/s pendant 5 s, donc 0,4 m max demandé)
V_CRABE = 0.15      # m/s
V_ROTATION = 0.6    # rad/s
PERIODE = 0.05      # s (le gardien considère une commande de plus de 0,3 s comme arrêtée)
ODOM_PERIME_S = 0.5
BLOQUE_S = 1.5      # bloqué par le gardien depuis 1,5 s -> échec « obstacle »
DEJA_LA_M = 0.01    # tolérance d'arrivée


class ExecuteurDeplacements(Node):
    def __init__(self):
        super().__init__('llm_move_bridge')
        self._lock = threading.Lock()
        self._occupe = False
        self._interrompre = False
        self._verrou = False
        self._odom = (0.0, 0.0, 0.0)   # x, y, t
        self._motif = ''
        self._motif_depuis = 0.0

        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.RELIABLE)
        self.pub_cmd = self.create_publisher(Twist, '/robot/cmd_vel/auto', 1)
        self.pub_fin = self.create_publisher(String, '/robot/ordre/fin', 10)
        self.create_subscription(String, '/robot/ordre', self._ordre_cb, 10)
        self.create_subscription(Bool, '/robot/estop_etat', self._estop_cb, latched)
        self.create_subscription(String, '/robot/securite/etat', self._secu_cb, 1)
        self.create_subscription(Odometry, '/odom', self._odom_cb, 1)
        self.get_logger().info('llm_move_bridge v4 prêt — exécute avance / recule / crabe / tourne du routeur')

    # ── callbacks ──
    def _ordre_cb(self, msg):
        try:
            o = json.loads(msg.data)
        except ValueError:
            return
        if o.get('action') not in ('avance', 'recule', 'crabe', 'tourne'):
            return   # ordre destiné à un autre exécuteur
        if self._verrou:
            self._fin(o, 'refus', 'arrêt général actif')
            return
        with self._lock:
            if self._occupe:
                occupe = True
            else:
                occupe = False
                self._occupe = True
                self._interrompre = False
        if occupe:
            self._fin(o, 'refus', 'déplacement déjà en cours')
            return
        self._fin(o, 'recu')
        threading.Thread(target=self._executer, args=(o,), daemon=True).start()

    def _estop_cb(self, msg):
        self._verrou = bool(msg.data)
        if msg.data:
            with self._lock:
                self._interrompre = True
            self.pub_cmd.publish(Twist())

    def _secu_cb(self, msg):
        try:
            motif = json.loads(msg.data).get('motif', '') or ''
        except ValueError:
            return
        bloque = ('arrêt' in motif and motif.startswith('obstacle')) or \
            motif.startswith('recul trop long') or motif.startswith('lidar muet')
        with self._lock:
            if bloque and not self._motif:
                self._motif_depuis = time.monotonic()
            self._motif = motif if bloque else ''

    def _odom_cb(self, msg):
        p = msg.pose.pose.position
        with self._lock:
            self._odom = (p.x, p.y, time.monotonic())

    # ── exécution ──
    def _fin(self, o, resultat, detail=''):
        self.pub_fin.publish(String(data=json.dumps(
            {'id': o.get('id'), 'resultat': resultat, 'detail': detail}, ensure_ascii=False)))

    def _executer(self, o):
        res, detail = 'echec', 'erreur interne'
        try:
            a = o['action']
            if a == 'tourne':
                res, detail = self._tourner(float(o['angle_deg']))
            else:
                d = float(o['distance_m'])
                if a == 'avance':
                    t = Twist(); t.linear.x = V_AVANCE; v = V_AVANCE
                elif a == 'recule':
                    t = Twist(); t.linear.x = -V_RECUL; v = V_RECUL
                else:
                    t = Twist(); v = V_CRABE
                    t.linear.y = V_CRABE if o.get('cote') == 'gauche' else -V_CRABE
                res, detail = self._rouler(t, d, v)
        except Exception as e:
            self.get_logger().error(f'Erreur : {e}')
        finally:
            self.pub_cmd.publish(Twist())
            with self._lock:
                self._occupe = False
            self.get_logger().info(f'{o.get("action")} -> {res} {detail}')
            self._fin(o, res, detail)

    def _arret_demande(self):
        with self._lock:
            if self._interrompre:
                return 'annule', 'arrêt général'
            if self._motif and time.monotonic() - self._motif_depuis > BLOQUE_S:
                return 'echec', ('obstacle devant moi' if self._motif.startswith('obstacle')
                                 else self._motif)
        return None

    def _rouler(self, twist, distance, vitesse):
        """Boucle sur l'odométrie ; sans odométrie : durée nominale."""
        with self._lock:
            x0, y0, t_odom = self._odom
        odom_ok = time.monotonic() - t_odom < ODOM_PERIME_S
        nominal = distance / vitesse
        debut = time.monotonic()
        limite = debut + (3.0 * nominal + 2.0 if odom_ok else nominal)
        self.get_logger().info(f'{distance:.2f} m à {vitesse:.2f} m/s '
                               f'({"odométrie" if odom_ok else "chronomètre, odométrie absente"})')
        while time.monotonic() < limite:
            stop = self._arret_demande()
            if stop:
                return stop
            if odom_ok:
                with self._lock:
                    x, y, t_odom = self._odom
                if time.monotonic() - t_odom > ODOM_PERIME_S:
                    return 'echec', "odométrie perdue"
                if math.hypot(x - x0, y - y0) >= distance - DEJA_LA_M:
                    return 'ok', ''
            self.pub_cmd.publish(twist)
            time.sleep(PERIODE)
        if odom_ok:
            return 'echec', "distance non atteinte à temps"
        return 'ok', 'chronomètre'

    def _tourner(self, angle_deg):
        t = Twist()
        t.angular.z = math.copysign(V_ROTATION, angle_deg)
        duree = math.radians(abs(angle_deg)) / V_ROTATION
        fin = time.monotonic() + duree
        while time.monotonic() < fin:
            stop = self._arret_demande()
            if stop:
                return stop
            self.pub_cmd.publish(t)
            time.sleep(PERIODE)
        return 'ok', ''


def main(args=None):
    rclpy.init(args=args)
    node = ExecuteurDeplacements()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.pub_cmd.publish(Twist())
        node.destroy_node()
        if rclpy.ok():          # déjà arrêté si le programme a reçu un signal (pkill)
            rclpy.shutdown()


if __name__ == '__main__':
    main()
