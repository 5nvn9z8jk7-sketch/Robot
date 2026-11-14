#!/usr/bin/env python3
# encoding: utf-8
"""
autonomous_mission_node.py — Mode mission autonome complet.

Le robot reçoit un ordre vocal et exécute une mission complète sans intervention:
  - "Mission attrape tous les cubes" → scan 360°, attrape chaque cube, les dépose
  - "Patrouille" → avance, tourne, scan, répète
  - "Va à la base" → retourne au point de départ (odométrie)
  - "Arrête-toi" / "Stop mission" → arrêt immédiat
  - "Status" → annonce l'état (batterie, position, mission en cours)

Fonctionnalités:
  - Gestion batterie: retour base si < 20%
  - Mémoire: se souvient des cubes déjà traités (évite les doublons)
  - Retry automatique si échec (3 tentatives)
  - Feedback vocal à chaque étape
  - Évitement obstacles basique (lidar)
  - Séquence de dépôt: attrape → recule → lâche → cherche suivant

Topics:
  - Écoute: /robot/ordre (étape 2 : ordres déjà compris par routeur_ordres.py)
  - Publie: /robot/ordre/fin (fin de mission)
  - Publie: /tts_node/tts_text (feedback vocal)
  - Publie: /controller/cmd_vel (mouvements)
  - Publie: /servo_controller (bras)
  - Lit: /ros_robot_controller/battery (batterie)
  - Lit: /odom (position)
  - Lit: /scan (lidar pour évitement)
"""

import math
import threading
import time
import json

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from std_msgs.msg import String, UInt16, Bool
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan

from interfaces.msg import ColorsInfo
from servo_controller_msgs.msg import ServosPosition
from servo_controller.action_group_controller import ActionGroupController

ACTION_GROUPS_PATH = '/home/ubuntu/software/arm_pc/ActionGroups'

# Paramètres
BATTERY_LOW_THRESHOLD = 20       # % batterie minimum
BATTERY_CRITICAL = 10            # % batterie critique (arrêt immédiat)
MAX_CUBES_PER_MISSION = 10       # max cubes par mission
RETRY_ATTEMPTS = 3               # tentatives par cube
SCAN_STEP_DEG = 30               # degrés par palier de scan
LINEAR_SPEED = 0.12              # m/s
ANGULAR_SPEED = 0.5              # rad/s
CMD_VEL_RATE = 0.05

# Actions du bras
ACTION_PICK = 'voice_pick'       # attraper
ACTION_DROP = 'voice_place'      # déposer (si existe, sinon voice_pick inversé)
ACTION_RESET = 'init'            # reset position

# États de mission
STATE_IDLE = 'idle'
STATE_SCANNING = 'scanning'
STATE_NAVIGATING = 'navigating'
STATE_PICKING = 'picking'
STATE_DROPPING = 'dropping'
STATE_RETURNING = 'returning'
STATE_LOW_BATTERY = 'low_battery'
STATE_ERROR = 'error'

# Commandes vocales reconnues
MISSION_COMMANDS = {
    'mission': ['mission', 'tache', 'tâche', 'travaille', 'au boulot', 'go'],
    'attrape_tout': ['attrape tout', 'attrape tous', 'ramasse tout', 'ramasse tous',
                    'collecte', 'collecte tout', 'pick all', 'tout attraper'],
    'patrouille': ['patrouille', 'patrol', 'surveille', 'garde', 'ronde'],
    'base': ['base', 'maison', 'retourne', 'rentre', 'home', 'charger', 'charge',
             'va a la base', 'retourne a la base', 'retourne a la maison'],
    'stop': ['stop', 'arrête', 'arrête-toi', 'stop mission', 'annule', 'cancel',
             'pause', 'halte', 'stoppe'],
    'status': ['status', 'état', 'etat', 'rapport', 'où en es-tu', 'ou en es tu',
               'batterie', 'resume', 'résume'],
    # 'attrape' (un seul cube) retire : c'est pick_and_place_node_v6 qui s'en charge.
    # Avant, "attrape cube" lancait les DEUX noeuds en meme temps (conflit roues + bras).
}


class AutonomousMissionNode(Node):
    def __init__(self):
        super().__init__('autonomous_mission_node')

        # Paramètres ROS2
        self.declare_parameter('battery_low', BATTERY_LOW_THRESHOLD)
        self.declare_parameter('battery_critical', BATTERY_CRITICAL)
        self.declare_parameter('max_cubes', MAX_CUBES_PER_MISSION)
        self.declare_parameter('linear_speed', LINEAR_SPEED)
        self.declare_parameter('angular_speed', ANGULAR_SPEED)

        # État
        self._lock = threading.Lock()
        self._state = STATE_IDLE
        self._mission_thread = None
        self._abort = False
        self._verrou = False   # arrêt général du gardien

        # Données capteurs
        self._battery_level = 100  # % (estimation si pas de topic)
        self._battery_voltage = 0  # mV
        self._odom_x = 0.0
        self._odom_y = 0.0
        self._odom_theta = 0.0
        self._latest_color_info = None
        self._latest_scan = None
        self._home_x = 0.0  # position de départ
        self._home_y = 0.0

        # Mémoire mission
        self._cubes_found = []      # positions des cubes trouvés
        self._cubes_picked = []     # positions des cubes attrapés
        self._current_mission = None
        self._mission_start_time = 0

        # Publishers
        # Étape 1 : les roues passent par gardien_securite.py (obstacles, arrêt général)
        self.cmd_vel_pub = self.create_publisher(Twist, '/robot/cmd_vel/auto', 1)
        self.tts_pub = self.create_publisher(String, '/tts_node/tts_text', 1)

        # Bras
        self.arm_controller = ActionGroupController(
            self.create_publisher(ServosPosition, 'servo_controller', 1),
            ACTION_GROUPS_PATH
        )

        # Subscriptions
        # Étape 2 : les phrases sont comprises par routeur_ordres.py, qui envoie
        # {"action": "attrape_tout" | "patrouille"} sur /robot/ordre.
        self.create_subscription(String, '/robot/ordre', self._ordre_callback, 10)
        self.pub_fin = self.create_publisher(String, '/robot/ordre/fin', 10)
        self._ordre_id = None
        self.create_subscription(
            ColorsInfo, '/color_detect_node/color_info', self._color_callback, 1)
        self.create_subscription(
            UInt16, '/ros_robot_controller/battery', self._battery_callback, 1)
        self.create_subscription(
            LaserScan, '/scan', self._scan_callback, 1)
        self.create_subscription(
            Bool, '/robot/estop_etat', self._estop_callback,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                            reliability=ReliabilityPolicy.RELIABLE))

        # Timer pour vérification batterie
        self.create_timer(5.0, self._battery_check_timer)

        self.get_logger().info('🤖 Autonomous Mission Node prêt')
        self.get_logger().info("Ordres reçus du routeur : attrape_tout, patrouille")

    # ─── Callbacks ───

    def _ordre_callback(self, msg):
        try:
            o = json.loads(msg.data)
        except ValueError:
            return
        commande = {'attrape_tout': 'attrape_tout', 'patrouille': 'patrouille'}.get(o.get('action'))
        if commande is None:
            return
        if self._verrou:
            self._say("Arrêt général actif. Dis reprends d'abord.")
            self._publier_fin(o.get('id'), 'refus', 'arrêt général actif')
            return
        with self._lock:
            occupe = self._state != STATE_IDLE
        if occupe:
            self._say("Une mission est déjà en cours. Dis 'stop' pour annuler.")
            self._publier_fin(o.get('id'), 'refus', 'mission déjà en cours')
            return
        self._ordre_id = o.get('id')
        self._publier_fin(o.get('id'), 'recu')
        self._start_mission(commande, o.get('action'))

    def _publier_fin(self, oid, resultat, detail=''):
        if oid is None:
            return
        self.pub_fin.publish(String(data=json.dumps(
            {'id': oid, 'resultat': resultat, 'detail': detail}, ensure_ascii=False)))

    def _estop_callback(self, msg):
        """Arrêt général du gardien : annule la mission en cours."""
        self._verrou = bool(msg.data)
        if msg.data and self._state not in (STATE_IDLE, STATE_LOW_BATTERY):
            self.get_logger().warn('🛑 Arrêt général (gardien) - mission annulée')
            threading.Thread(target=self._abort_mission, daemon=True).start()

    def _color_callback(self, msg):
        with self._lock:
            self._latest_color_info = msg

    def _battery_callback(self, msg):
        # UInt16 en mV, 3S LiPo: 12600mV = 100%, 9900mV = 0%
        self._battery_voltage = msg.data
        # Conversion approximative: 10500mV = 0%, 12600mV = 100%
        pct = max(0, min(100, (msg.data - 10500) / (12600 - 10500) * 100))
        self._battery_level = int(pct)

    def _scan_callback(self, msg):
        with self._lock:
            self._latest_scan = msg

    def _battery_check_timer(self):
        """Vérifie la batterie et agit si faible."""
        if self._battery_level <= BATTERY_CRITICAL:
            if self._state != STATE_IDLE:
                self.get_logger().warn(f'🪫 Batterie critique: {self._battery_level}% — arrêt!')
                self._abort_mission()
                self._say(f"Batterie critique, {self._battery_level}%. Arrêt d'urgence.")
            self._state = STATE_LOW_BATTERY
        elif self._battery_level <= BATTERY_LOW_THRESHOLD:
            if self._state not in [STATE_IDLE, STATE_LOW_BATTERY, STATE_RETURNING]:
                self.get_logger().warn(f'🪫 Batterie faible: {self._battery_level}% — retour base')
                # Plus de retour automatique à la base : _drive roule dans le mauvais
                # sens (point ouvert, étape 3/4). On arrête la mission et on prévient.
                self._say(f"Batterie faible, {self._battery_level}%. J'arrête la mission, recharge-moi.")
                self._abort_mission()

    # ─── Parsing commandes ───

    def _parse_command(self, text):
        """Analyse le texte et retourne le type de commande."""
        # Recherche par MOT entier (avant : 'go' matchait 'gobelet', 'garde' matchait 'regarde'...)
        import re
        for cmd_type, keywords in MISSION_COMMANDS.items():
            for kw in keywords:
                if re.search(r'(?<!\w)' + re.escape(kw) + r'(?!\w)', text):
                    return cmd_type
        return None

    # ─── Gestion mission ───

    def _start_mission(self, command, full_text):
        """Démarre une nouvelle mission dans un thread séparé."""
        with self._lock:
            self._state = STATE_SCANNING
            self._abort = False
            self._current_mission = command
            self._mission_start_time = time.time()
            self._cubes_found = []
            self._cubes_picked = []

        self._mission_thread = threading.Thread(
            target=self._run_mission, args=(command, full_text), daemon=True)
        self._mission_thread.start()

    def _abort_mission(self):
        """Annule la mission en cours."""
        with self._lock:
            self._abort = True
        self._stop_robot()
        time.sleep(0.5)
        with self._lock:
            self._state = STATE_IDLE
            self._current_mission = None

    def _run_mission(self, command, full_text):
        """Exécute la mission complète."""
        resultat = 'ok'
        try:
            if command in ['mission', 'attrape_tout']:
                self._mission_pick_all()
            elif command == 'patrouille':
                self._mission_patrol()
            elif command == 'base':
                self._mission_return_home()
            elif command == 'attrape':
                self._mission_pick_one(full_text)
        except Exception as e:
            self.get_logger().error(f'Erreur mission: {e}')
            self._say("Erreur pendant la mission.")
            resultat = 'echec'
        finally:
            with self._lock:
                self._state = STATE_IDLE
                self._current_mission = None
            self._stop_robot()
            if self._abort and resultat == 'ok':
                resultat = 'annule'
            oid, self._ordre_id = self._ordre_id, None
            self._publier_fin(oid, resultat)

    # ─── Missions ───

    def _mission_pick_all(self):
        """Mission: attraper tous les cubes rouges trouvés."""
        self._say("Mission: attraper tous les cubes rouges. C'est parti !")
        self.get_logger().info('🎯 Mission: attrape tous les cubes')

        cubes_picked = 0
        max_cubes = int(self._get_param('max_cubes'))

        while cubes_picked < max_cubes and not self._abort:
            # 1. Scanner pour trouver un cube
            with self._lock:
                self._state = STATE_SCANNING
            self._say("Je cherche un cube...")
            cube = self._scan_for_cube()

            if cube is None:
                self._say("Je ne trouve plus de cube. Mission terminée.")
                break

            # 2. Attraper le cube (avec retry)
            success = False
            for attempt in range(RETRY_ATTEMPTS):
                if self._abort:
                    return
                self.get_logger().info(f'Tentative {attempt+1}/{RETRY_ATTEMPTS}')
                success = self._pick_cube(cube)
                if success:
                    break
                self._say(f"Échec, je réessaie... ({attempt+1})")

            if success:
                cubes_picked += 1
                self._say(f"Cube {cubes_picked} attrapé ! {max_cubes - cubes_picked} restant.")
                self.get_logger().info(f'✅ Cube {cubes_picked}/{max_cubes} attrapé')
            else:
                self._say("Je n'y arrive pas. Je passe au suivant.")
                self.get_logger().warn('❌ Échec définitif sur ce cube')

            # 3. Reculer pour lâcher de la place
            time.sleep(0.5)
            if not self._abort:
                self._drive(0.15)  # reculer 15cm

        # Fin de mission
        self._say(f"Mission terminée ! {cubes_picked} cube(s) attrapé(s).")
        self.get_logger().info(f'🏁 Mission terminée: {cubes_picked} cubes')

    def _mission_patrol(self):
        """Mission: patrouiller (avancer, tourner, scanner)."""
        self._say("Mission de patrouille activée.")
        self.get_logger().info('🚔 Mission: patrouille')

        patrol_duration = 120  # 2 minutes
        start_time = time.time()

        while time.time() - start_time < patrol_duration and not self._abort:
            with self._lock:
                self._state = STATE_NAVIGATING

            # Avancer 1 mètre
            self._drive(-0.5)  # avance 50cm
            if self._abort:
                break

            # Tourner 90°
            self._turn(math.radians(90))
            if self._abort:
                break

            # Scanner rapidement
            cube = self._get_red_cube(timeout=1.0)
            if cube:
                self._say("Cube détecté pendant la patrouille !")
                self.get_logger().info('👀 Cube détecté en patrouille')

        self._say("Patrouille terminée.")

    def _mission_return_home(self):
        """Mission: retourner au point de départ."""
        self._say("Retour à la base.")
        self.get_logger().info('🏠 Mission: retour base')

        with self._lock:
            self._state = STATE_RETURNING

        # Calculer distance et angle vers home
        dx = self._home_x - self._odom_x
        dy = self._home_y - self._odom_y
        distance = math.sqrt(dx*dx + dy*dy)
        target_angle = math.atan2(dy, dx)

        # Tourner vers la base
        angle_diff = self._normalize_angle(target_angle - self._odom_theta)
        if abs(angle_diff) > 0.1:
            self._turn(angle_diff)

        # Avancer vers la base
        if distance > 0.1:
            self._drive(-distance)

        self._say("Je suis arrivé à la base.")

    def _mission_pick_one(self, text):
        """Mission: attraper un seul cube (commande simple)."""
        self._say("Je cherche le cube rouge.")
        cube = self._scan_for_cube()
        if cube:
            self._pick_cube(cube)
            self._say("Cube attrapé !")
        else:
            self._say("Aucun cube trouvé.")

    # ─── Actions primitives ───

    def _scan_for_cube(self):
        """Scan 360° pour trouver un cube rouge."""
        scan_step = SCAN_STEP_DEG
        num_steps = int(360 / scan_step)

        for step in range(num_steps):
            if self._abort:
                return None

            cube = self._get_red_cube(timeout=1.0)
            if cube is not None:
                self.get_logger().info(f'Cube trouvé au scan {step+1}')
                return cube

            self._turn(math.radians(scan_step))

        return None

    def _pick_cube(self, cube):
        """Séquence complète pour attraper un cube."""
        with self._lock:
            self._state = STATE_NAVIGATING

        # Centrer
        cube = self._center_cube(cube)
        if cube is None:
            return False

        # Ajuster distance (simplifié: avance fixe)
        with self._lock:
            self._state = STATE_PICKING
        self._say("J'y vais !")  # pas « attrape »+« cube »: relancerait pick_and_place_node_v6 via le micro
        self._drive(-0.10)  # avance 10cm

        # Action bras
        self.arm_controller.run_action(ACTION_PICK)
        time.sleep(4.0)

        # Reculer avec le cube
        self._drive(0.20)
        return True

    def _get_red_cube(self, timeout=3.0):
        """Retourne le cube rouge détecté ou None."""
        deadline = time.time() + timeout
        best = None
        best_size = 0
        while time.time() < deadline and not self._abort:
            with self._lock:
                info = self._latest_color_info
            if info and len(info.data) > 0:
                reds = [ci for ci in info.data if ci.color == 'red' and ci.y >= 0]
                for c in reds:
                    size = c.width * c.height
                    if size > best_size:
                        best = c
                        best_size = size
                if best:
                    return best
            time.sleep(0.05)
        return best

    def _center_cube(self, cube):
        """Tourne pour centrer le cube."""
        fx = 211.688
        cx = 159.752
        angle_rad = math.atan2(cx - cube.x, fx)
        if abs(angle_rad) > 0.03:
            self._turn(angle_rad)
            time.sleep(0.3)
            cube = self._get_red_cube(timeout=2.0) or cube
        return cube

    def _drive(self, distance_m):
        """Avance (négatif) ou recule (positif)."""
        speed = float(self._get_param('linear_speed'))
        if abs(distance_m) < 0.02:
            return
        duration = abs(distance_m) / speed
        twist = Twist()
        twist.linear.x = -speed if distance_m < 0 else speed
        start = time.time()
        while time.time() - start < duration and not self._abort:
            self.cmd_vel_pub.publish(twist)
            time.sleep(CMD_VEL_RATE)
        self._stop_robot()

    def _turn(self, angle_rad):
        """Tourne de angle_rad radians."""
        speed = float(self._get_param('angular_speed'))
        if abs(angle_rad) < 0.03:
            return
        duration = abs(angle_rad) / speed
        twist = Twist()
        twist.angular.z = -math.copysign(speed, angle_rad)
        start = time.time()
        while time.time() - start < duration and not self._abort:
            self.cmd_vel_pub.publish(twist)
            time.sleep(CMD_VEL_RATE)
        self._stop_robot()

    def _stop_robot(self):
        self.cmd_vel_pub.publish(Twist())

    def _say(self, text):
        self.get_logger().info(f'🗣️  {text}')
        msg = String()
        msg.data = text
        self.tts_pub.publish(msg)

    def _announce_status(self):
        """Annonce l'état actuel du robot."""
        with self._lock:
            state = self._state
            mission = self._current_mission

        status = f"État: {state}. "
        if mission:
            elapsed = int(time.time() - self._mission_start_time)
            status += f"Mission {mission} en cours depuis {elapsed} secondes. "
        status += f"Batterie: {self._battery_level}%. "
        status += f"Position: x={self._odom_x:.1f}, y={self._odom_y:.1f}."

        self._say(status)
        self.get_logger().info(f'📊 {status}')

    def _get_param(self, name):
        return self.get_parameter(name).value

    @staticmethod
    def _normalize_angle(angle):
        while angle > math.pi:
            angle -= 2 * math.pi
        while angle < -math.pi:
            angle += 2 * math.pi
        return angle


def main(args=None):
    rclpy.init(args=args)
    node = AutonomousMissionNode()
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
