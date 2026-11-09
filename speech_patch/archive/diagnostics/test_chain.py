#!/usr/bin/env python3
# test_chain.py — Teste la chaîne complète en publiant un ASR manuel
# et en écoutant tous les topics intermédiaires

import json
import time
import threading
from websocket import WebSocketApp

ROBOT_WS = "ws://192.168.1.30:9090"

TOPICS = {
    "/vocal_detect/asr_result": "std_msgs/msg/String",
    "/agent_process/result": "std_msgs/msg/String",
    "/agent_process/tools": "std_msgs/msg/String",
    "/agent_process/tools_result": "std_msgs/msg/String",
    "/tts_node/tts_text": "std_msgs/msg/String",
    "/controller/cmd_vel": "geometry_msgs/msg/Twist",
}

def on_open(ws):
    print("[WS] Connecte")
    for topic, msg_type in TOPICS.items():
        ws.send(json.dumps({"op": "subscribe", "topic": topic, "type": msg_type}))
        print(f"[WS] Abonne: {topic}")
    
    # Attendre 2s puis publier le test
    time.sleep(2)
    print("\n[TEST] Publication de 'avance' sur /vocal_detect/asr_result...")
    ws.send(json.dumps({
        "op": "publish",
        "topic": "/vocal_detect/asr_result",
        "msg": {"data": "avance"}
    }))
    
    # Attendre 20s pour voir la reponse
    time.sleep(20)
    print("\n[TEST] Termine")
    ws.close()

def on_message(ws, message):
    try:
        data = json.loads(message)
        if data.get("op") != "publish":
            return
        topic = data.get("topic", "")
        msg = data.get("msg", {})
        ts = time.strftime("%H:%M:%S")
        
        if topic == "/agent_process/result":
            text = msg.get("data", "")
            print(f"\n[{ts}] >>> [LLM_RESULT] {text[:400]}")
        elif topic == "/agent_process/tools":
            text = msg.get("data", "")
            print(f"[{ts}] >>> [LLM_TOOLS] {text[:400]}")
        elif topic == "/agent_process/tools_result":
            text = msg.get("data", "")
            print(f"[{ts}] [TOOLS_RESULT] {text[:200]}")
        elif topic == "/tts_node/tts_text":
            text = msg.get("data", "")
            print(f"[{ts}] [TTS] parle: '{text[:200]}'")
        elif topic == "/controller/cmd_vel":
            lin = msg.get("linear", {})
            ang = msg.get("angular", {})
            lx = lin.get("x", 0) or 0
            lz = ang.get("z", 0) or 0
            if abs(lx) > 0.01 or abs(lz) > 0.01:
                print(f"[{ts}] >>> [MOVE] v={lx:.2f} rot={lz:.2f}")
    except Exception as e:
        print(f"[ERREUR] {e}")

def on_error(ws, error):
    print(f"[ERREUR WS] {error}")

def main():
    ws = WebSocketApp(ROBOT_WS, on_open=on_open, on_message=on_message, on_error=on_error)
    ws.run_forever(ping_interval=30, ping_timeout=10)

if __name__ == "__main__":
    main()
