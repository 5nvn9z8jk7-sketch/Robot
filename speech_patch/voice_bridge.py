#!/usr/bin/env python3
# voice_bridge.py - Pont vocal LLM (PC) -> rosbridge (robot) -> mouvement
#
# Usage:
#   python3 voice_bridge.py "Avance"
#   python3 voice_bridge.py --interactive

import json
import os
import sys
import time
import argparse
import urllib.request

try:
    import websocket
except ImportError:
    print("Installation de websocket-client...")
    os.system("pip install websocket-client -q")
    import websocket

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://192.168.1.20:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")
ROBOT_WS = os.environ.get("ROBOT_WS", "ws://192.168.1.30:9090")

LINEAR_SPEED = 0.3
ANGULAR_SPEED = 0.5
MOVE_DURATION = 2.0

SYSTEM_PROMPT = """Tu es un assistant vocal pour un robot mobile. Convertis les commandes vocales en actions.

Reponds UNIQUEMENT en JSON strict, sans texte avant ou apres :
{"action": "<action>", "response": "<phrase en francais>"}

Actions : "forward" (avancer), "backward" (reculer), "left" (tourner a gauche),
          "right" (tourner a droite), "stop" (arreter, aussi pour salutations)

Exemples :
"Avance" -> {"action": "forward", "response": "J'avance."}
"Recule" -> {"action": "backward", "response": "Je recule."}
"Tourne a gauche" -> {"action": "left", "response": "Je tourne a gauche."}
"Stop" -> {"action": "stop", "response": "Je m'arrete."}
"Bonjour" -> {"action": "stop", "response": "Bonjour !"}"""


class VoiceBridge:
    def __init__(self):
        self.ws = None
        self.connected = False

    def connect_robot(self):
        try:
            self.ws = websocket.create_connection(ROBOT_WS, timeout=10)
            self.connected = True
            print(f"[OK] Connecte au robot: {ROBOT_WS}")
            return True
        except Exception as e:
            print(f"[ERREUR] Connexion robot: {e}")
            return False

    def disconnect_robot(self):
        if self.ws:
            self.ws.close()
            self.connected = False

    def send_twist(self, linear_x=0.0, angular_z=0.0):
        if not self.connected:
            return False
        msg = {
            "op": "publish",
            "topic": "/controller/cmd_vel",
            "msg": {
                "linear": {"x": linear_x, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": angular_z}
            }
        }
        try:
            self.ws.send(json.dumps(msg))
            return True
        except Exception as e:
            print(f"[ERREUR] Envoi: {e}")
            return False

    def stop_robot(self):
        self.send_twist(0.0, 0.0)

    def execute_action(self, action, duration=MOVE_DURATION):
        action = action.lower().strip()
        if "forward" in action or "avance" in action:
            print(f"  -> Avancer ({LINEAR_SPEED} m/s, {duration}s)")
            self.send_twist(LINEAR_SPEED, 0.0)
            time.sleep(duration)
            self.stop_robot()
            return "forward"
        elif "backward" in action or "recule" in action:
            print(f"  -> Reculer ({-LINEAR_SPEED} m/s, {duration}s)")
            self.send_twist(-LINEAR_SPEED, 0.0)
            time.sleep(duration)
            self.stop_robot()
            return "backward"
        elif "left" in action or "gauche" in action:
            print(f"  -> Gauche ({ANGULAR_SPEED} rad/s, {duration}s)")
            self.send_twist(0.0, ANGULAR_SPEED)
            time.sleep(duration)
            self.stop_robot()
            return "left"
        elif "right" in action or "droite" in action:
            print(f"  -> Droite ({-ANGULAR_SPEED} rad/s, {duration}s)")
            self.send_twist(0.0, -ANGULAR_SPEED)
            time.sleep(duration)
            self.stop_robot()
            return "right"
        elif "stop" in action or "arret" in action:
            print("  -> Stop")
            self.stop_robot()
            return "stop"
        else:
            print(f"  -> Action inconnue: {action}")
            self.stop_robot()
            return None

    def ask_llm(self, command):
        prompt = f"{SYSTEM_PROMPT}\n\nCommande: \"{command}\"\n\nJSON:"
        payload = json.dumps({
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 4096, "temperature": 0.1}
        }).encode()
        try:
            req = urllib.request.Request(
                f"{OLLAMA_URL}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                return data.get("response", "")
        except Exception as e:
            print(f"[ERREUR] LLM: {e}")
            return ""

    def parse_llm_response(self, response):
        if not response:
            return None, "(pas de reponse)"
        try:
            text = response.strip()
            if "```" in text:
                text = text.split("```")[1] if "```json" not in text else text.split("```json")[1]
                text = text.split("```")[0].strip()
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                data = json.loads(text[start:end+1])
                return data.get("action", "stop"), data.get("response", "")
        except:
            pass
        text = response.lower()
        if "forward" in text or "avance" in text:
            return "forward", response[:100]
        elif "backward" in text or "recule" in text:
            return "backward", response[:100]
        elif "left" in text or "gauche" in text:
            return "left", response[:100]
        elif "right" in text or "droite" in text:
            return "right", response[:100]
        return "stop", response[:100]

    def process_command(self, command):
        print(f"\nCommande: \"{command}\"")
        print("  LLM reflechit...")
        llm_response = self.ask_llm(command)
        action, response_text = self.parse_llm_response(llm_response)
        print(f"  Reponse: \"{response_text}\"")
        print(f"  Action: {action}")
        if action and action != "stop":
            self.execute_action(action)
        elif action == "stop":
            self.stop_robot()
        return action, response_text

    def interactive_mode(self):
        print("\nMode interactif - tapez vos commandes (quit pour quitter)\n")
        try:
            while True:
                command = input("> ").strip()
                if not command:
                    continue
                if command.lower() in ("quit", "exit", "q"):
                    break
                self.process_command(command)
        except (KeyboardInterrupt, EOFError):
            print()


def main():
    parser = argparse.ArgumentParser(description="Pont vocal LLM -> Robot")
    parser.add_argument("command", nargs="?", help="Commande a executer")
    parser.add_argument("--interactive", "-i", action="store_true", help="Mode interactif")
    parser.add_argument("--duration", type=float, default=MOVE_DURATION, help="Duree mouvement (s)")
    args = parser.parse_args()

    print("=" * 50)
    print("  Pont Vocal LLM -> Robot (rosbridge)")
    print("=" * 50)
    print(f"  Ollama: {OLLAMA_URL} ({OLLAMA_MODEL})")
    print(f"  Robot : {ROBOT_WS}")
    print()

    bridge = VoiceBridge()
    if not bridge.connect_robot():
        print("[ERREUR] Connexion robot echouee")
        sys.exit(1)

    try:
        if args.interactive or not args.command:
            bridge.interactive_mode()
        else:
            bridge.process_command(args.command)
    finally:
        bridge.stop_robot()
        bridge.disconnect_robot()
        print("\n[OK] Termine")


if __name__ == "__main__":
    main()
