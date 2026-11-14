#!/usr/bin/env python3
# encoding: utf-8
"""
robot_watchdog.py — Surveillance automatique des composants du robot.

Vérifie toutes les N secondes que les nœuds critiques sont actifs.
Redémarre automatiquement ceux qui sont tombés.

Nœuds surveillés:
  - ros_robot_controller  (moteurs — CRITIQUE)
  - aurora                (caméra depth)
  - rosbridge_websocket   (WebSocket — CRITIQUE)
  - pick_and_place_node_v5 (pick and place au sol)
  - ws_audio_asr          (ASR vocal)
  - tts_node              (TTS vocal)
  - agent_process         (LLM)
  - routeur_ordres        (compréhension des phrases, étape 2)
  - llm_move_bridge       (exécuteur des déplacements)
  - autonomous_mission_node (missions autonomes)
  - simple_color_detect   (détection couleur)
  - servo_manager         (bras robotique — nœud réel, ex-servo_controller)
  - odom_publisher        (odométrie)

Usage sur le robot:
  nohup python3 robot_watchdog.py > /tmp/watchdog.log 2>&1 &

Ou avec paramètres:
  python3 robot_watchdog.py --interval 10 --max-restarts 5
"""

import subprocess
import time
import sys
import argparse
import os

# Configuration des nœuds à surveiller
# Format: (nom_node, commande_lancement, topic_test, priorite)
# priorite: 1=critique (redémarrage immédiat), 2=important, 3=normal
NODES_CONFIG = [
    # (nom, commande, topic à vérifier, priorité, delai avant test)
    ("ros_robot_controller",
     "/home/ubuntu/ros2_ws/install/ros_robot_controller/lib/ros_robot_controller/ros_robot_controller --ros-args -r __ns:=/ --params-file /home/ubuntu/speech_patch/params_ros_robot_controller.yaml",
     "/ros_robot_controller/imu_raw", 1, 3),
    # Étape 1 : seul passage vers les roues pour nos nœuds. S'il tombe, nos nœuds
    # ne peuvent plus bouger le robot (panne « sûre »), mais il faut le relancer vite.
    ("gardien_securite",
     "python3 -u /home/ubuntu/speech_patch/gardien_securite.py",
     None, 1, 2),
    # Programme du lidar (/scan_raw). Vu le 15/11 : lancé au boot AVANT que le port
    # /dev/lidar n'existe (créé 3 min plus tard) -> moteur qui tourne, aucune mesure,
    # et le gardien bloque tous les déplacements. Relancé ici si /scan_raw se tait.
    ("sclidar_scan_publisher",
     "bash -c 'source /home/ubuntu/third_party/third_party_ws/install/setup.bash; exec /home/ubuntu/third_party/third_party_ws/install/sclidar_ros2/lib/sclidar_ros2/sclidar --ros-args -r __node:=sclidar_scan_publisher --params-file /home/ubuntu/speech_patch/lidar_sclidar.yaml -r /scan:=scan_raw'",
     "/scan_raw", 1, 5),
    # Filtre lidar Hiwonder (/scan_raw -> /scan). Vu figé le 11/11 (32 % CPU, plus
    # rien sur /scan) : le gardien bloquait alors tous les déplacements. Lancé au
    # boot par lidar.launch.py ; ici on le relance seulement s'il disparaît ou se tait.
    ("scan_to_scan_filter_chain",
     "/opt/ros/humble/lib/laser_filters/scan_to_scan_filter_chain --ros-args --params-file /home/ubuntu/ros2_ws/install/peripherals/share/peripherals/config/lidar_filters_config_sclidar.yaml -r scan:=scan_raw -r scan_filtered:=scan",
     "/scan", 1, 3),
    # Étape 2 : seule porte d'entrée des phrases (voix robot, micro PC, page).
    # S'il tombe, plus aucun ordre n'est compris (panne « sûre »).
    ("routeur_ordres",
     "python3 -u /home/ubuntu/speech_patch/routeur_ordres.py",
     None, 1, 3),
    ("rosbridge_websocket",
     "ros2 launch rosbridge_server rosbridge_websocket_launch.xml",
     None, 1, 5),  # Pas de topic spécifique, on teste le port
    # ("aurora", ...) — supervisé par camera_supervisor.py (relance dediée + reset USB),
    # ne pas le gérer ici pour éviter les doubles redémarrages USB.
    ("pick_and_place_node_v6",
     "python3 /home/ubuntu/speech_patch/pick_and_place_node_v6.py",
     None, 2, 3),
    ("ws_audio_asr",
     None,  # Lancé par un script externe, on vérifie juste
     "/vocal_detect/asr_result", 2, 0),
    ("tts_node",
     "bash -c 'export ASR_MODE=offline ASR_LANGUAGE=fr MIC_TYPE=xf; ros2 run large_models tts_node'",
     None, 1, 3),  # tts_text = topic de requetes (ne publie jamais spontanement)
    ("agent_process",
     None,
     "/agent_process/result", 2, 0),
    ("llm_move_bridge",
     "python3 /home/ubuntu/speech_patch/llm_move_bridge_node.py",
     None, 2, 3),
    ("autonomous_mission_node",
     "python3 /home/ubuntu/speech_patch/autonomous_mission_node.py",
     None, 2, 3),
    ("simple_color_detect",
     "python3 /home/ubuntu/speech_patch/simple_color_detect_v3.py",
     "/color_detect_node/color_info", 1, 3),
    ("servo_manager",
     None,
     None, 1, 0),
    ("odom_publisher",
     None,
     "/odom", 2, 0),
]

# Fichiers de log pour chaque nœud
LOG_DIR = "/tmp/watchdog_logs"


class RobotWatchdog:
    def __init__(self, interval=10, max_restarts=5):
        self.interval = interval
        self.max_restarts = max_restarts
        self.restart_counts = {}  # {node_name: count}
        self.last_restart = {}    # {node_name: timestamp}
        self.running = True
        self._camera_check_count = 0
        self._last_camera_ok = time.time()
        # Compteur d'échecs consécutifs par nœud (anti faux-négatifs ros2 topic hz)
        self._fail_counts = {}

        # Créer le répertoire de logs
        os.makedirs(LOG_DIR, exist_ok=True)

        # Sourcer ROS2
        self.ros_env = self._get_ros_env()

    def _get_ros_env(self):
        """Retourne les commandes pour sourcer ROS2."""
        # XDG_RUNTIME_DIR : sans lui, les programmes lancés au boot (crontab)
        # ne trouvent pas le service audio -> le TTS ne sortait aucun son
        # (vérifié le 09/11 : même synthèse, son avec, silence sans).
        return (
            "export XDG_RUNTIME_DIR=/run/user/1000 && "
            "source /opt/ros/humble/setup.bash && "
            "source /home/ubuntu/ros2_ws/install/setup.bash && "
            "source /home/ubuntu/third_party/aurora_ws/install/setup.bash 2>/dev/null; "
        )

    def _run_cmd(self, cmd, timeout=10):
        """Exécute une commande shell et retourne (returncode, stdout, stderr)."""
        try:
            # bash obligatoire : /bin/sh (dash) ne connait pas "source" utilisé par ros_env
            result = subprocess.run(
                ["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "timeout"
        except Exception as e:
            return -1, "", str(e)

    def _is_node_active(self, node_name):
        """Vérifie si un nœud ROS2 est actif."""
        cmd = f"{self.ros_env} ros2 node list 2>/dev/null | grep -q '/{node_name}'"
        rc, _, _ = self._run_cmd(cmd, timeout=8)
        return rc == 0

    def _is_topic_publishing(self, topic, timeout=12):
        """Vérifie si un topic publie des messages."""
        if topic is None:
            return True  # Pas de test de topic
        # Correction faite sur le robot (récupérée le 09/11) : sortie non bufferisée
        # et sans « head -1 » (la 1re ligne n'est pas toujours « average rate »).
        cmd = f"{self.ros_env} timeout {timeout} env PYTHONUNBUFFERED=1 ros2 topic hz {topic} 2>/dev/null | grep -q 'average rate'"
        rc, _, _ = self._run_cmd(cmd, timeout=timeout + 2)
        return rc == 0

    def _is_port_open(self, port):
        """Vérifie si un port TCP est ouvert."""
        cmd = f"timeout 2 bash -c 'echo > /dev/tcp/localhost/{port}' 2>/dev/null"
        rc, _, _ = self._run_cmd(cmd, timeout=5)
        return rc == 0

    def _restart_node(self, node_name, launch_cmd, priority):
        """Redémarre un nœud."""
        # Vérifier le nombre de redémarrages récents
        count = self.restart_counts.get(node_name, 0)
        last_time = self.last_restart.get(node_name, 0)

        # Reset le compteur si le dernier redémarrage date de plus de 5 minutes
        if time.time() - last_time > 300:
            count = 0

        if count >= self.max_restarts:
            print(f"⚠️  {node_name}: max redémarrages atteint ({count}), abandon")
            return False

        print(f"🔄 Redémarrage de {node_name} (tentative {count+1}/{self.max_restarts})...")

        if launch_cmd is None:
            print(f"   ℹ️  Pas de commande de lancement définie pour {node_name}")
            return False

        # Tuer l'ancien processus si existe
        if node_name == "aurora":
            # Camera: tuer AGRESSIVEMENT tous les processus aurora/deptrum
            # et attendre que l'USB se libere (sinon le nouveau process ne peut pas ouvrir)
            print(f"   📷 Kill agressif caméra (SIGKILL)...")
            self._run_cmd("pkill -9 -f aurora930 2>/dev/null", timeout=5)
            self._run_cmd("pkill -9 -f deptrum 2>/dev/null", timeout=5)
            self._run_cmd("pkill -9 -f aurora930_node 2>/dev/null", timeout=5)
            time.sleep(5)  # Attendre liberation USB
            # Verifier que le device est libre
            rc, out, _ = self._run_cmd("lsof /dev/bus/usb/001/* 2>/dev/null | grep -c aurora || true", timeout=5)
            if out.strip() and out.strip() != "0":
                print(f"   ⚠️  Device USB encore occupe, attente supplémentaire...")
                time.sleep(5)
        else:
            # Motif entre crochets : sans eux, pkill tue aussi le « bash -c » qui
            # le lance (sa ligne de commande contient le nom du nœud).
            pattern = f"[{node_name[0]}]{node_name[1:]}"
            self._run_cmd(f"pkill -f '{pattern}' 2>/dev/null", timeout=5)
            time.sleep(1)

        # Lancer le nouveau
        log_file = os.path.join(LOG_DIR, f"{node_name}.log")
        full_cmd = f"{self.ros_env} nohup {launch_cmd} > {log_file} 2>&1 &"
        rc, out, err = self._run_cmd(full_cmd, timeout=5)

        self.restart_counts[node_name] = count + 1
        self.last_restart[node_name] = time.time()

        if rc == 0:
            print(f"   ✅ {node_name} relancé (log: {log_file})")
            return True
        else:
            print(f"   ❌ Échec: {err[:200]}")
            return False

    def check_all(self):
        """Vérifie tous les nœuds configurés."""
        print(f"\n{'='*50}")
        print(f"🔍 Watchdog check — {time.strftime('%H:%M:%S')}")
        print(f"{'='*50}")

        issues = []

        for node_name, launch_cmd, topic, priority, delay in NODES_CONFIG:
            # Vérifier si le nœud est actif
            active = self._is_node_active(node_name)

            reason = None
            if not active:
                status = "❌ INACTIF"
                reason = "node down"
            else:
                # Vérifier si le topic publie (si applicable)
                if topic:
                    publishing = self._is_topic_publishing(topic)
                    if not publishing:
                        status = "⚠️  Nœud actif mais topic mort"
                        reason = f"topic {topic} mort"
                    else:
                        status = "✅ OK"
                # Vérification spéciale pour rosbridge (port 9090)
                elif node_name == "rosbridge_websocket":
                    port_ok = self._is_port_open(9090)
                    if port_ok:
                        status = "✅ OK"
                    else:
                        status = "⚠️ Port 9090 fermé"
                        reason = "port 9090 fermé"
                else:
                    status = "✅ OK"

            # Anti faux-négatifs : "ros2 topic hz" échoue parfois sous charge
            # alors que le nœud va bien. On ne redémarre qu'après 2 échecs
            # CONSÉCUTIFS du même nœud.
            if reason is None:
                self._fail_counts.pop(node_name, None)
            else:
                count = self._fail_counts.get(node_name, 0) + 1
                self._fail_counts[node_name] = count
                if count >= 2:
                    # Correction faite sur le robot (récupérée le 09/11) : ces nœuds
                    # sont lancés à la main, le watchdog ne fait que les surveiller.
                    if node_name in ("ws_audio_asr", "agent_process"):
                        status += " [surveillance seule, lancement externe]"
                    else:
                        issues.append((node_name, launch_cmd, priority, delay, f"{reason} (x{count})"))
                else:
                    status += " [1er échec, on attend le prochain cycle]"

            icon = "🔴" if priority == 1 else ("🟡" if priority == 2 else "🟢")
            print(f"  {icon} {node_name:30s} {status}")

        # Redémarrer les nœuds tombés (par ordre de priorité)
        if issues:
            print(f"\n🚨 {len(issues)} problème(s) détecté(s):")
            # Trier par priorité (1=critique d'abord)
            issues.sort(key=lambda x: x[2])

            for node_name, launch_cmd, priority, delay, reason in issues:
                print(f"   → {node_name}: {reason}")
                if delay > 0:
                    time.sleep(delay)
                self._restart_node(node_name, launch_cmd, priority)
        else:
            print(f"\n✅ Tous les systèmes opérationnels")

        # NOTE: la caméra aurora est gérée EXCLUSIVEMENT par camera_supervisor.py
        # (vérification du flux + relance USB dédiée). Ne pas la gérer ici :
        # double gestion = conflits de kill/relance (vécu 01/11).

        return len(issues)

    def run(self):
        """Boucle principale du watchdog."""
        print(f"🐕 Robot Watchdog démarré (intervalle: {self.interval}s)")
        print(f"   Nœuds surveillés: {len(NODES_CONFIG)}")
        print(f"   Max redémarrages/nœud: {self.max_restarts}")
        print(f"   Logs: {LOG_DIR}/")
        print(f"   Ctrl+C pour arrêter\n")

        while self.running:
            try:
                self.check_all()
            except KeyboardInterrupt:
                print("\n🛑 Arrêt du watchdog")
                self.running = False
                break
            except Exception as e:
                print(f"❌ Erreur watchdog: {e}")

            # Attendre avant le prochain check
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description='Robot Watchdog')
    parser.add_argument('--interval', type=int, default=10, help='Intervalle entre checks (secondes)')
    parser.add_argument('--max-restarts', type=int, default=5, help='Max redémarrages par nœud')
    args = parser.parse_args()

    watchdog = RobotWatchdog(interval=args.interval, max_restarts=args.max_restarts)
    watchdog.run()


if __name__ == '__main__':
    main()
