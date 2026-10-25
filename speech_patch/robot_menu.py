#!/usr/bin/env python3
# encoding: utf-8
"""
robot_menu.py v2 — Menu interactif pour controler le robot.

Usage:
    python3 robot_menu.py
"""

import argparse
import json
import subprocess
import sys
import time

import websocket


COMMANDS = {
    '1': ('Avance',          {'type': 'move', 'action': 'forward',  'duration': 2.0}),
    '2': ('Recule',          {'type': 'move', 'action': 'backward', 'duration': 2.0}),
    '3': ('Tourne a gauche', {'type': 'move', 'action': 'turn_left',  'duration': 1.5}),
    '4': ('Tourne a droite', {'type': 'move', 'action': 'turn_right', 'duration': 1.5}),
    '5': ('Stop',            {'type': 'move', 'action': 'stop',     'duration': 0}),
    '6': ('Bonjour (TTS)',   {'type': 'tts',  'text': 'Bonjour ! Je suis le robot ROSOrin, pret a t\'aider.'}),
    '7': ('Qui es-tu ? (LLM)', {'type': 'asr', 'text': 'qui es-tu'}),
    '8': ('Attrape cube rouge (auto)', {'type': 'pick_and_place'}),
    '9': ('Niveau batterie', {'type': 'battery'}),
    '0': ('Quitter',         {'type': 'quit'}),
}

LINEAR_SPEED = 0.3
ANGULAR_SPEED = 1.0


class RobotMenu:
    def __init__(self, robot_ip='192.168.1.30', port=9090):
        self.robot_ip = robot_ip
        self.ws_url = 'ws://' + robot_ip + ':' + str(port)
        self.ws = None
        self._connect()

    def _connect(self):
        try:
            self.ws = websocket.create_connection(self.ws_url, timeout=5)
            self.ws.settimeout(0.5)
            print('Connecte au robot (' + self.ws_url + ')')
        except Exception as e:
            print('ERREUR: Impossible de se connecter au robot: ' + str(e))
            sys.exit(1)

    def _send(self, topic, msg):
        self.ws.send(json.dumps({'op': 'publish', 'topic': topic, 'msg': msg}))

    def _ssh(self, cmd):
        try:
            result = subprocess.run(
                ['ssh', '-o', 'ConnectTimeout=5', 'robot', cmd],
                capture_output=True, timeout=10,
            )
            return result.stdout.decode('utf-8', errors='replace').strip()
        except Exception as e:
            return 'Erreur SSH: ' + str(e)

    def _move(self, action, duration):
        speeds = {
            'forward':   {'linear': {'x': LINEAR_SPEED, 'y': 0, 'z': 0}, 'angular': {'x': 0, 'y': 0, 'z': 0}},
            'backward':  {'linear': {'x': -LINEAR_SPEED, 'y': 0, 'z': 0}, 'angular': {'x': 0, 'y': 0, 'z': 0}},
            'turn_left':  {'linear': {'x': 0, 'y': 0, 'z': 0}, 'angular': {'x': 0, 'y': 0, 'z': ANGULAR_SPEED}},
            'turn_right': {'linear': {'x': 0, 'y': 0, 'z': 0}, 'angular': {'x': 0, 'y': 0, 'z': -ANGULAR_SPEED}},
            'stop':      {'linear': {'x': 0, 'y': 0, 'z': 0}, 'angular': {'x': 0, 'y': 0, 'z': 0}},
        }
        speed = speeds.get(action, speeds['stop'])
        if action == 'stop' or duration == 0:
            self._send('/controller/cmd_vel', speed)
            return
        print('  -> ' + action + ' pendant ' + str(duration) + 's...')
        for _ in range(int(duration * 10)):
            self._send('/controller/cmd_vel', speed)
            time.sleep(0.1)
        self._send('/controller/cmd_vel', speeds['stop'])
        print('  -> Stop')

    def _tts(self, text):
        print('  -> TTS: "' + text + '"')
        self._send('/tts_node/tts_text', {'data': text})

    def _asr(self, text):
        print('  -> Commande: "' + text + '"')
        self._send('/vocal_detect/asr_result', {'data': text})

    def _pick_and_place(self):
        print('  -> Lancement des noeuds pick-and-place...')
        # Tuer les anciens (force kill)
        self._ssh('pkill -9 -f pick_and_place_node 2>/dev/null; pkill -9 -f voice_pick_node 2>/dev/null; pkill -9 -f simple_color_detect 2>/dev/null; sleep 2')
        # Lancer les 3 noeuds via le script clean (une seule session SSH)
        self._ssh('bash ~/start_pick_clean.sh')
        print('     Noeuds lances, attente 8 secondes...')
        time.sleep(8)
        # Verifier avec ps (evite les enregistrements fantomes de ros2 node list)
        procs = self._ssh("ps aux | grep -E 'pick_and_place_node|simple_color_detect|voice_pick_node' | grep -v grep | awk '{print $11, $12}'")
        if 'pick_and_place_node' in procs:
            print('  -> Noeud pick_and_place ACTIF')
        else:
            print('  -> PROBLEME: pick_and_place_node non demarre')
            print('     Logs: ssh robot "tail -20 ~/pick_and_place.log"')
        if 'simple_color_detect' in procs:
            print('  -> Detecteur couleur ACTIF')
        else:
            print('  -> PROBLEME: simple_color_detect non demarre')
            print('     Logs: ssh robot "tail -20 ~/simple_color.log"')
        # Verifier que la detection publie
        color_check = self._ssh("bash -lc 'source /opt/ros/humble/setup.bash && timeout 3 ros2 topic echo /color_detect_node/color_info --once 2>/dev/null | head -5'")
        if 'red' in color_check:
            print('  -> Detection rouge CONFIRMEE')
        else:
            print('  -> Pas de detection rouge pour l instant (normal si pas de cube)')
        print('  -> Envoi commande: "attrape le cube rouge"')
        self._send('/vocal_detect/asr_result', {'data': 'attrape le cube rouge'})
        print('  -> Mets un cube rouge devant le robot !')
        print('     Logs: ssh robot "tail -f ~/pick_and_place.log"')

    def _battery(self):
        try:
            self.ws.send(json.dumps({
                'op': 'subscribe', 'topic': '/ros_robot_controller/battery',
                'type': 'std_msgs/msg/UInt16', 'id': 'batt',
            }))
            time.sleep(0.5)
            try:
                while True:
                    msg = json.loads(self.ws.recv())
                    if msg.get('topic') == '/ros_robot_controller/battery':
                        mv = msg['msg']['data']
                        v = mv / 1000.0
                        pct = max(0, min(100, int((v - 10.0) / 2.0 * 100)))
                        print('  -> Batterie: ' + str(mv) + ' mV (' + str(round(v,2)) + 'V, ~' + str(pct) + '%)')
                        break
            except Exception:
                print('  -> Batterie: pas de reponse (robot sur secteur?)')
            self.ws.send(json.dumps({'op': 'unsubscribe', 'id': 'batt'}))
        except Exception as e:
            print('  -> Erreur: ' + str(e))

    def execute(self, cmd_num):
        if cmd_num not in COMMANDS:
            print('  Commande inconnue: ' + cmd_num)
            return True
        desc, cmd = COMMANDS[cmd_num]
        if cmd['type'] == 'quit':
            return False
        print()
        print('[' + cmd_num + '] ' + desc)
        if cmd['type'] == 'move':
            self._move(cmd['action'], cmd['duration'])
        elif cmd['type'] == 'tts':
            self._tts(cmd['text'])
        elif cmd['type'] == 'asr':
            self._asr(cmd['text'])
        elif cmd['type'] == 'pick_and_place':
            self._pick_and_place()
        elif cmd['type'] == 'battery':
            self._battery()
        return True

    def run(self):
        print()
        print('=' * 55)
        print('  CONTROLE DU ROBOT — Menu interactif')
        print('=' * 55)
        print()
        print('  Tape un numero puis Entree:')
        print()
        print('    1  Avance')
        print('    2  Recule')
        print('    3  Tourne a gauche')
        print('    4  Tourne a droite')
        print('    5  Stop')
        print('    6  Bonjour (le robot parle)')
        print('    7  Qui es-tu ? (LLM repond)')
        print('    8  Attrape le cube rouge (auto)')
        print('    9  Niveau batterie')
        print('    0  Quitter')
        print()
        print('=' * 55)
        while True:
            try:
                choice = input('\nCommande > ').strip()
                if not choice:
                    continue
                if not self.execute(choice):
                    break
            except KeyboardInterrupt:
                print()
                break
            except EOFError:
                break
        print('\nAu revoir !')
        self.ws.close()


def main():
    parser = argparse.ArgumentParser(description='Menu interactif pour controler le robot')
    parser.add_argument('--robot', default='192.168.1.30', help='IP du robot')
    parser.add_argument('--port', type=int, default=9090, help='Port rosbridge')
    args = parser.parse_args()
    menu = RobotMenu(robot_ip=args.robot, port=args.port)
    menu.run()


if __name__ == '__main__':
    main()
