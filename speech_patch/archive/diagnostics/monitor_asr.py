#!/usr/bin/env python3
# monitor_asr.py — Écoute les topics vocaux via rosbridge
# Usage: python3 monitor_asr.py [duree_secondes]
# ASCII only — pas d'emoji pour éviter UnicodeEncodeError sur Windows

import sys
import json
import time
import threading

try:
    from websocket import WebSocketApp
except ImportError:
    print("[ERREUR] Installe websocket-client: pip install websocket-client")
    sys.exit(1)

ROBOT_WS = "ws://192.168.1.30:9090"

# topic -> (type ROS2, label court)
TOPICS = {
    "/vocal_detect/asr_result":       ("std_msgs/msg/String",       "ASR"),
    "/vocal_detect/wakeup":           ("std_msgs/msg/Bool",         "WAKE"),
    "/agent_process/result":          ("std_msgs/msg/String",       "LLM"),
    "/tts_node/tts_text":             ("std_msgs/msg/String",       "TTS"),
    "/tts_node/play_finish":          ("std_msgs/msg/Bool",         "TTS_DONE"),
    "/controller/cmd_vel":            ("geometry_msgs/msg/Twist",   "MOVE"),
    "/ros_robot_controller/battery":  ("sensor_msgs/msg/BatteryState", "BATT"),
}

duration = int(sys.argv[1]) if len(sys.argv) > 1 else 60

received_count = 0

def on_message(ws, message):
    global received_count
    try:
        data = json.loads(message)
        if data.get("op") != "publish":
            return
        topic = data.get("topic", "")
        msg = data.get("msg", {})
        ts = time.strftime("%H:%M:%S")

        if topic == "/vocal_detect/asr_result":
            text = msg.get("data", "")
            if text.strip():
                received_count += 1
                print(f"\n[{ts}] >>> [ASR] '{text}'  (recu #{received_count})")
            else:
                print(f"[{ts}] [ASR] (vide)")

        elif topic == "/vocal_detect/wakeup":
            val = msg.get("data", False)
            print(f"[{ts}] [WAKE] {'OUI' if val else 'non'}")

        elif topic == "/agent_process/result":
            text = msg.get("data", "")
            if text.strip():
                print(f"[{ts}] [LLM] '{text[:300]}'")

        elif topic == "/tts_node/tts_text":
            text = msg.get("data", "")
            if text.strip():
                print(f"[{ts}] [TTS] parle: '{text[:200]}'")

        elif topic == "/tts_node/play_finish":
            val = msg.get("data", False)
            if val:
                print(f"[{ts}] [TTS] lecture terminee")

        elif topic == "/controller/cmd_vel":
            lin = msg.get("linear", {})
            ang = msg.get("angular", {})
            lx = lin.get("x", 0) or 0
            lz = ang.get("z", 0) or 0
            if abs(lx) > 0.01 or abs(lz) > 0.01:
                direction = ""
                if lx > 0: direction += "AVANCE "
                elif lx < 0: direction += "RECULE "
                if lz > 0: direction += "GAUCHE"
                elif lz < 0: direction += "DROITE"
                print(f"[{ts}] >>> [MOVE] {direction} (v={lx:.2f} rot={lz:.2f})")

        elif topic == "/ros_robot_controller/battery":
            pct = msg.get("percentage", 0) or 0
            voltage = msg.get("voltage", 0) or 0
            print(f"[{ts}] [BATT] {pct*100:.0f}% ({voltage:.1f}V)")

    except json.JSONDecodeError:
        pass
    except Exception as e:
        print(f"[ERREUR] {e}")

def on_error(ws, error):
    print(f"[ERREUR WS] {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"[WS] Ferme (code={close_status_code})")

def on_open(ws):
    print(f"[WS] Connecte a {ROBOT_WS}")
    for topic, (ros_type, label) in TOPICS.items():
        sub_msg = json.dumps({
            "op": "subscribe",
            "topic": topic,
            "type": ros_type,
            "throttle_rate": 0
        })
        ws.send(sub_msg)
        print(f"[WS] Abonne: {topic} ({label})")
    print(f"\n{'='*55}")
    print(f"  MONITORING ACTIF — parle au robot maintenant!")
    print(f"  Duree: {duration}s — Ctrl+C pour arreter")
    print(f"  Essaie: 'Avance', 'Recule', 'Tourne a gauche',")
    print(f"         'Stop', 'Bonjour', 'Quelle heure est-il?'")
    print(f"{'='*55}\n")

def main():
    ws = WebSocketApp(
        ROBOT_WS,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.run_forever(ping_interval=30, ping_timeout=10)

if __name__ == "__main__":
    ws_holder = {}

    def delayed_close():
        time.sleep(duration)
        print(f"\n[TIMER] {duration}s écoulées — arrêt du monitoring")
        if "ws" in ws_holder:
            ws_holder["ws"].close()

    orig_on_open = on_open
    def wrapped_on_open(ws):
        ws_holder["ws"] = ws
        orig_on_open(ws)

    timer = threading.Thread(target=delayed_close, daemon=True)
    timer.start()

    try:
        ws = WebSocketApp(
            ROBOT_WS,
            on_open=wrapped_on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        ws.run_forever(ping_interval=30, ping_timeout=10)
    except KeyboardInterrupt:
        print("\n[STOP] Interrompu")
    except Exception as e:
        print(f"\n[ERREUR] {e}")
    finally:
        print(f"\n[RESUME] {received_count} message(s) ASR recu(s)")
