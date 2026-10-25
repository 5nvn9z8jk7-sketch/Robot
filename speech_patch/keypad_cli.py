#!/usr/bin/env python3
"""
Clavier numérique interactif pour contrôler le robot Hiwonder.
Commandes:
  1 = Merci       2 = Recule      3 = Ça va?
  4 = Gauche      5 = STOP        6 = Droite
  7 = Salut       8 = Avance      9 = Qui es-tu?
  0 = ARRÊT D'URGENCE   Q = Quitter   H = Aide
"""
import json
import time
import sys
import threading

try:
    import websocket
except ImportError:
    print("Installation de websocket-client...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
    import websocket

ROBOT_WS = "ws://192.168.1.30:9090"

# Commandes de mouvement: (nom, linear_x, angular_z, duree_ms)
CMDS = {
    "8": ("⬆️  AVANCE",   0.3,  0.0,  2000),
    "2": ("⬇️  RECULE",  -0.3,  0.0,  2000),
    "4": ("⬅️  GAUCHE",   0.0,  1.0,  1500),
    "6": ("➡️  DROITE",   0.0, -1.0,  1500),
    "5": ("⏹️  STOP",     0.0,  0.0,     0),
    "0": ("🛑 URGENCE",   0.0,  0.0,     0),
}

# Commandes vocales (publiées sur ASR)
VOICE_CMDS = {
    "7": ("👋 Salut",        "Dis bonjour au robot"),
    "9": ("❓ Qui es-tu",    "Présente-toi, qui es-tu ?"),
    "1": ("🙏 Merci",        "Dis merci au robot"),
    "3": ("💬 Ça va?",       "Demande au robot comment ça va"),
}

ws = None
stop_flag = False


def connect():
    global ws
    print("🔌 Connexion au robot...", end=" ", flush=True)
    ws = websocket.create_connection(ROBOT_WS, timeout=5)
    print("✅ Connecté")
    # S'abonner aux topics de retour
    for topic in ["/tts_node/tts_text", "/agent_process/result"]:
        ws.send(json.dumps({"op": "subscribe", "topic": topic, "type": "std_msgs/String"}))
    print("👂 Écoute TTS + LLM activée")


def publish_cmd_vel(linear, angular):
    if ws:
        ws.send(json.dumps({
            "op": "publish",
            "topic": "/controller/cmd_vel",
            "msg": {
                "linear": {"x": linear, "y": 0, "z": 0},
                "angular": {"x": 0, "y": 0, "z": angular}
            }
        }))


def publish_asr(text):
    if ws:
        ws.send(json.dumps({
            "op": "publish",
            "topic": "/vocal_detect/asr_result",
            "msg": {"data": text}
        }))


def send_movement(num):
    name, linear, angular, duration = CMDS[num]
    print(f"\n▶️  [{num}] {name}")

    if num in ("5", "0"):
        publish_cmd_vel(0, 0)
        print("   ⏹️  Arrêté")
        return

    # Envoyer à 10Hz pendant la durée
    count = 0
    max_count = duration // 100
    publish_cmd_vel(linear, angular)
    while count < max_count and not stop_flag:
        time.sleep(0.1)
        count += 1
        publish_cmd_vel(linear, angular)

    publish_cmd_vel(0, 0)
    print(f"   ✅ Terminé ({duration/1000:.1f}s)")


def send_voice(num):
    name, text = VOICE_CMDS[num]
    print(f"\n🗣️  [{num}] {name}")
    print(f"   → \"{text}\"")
    publish_asr(text)
    print("   📤 Envoyé à l'ASR (attend réponse LLM/TTS...)")


def listen_ws():
    """Thread d'écoute des messages rosbridge."""
    global ws
    while not stop_flag:
        try:
            msg = json.loads(ws.recv())
            if msg.get("op") == "publish":
                topic = msg.get("topic", "")
                data = msg.get("msg", {}).get("data", "")
                if topic == "/tts_node/tts_text":
                    print(f"\n   🗣️  ROBOT DIT: \"{data}\"")
                    print_menu()
                elif topic == "/agent_process/result":
                    print(f"\n   🤖 LLM: {data[:120]}")
                    print_menu()
        except websocket.WebSocketTimeoutException:
            continue
        except Exception:
            break


def print_menu():
    print("\n" + "═" * 45)
    print("  CLAVIER NUMÉRIQUE — Robot Hiwonder")
    print("═" * 45)
    print("  ┌─────┬─────┬─────┐")
    print("  │  7  │  8  │  9  │   👋Salut ⬆️Avance ❓Qui?")
    print("  │Salut│ ⬆️  │❓Qui│")
    print("  ├─────┼─────┼─────┤")
    print("  │  4  │  5  │  6  │   ⬅️Gauche ⏹️STOP  ➡️Droite")
    print("  │ ⬅️  │ ⏹️  │ ➡️  │")
    print("  ├─────┼─────┼─────┤")
    print("  │  1  │  2  │  3  │   🙏Merci  ⬇️Recule 💬Ça va")
    print("  │ 🙏  │ ⬇️  │ 💬  │")
    print("  └─────┴─────┴─────┘")
    print("  [0] 🛑 ARRÊT D'URGENCE   [ESPACE] Stop immédiat")
    print("  [Q] Quitter              [H] Aide")
    print("═" * 45)
    print("  Choix: ", end="", flush=True)


def main():
    global stop_flag

    print("=" * 45)
    print("  🤖 CLAVIER NUMÉRIQUE — Robot Hiwonder")
    print("=" * 45)

    connect()

    # Thread d'écoute
    listener = threading.Thread(target=listen_ws, daemon=True)
    listener.start()

    print_menu()

    while True:
        try:
            choice = input().strip().upper()

            if choice == "Q":
                stop_flag = True
                publish_cmd_vel(0, 0)
                print("\n👋 Au revoir!")
                break

            elif choice == "H":
                print("\nCommandes disponibles:")
                for k, (name, *_) in sorted(CMDS.items()):
                    print(f"  [{k}] {name}")
                for k, (name, text) in sorted(VOICE_CMDS.items()):
                    print(f"  [{k}] {name} → \"{text}\"")
                print("  [ESPACE] Arrêt d'urgence")
                print("  [Q] Quitter")
                print_menu()
                continue

            elif choice == " " or choice == "":
                publish_cmd_vel(0, 0)
                print("⏹️  Arrêt immédiat")
                continue

            elif choice in CMDS:
                send_movement(choice)

            elif choice in VOICE_CMDS:
                send_voice(choice)

            else:
                print(f"❌ Commande inconnue: '{choice}' — tape H pour l'aide")

        except KeyboardInterrupt:
            stop_flag = True
            publish_cmd_vel(0, 0)
            print("\n👋 Interruption — arrêt du robot")
            break
        except EOFError:
            break

    if ws:
        ws.close()


if __name__ == "__main__":
    main()
