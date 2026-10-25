#!/usr/bin/env python3
# encoding: utf-8
"""
calibrate_pick.py — Outil de calibration interactif pour le pick-and-place.

Permet de:
  1. Voir en temps réel ce que voit le robot (détection couleur)
  2. Tester le bras seul (action voice_pick)
  3. Ajuster la distance fixe à la volée
  4. Tester la séquence complète
  5. Avancer/reculer manuellement pour trouver la bonne position

Usage:
  python3 calibrate_pick.py
"""

import json
import time
import sys
import threading

try:
    import websocket
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
    import websocket

ROBOT_WS = "ws://192.168.1.30:9090"
NODE_NAME = "/pick_and_place_node_v2"

ws = None
latest_color = None
latest_asr = None
stop_flag = False

# Distance par défaut (sera ajustée interactivement)
fixed_distance = 0.25  # mètres


def connect():
    global ws
    print("🔌 Connexion au robot...", end=" ", flush=True)
    ws = websocket.create_connection(ROBOT_WS, timeout=5)
    print("✅ Connecté")
    # S'abonner aux topics
    for topic, msg_type in [
        ("/color_detect_node/color_info", "interfaces/msg/ColorsInfo"),
        ("/tts_node/tts_text", "std_msgs/String"),
        ("/vocal_detect/asr_result", "std_msgs/String"),
    ]:
        ws.send(json.dumps({"op": "subscribe", "topic": topic, "type": msg_type}))
    print("👂 Écoute activée (couleurs + TTS + ASR)")


def listen():
    global latest_color, latest_asr
    while not stop_flag:
        try:
            msg = json.loads(ws.recv())
            if msg.get("op") == "publish":
                topic = msg.get("topic", "")
                if topic == "/color_detect_node/color_info":
                    latest_color = msg.get("msg", {}).get("data", [])
                elif topic == "/tts_node/tts_text":
                    print(f"\n   🗣️  ROBOT: \"{msg.get('msg', {}).get('data', '')}\"")
                    print_menu()
                elif topic == "/vocal_detect/asr_result":
                    latest_asr = msg.get("msg", {}).get("data", "")
        except websocket.WebSocketTimeoutException:
            continue
        except Exception:
            break


def publish_cmd_vel(linear, angular, duration_ms=0):
    """Envoie une commande de mouvement."""
    if ws:
        msg = {
            "op": "publish",
            "topic": "/controller/cmd_vel",
            "msg": {
                "linear": {"x": linear, "y": 0, "z": 0},
                "angular": {"x": 0, "y": 0, "z": angular}
            }
        }
        if duration_ms > 0:
            # Envoyer à 10Hz pendant la durée
            count = duration_ms // 100
            for _ in range(count):
                ws.send(json.dumps(msg))
                time.sleep(0.1)
            # Stop
            ws.send(json.dumps({
                "op": "publish",
                "topic": "/controller/cmd_vel",
                "msg": {"linear": {"x": 0, "y": 0, "z": 0}, "angular": {"x": 0, "y": 0, "z": 0}}
            }))
        else:
            ws.send(json.dumps(msg))


def publish_asr(text):
    if ws:
        ws.send(json.dumps({
            "op": "publish",
            "topic": "/vocal_detect/asr_result",
            "msg": {"data": text}
        }))


def set_param(name, value):
    """Modifie un paramètre ROS2 du nœud pick_and_place_node_v2."""
    if ws:
        ws.send(json.dumps({
            "op": "call_service",
            "service": f"{NODE_NAME}/set_parameters",
            "args": {
                "parameters": [{"name": name, "value": {"type": 3, "double_value": float(value)}}]
            },
            "id": f"set_{name}"
        }))


def get_param(name):
    """Lit un paramètre ROS2."""
    if ws:
        ws.send(json.dumps({
            "op": "call_service",
            "service": f"{NODE_NAME}/get_parameters",
            "args": {"names": [name]},
            "id": f"get_{name}"
        }))


def show_color_detection():
    """Affiche les dernières détections de couleur."""
    if latest_color:
        reds = [c for c in latest_color if c.get("color") == "red"]
        if reds:
            for c in reds:
                print(f"   🔴 Rouge: x={c['x']}, y={c['y']}, {c['width']}x{c['height']}")
        else:
            all_colors = [c.get("color", "?") for c in latest_color]
            print(f"   Détections: {all_colors if all_colors else 'aucune'}")
    else:
        print("   Pas encore de détection")


def run_arm_action(action_name):
    """Lance une action du bras via servo_controller."""
    if ws:
        ws.send(json.dumps({
            "op": "publish",
            "topic": "/servo_controller",
            "msg": {
                "servos": [{"id": 1, "position": 0}],
                "duration": 0
            }
        }))
    print(f"   🤖 Action bras: {action_name} (via voice_pick_node)")
    # Utiliser voice_pick_node via ASR
    publish_asr(f"{action_name} le cube")


def test_sequence():
    """Lance la séquence pick-and-place complète."""
    global fixed_distance
    print(f"\n🧪 Test séquence complète (distance fixe: {fixed_distance}m)")
    print("   → Envoi commande 'Attrape le cube rouge'...")
    publish_asr("Attrape le cube rouge")


def print_menu():
    global fixed_distance
    print("\n" + "═" * 50)
    print("  🔧 CALIBRATION PICK-AND-PLACE")
    print("═" * 50)
    print(f"  Distance fixe actuelle: {fixed_distance:.2f} m")
    print("─" * 50)
    print("  MOUVEMENT MANUEL (AZERTY):")
    print("    [Z] ou [↑] Avancer 10cm    [S] ou [↓] Reculer 10cm")
    print("    [Q] ou [←] Tourner G 10°    [D] ou [→] Tourner D 10°")
    print("    [A] Avancer 5cm     [E] Reculer 5cm")
    print("    [ESPACE] STOP")
    print("─" * 50)
    print("  BRAS:")
    print("    [G] Tester préhension (voice_pick)")
    print("    [R] Reset bras (init)")
    print("─" * 50)
    print("  PARAMÈTRES:")
    print("    [+] Augmenter distance (+5cm)")
    print("    [-] Diminuer distance (-5cm)")
    print("    [V] Voir détection couleur actuelle")
    print("─" * 50)
    print("  TEST:")
    print("    [T] Tester séquence complète")
    print("─" * 50)
    print("    [H] Aide    [X] Quitter")
    print("═" * 50)
    print("  Choix: ", end="", flush=True)


def main():
    global fixed_distance, stop_flag

    print("=" * 50)
    print("  🔧 CALIBRATION PICK-AND-PLACE — Robot Hiwonder")
    print("=" * 50)
    print()
    print("  Ce script permet de calibrer la distance pour le pick-and-place")
    print("  sans caméra depth. Place le robot près du cube rouge, puis:")
    print("  1. Ajuste la distance avec +/-")
    print("  2. Teste avec T")
    print("  3. Ajuste jusqu'à ce que le bras attrape le cube")
    print()

    connect()
    listener = threading.Thread(target=listen, daemon=True)
    listener.start()

    print_menu()

    while True:
        try:
            raw = input().strip()
            # Support flèches directionnelles (séquences ANSI)
            if raw == '[A' or raw == 'OA':  # Flèche haut
                choice = 'Z'
            elif raw == '[B' or raw == 'OB':  # Flèche bas
                choice = 'S'
            elif raw == '[D' or raw == 'OD':  # Flèche gauche
                choice = 'Q'
            elif raw == '[C' or raw == 'OC':  # Flèche droite
                choice = 'D'
            else:
                choice = raw.upper()

            if choice == "X":
                stop_flag = True
                publish_cmd_vel(0, 0)
                print("\n👋 Au revoir!")
                break

            elif choice == "H":
                print("\nAide:")
                print("  Z/S ou ↑/↓ = Avancer/Reculer 10cm")
                print("  Q/D ou ←/→ = Tourner Gauche/Droite 10°")
                print("  A/E = Avancer/Reculer 5cm (ajustement fin)")
                print("  G = Tester le bras (préhension)")
                print("  +/- = Ajuster la distance fixe")
                print("  V = Voir les détections couleur")
                print("  T = Tester la séquence complète")
                print_menu()

            # Mouvement
            elif choice == "Z":
                print("   ⬆️  Avance 10cm")
                publish_cmd_vel(-0.15, 0, 667)  # -0.15 m/s * 0.667s = -10cm
            elif choice == "S":
                print("   ⬇️  Recule 10cm")
                publish_cmd_vel(0.15, 0, 667)
            elif choice == "A":
                print("   ⬆️  Avance 5cm")
                publish_cmd_vel(-0.15, 0, 333)
            elif choice == "E":
                print("   ⬇️  Recule 5cm")
                publish_cmd_vel(0.15, 0, 333)
            elif choice == "Q":
                print("   ⬅️  Tourne G 10°")
                publish_cmd_vel(0, -0.8, 218)  # 10° = 0.175 rad / 0.8 = 0.218s
            elif choice == "D":
                print("   ➡️  Tourne D 10°")
                publish_cmd_vel(0, 0.8, 218)
            elif choice == " " or choice == "":
                publish_cmd_vel(0, 0)
                print("   ⏹️  STOP")

            # Bras
            elif choice == "G":
                print("   🤖 Test préhension...")
                publish_asr("Attrape")
            elif choice == "R":
                print("   🤖 Reset bras...")
                publish_asr("Repose")

            # Paramètres
            elif choice == "+":
                fixed_distance += 0.05
                set_param("fixed_distance_m", fixed_distance)
                print(f"   📏 Distance fixe: {fixed_distance:.2f} m (+5cm)")
            elif choice == "-":
                fixed_distance = max(0.05, fixed_distance - 0.05)
                set_param("fixed_distance_m", fixed_distance)
                print(f"   📏 Distance fixe: {fixed_distance:.2f} m (-5cm)")
            elif choice == "V":
                print("   📷 Détection couleur:")
                show_color_detection()
                print_menu()

            # Test
            elif choice == "T":
                test_sequence()

            else:
                print(f"   ❌ Inconnu: '{choice}' — tape H pour l'aide")

        except KeyboardInterrupt:
            stop_flag = True
            publish_cmd_vel(0, 0)
            print("\n👋 Interruption")
            break
        except EOFError:
            break

    if ws:
        ws.close()


if __name__ == "__main__":
    main()
