#!/usr/bin/env python3
"""Calibration interactive du pick-and-place v5.

Affiche en temps reel la position du cube detecte et permet d'ajuster
les parametres du robot pour un attrappage precis.

Usage:
    python3 calibrate_pick_v5.py
    python3 calibrate_pick_v5.py --cube-distance 0.20  # cube a 20cm
"""

import argparse
import json
import math
import time
import threading
from websocket import create_connection

ROBOT_WS = "ws://192.168.1.30:9090"

# Parametres par defaut du pick-and-place v5
PARAMS = {
    'camera_to_gripper_offset': 0.10,  # m (10cm)
    'gripper_reach': 0.15,             # m (15cm)
    'target_size_px': 80,
    'linear_speed': 0.12,
    'angular_speed': 0.6,
    'min_y_pixel': 0,
}

class Calibrator:
    def __init__(self):
        self.ws = create_connection(ROBOT_WS, timeout=5)
        self.ws.settimeout(0.5)
        self.running = True
        self.latest_color = None
        self.latest_depth = None
        self._subscribe_topics()

    def _send(self, msg):
        self.ws.send(json.dumps(msg))

    def _subscribe_topics(self):
        # S'abonner a la detection couleur
        self._send({
            "op": "subscribe",
            "topic": "/color_detect_node/color_info",
            "type": "interfaces/msg/ColorsInfo",
            "id": "color_sub"
        })
        # S'abonner a la camera info pour les parametres intrinseques
        self._send({
            "op": "subscribe",
            "topic": "/depth_cam/depth0/camera_info",
            "type": "sensor_msgs/msg/CameraInfo",
            "id": "caminfo_sub"
        })
        # S'abonner a l'odometrie pour voir la position du robot
        self._send({
            "op": "subscribe",
            "topic": "/odom",
            "type": "nav_msgs/msg/Odometry",
            "id": "odom_sub"
        })

    def _receive_loop(self):
        while self.running:
            try:
                msg = json.loads(self.ws.recv())
                if msg.get('op') == 'publish':
                    topic = msg.get('topic', '')
                    data = msg.get('msg', {})
                    if 'color_info' in topic:
                        self.latest_color = data
                    elif 'camera_info' in topic:
                        self.camera_info = data
                    elif topic == '/odom':
                        self.latest_odom = data
            except Exception:
                pass

    def get_params(self):
        """Recupere les parametres actuels du noeud pick-and-place."""
        params = {}
        for name in ['camera_to_gripper_offset', 'gripper_reach', 'target_size_px',
                      'linear_speed', 'angular_speed', 'min_y_pixel', 'use_depth']:
            self._send({
                "op": "call_service",
                "service": f"/pick_and_place_node_v5/get_parameters",
                "args": {"names": [name]},
                "id": f"get_{name}"
            })
            try:
                while True:
                    resp = json.loads(self.ws.recv())
                    if resp.get('op') == 'service_response' and resp.get('id') == f"get_{name}":
                        values = resp.get('values', {})
                        if 'values' in values and len(values['values']) > 0:
                            params[name] = values['values'][0].get('double_value',
                                       values['values'][0].get('integer_value',
                                       values['values'][0].get('bool_value')))
                        break
            except Exception as e:
                params[name] = f"ERR: {e}"
        return params

    def set_param(self, name, value):
        """Modifie un parametre du noeud."""
        # Determiner le type
        if isinstance(value, bool):
            ptype = "bool_value"
        elif isinstance(value, int):
            ptype = "integer_value"
        else:
            ptype = "double_value"

        self._send({
            "op": "call_service",
            "service": f"/pick_and_place_node_v5/set_parameters",
            "args": {"parameters": [{ "name": name, "value": {ptype: value} }]},
            "id": f"set_{name}"
        })
        try:
            while True:
                resp = json.loads(self.ws.recv())
                if resp.get('op') == 'service_response' and resp.get('id') == f"set_{name}":
                    return resp.get('values', {}).get('results', [{}])[0].get('successful', False)
        except Exception as e:
            return False

    def trigger_pick(self, scan=False):
        """Declenche un pick-and-place."""
        topic = "/pick_and_place_node_v5/trigger_scan" if scan else "/pick_and_place_node_v5/trigger_pick"
        self._send({
            "op": "publish",
            "topic": topic,
            "msg": {"data": True}
        })

    def stop_robot(self):
        """Arret d'urgence."""
        self._send({
            "op": "publish",
            "topic": "/controller/cmd_vel",
            "msg": {"linear": {"x": 0, "y": 0, "z": 0}, "angular": {"x": 0, "y": 0, "z": 0}}
        })

    def get_cube_info(self):
        """Retourne les infos du cube detecte."""
        if not self.latest_color or 'data' not in self.latest_color:
            return None
        cubes = self.latest_color['data']
        if not cubes:
            return None
        c = cubes[0]
        return {
            'x': c.get('x', 0),
            'y': c.get('y', 0),
            'width': c.get('width', 0),
            'height': c.get('height', 0),
            'radius': c.get('radius', 0),
            'color': c.get('color', 'unknown')
        }

    def display(self):
        """Affiche l'etat en temps reel."""
        cube = self.get_cube_info()
        print("\033[2J\033[H", end="")  # Clear screen
        print("=" * 60)
        print("  CALIBRATION PICK-AND-PLACE V5")
        print("=" * 60)

        if cube:
            cx = 320  # centre image depth 640x400
            offset_x = cube['x'] - cx
            print(f"  Cube detecte : {cube['color']}")
            print(f"  Position     : x={cube['x']}, y={cube['y']} (centre=320,200)")
            print(f"  Taille       : {cube['width']}x{cube['height']} px (rayon={cube['radius']})")
            print(f"  Offset X     : {offset_x:+d} px ({'GAUCHE' if offset_x < 0 else 'DROITE' if offset_x > 0 else 'CENTRE'})")
            print(f"  Taille cible : {PARAMS['target_size_px']} px")
            if cube['radius'] > 0:
                ratio = PARAMS['target_size_px'] / cube['radius']
                print(f"  Ratio dist   : {ratio:.2f} ({'AVANCE' if ratio > 1.1 else 'RECULE' if ratio < 0.9 else 'OK'})")
        else:
            print("  Aucun cube detecte")

        print("-" * 60)
        print("  Parametres actuels :")
        print(f"    camera_to_gripper_offset = {PARAMS['camera_to_gripper_offset']:.3f} m ({PARAMS['camera_to_gripper_offset']*100:.0f} cm)")
        print(f"    gripper_reach            = {PARAMS['gripper_reach']:.3f} m ({PARAMS['gripper_reach']*100:.0f} cm)")
        print(f"    target_size_px           = {PARAMS['target_size_px']} px")
        print("-" * 60)
        print("  Commandes :")
        print("    [Z/S]  Ajuster camera_to_gripper_offset (+/- 1cm)")
        print("    [A/E]  Ajuster gripper_reach (+/- 1cm)")
        print("    [T/G]  Ajuster target_size_px (+/- 5px)")
        print("    [P]    Tester pick-and-place (direct)")
        print("    [C]    Tester scan 360 + pick")
        print("    [SPACE] Stop urgence")
        print("    [Q]    Quitter")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Calibration pick-and-place v5')
    parser.add_argument('--cube-distance', type=float, default=0.20,
                        help='Distance connue du cube en metres (pour verifier la profondeur)')
    args = parser.parse_args()

    print("Connexion au robot...")
    cal = Calibrator()

    # Thread de reception
    t = threading.Thread(target=cal._receive_loop, daemon=True)
    t.start()

    print("Connecte ! Place un cube rouge devant le robot.")
    time.sleep(1)

    try:
        while True:
            cal.display()
            cmd = input("\nCommande: ").strip().lower()

            if cmd == 'z':
                PARAMS['camera_to_gripper_offset'] = round(PARAMS['camera_to_gripper_offset'] + 0.01, 3)
                cal.set_param('camera_to_gripper_offset', PARAMS['camera_to_gripper_offset'])
                print(f"  -> camera_to_gripper_offset = {PARAMS['camera_to_gripper_offset']*100:.0f} cm")
            elif cmd == 's':
                PARAMS['camera_to_gripper_offset'] = round(max(0.0, PARAMS['camera_to_gripper_offset'] - 0.01), 3)
                cal.set_param('camera_to_gripper_offset', PARAMS['camera_to_gripper_offset'])
                print(f"  -> camera_to_gripper_offset = {PARAMS['camera_to_gripper_offset']*100:.0f} cm")
            elif cmd == 'a':
                PARAMS['gripper_reach'] = round(PARAMS['gripper_reach'] + 0.01, 3)
                cal.set_param('gripper_reach', PARAMS['gripper_reach'])
                print(f"  -> gripper_reach = {PARAMS['gripper_reach']*100:.0f} cm")
            elif cmd == 'e':
                PARAMS['gripper_reach'] = round(max(0.05, PARAMS['gripper_reach'] - 0.01), 3)
                cal.set_param('gripper_reach', PARAMS['gripper_reach'])
                print(f"  -> gripper_reach = {PARAMS['gripper_reach']*100:.0f} cm")
            elif cmd == 't':
                PARAMS['target_size_px'] += 5
                cal.set_param('target_size_px', PARAMS['target_size_px'])
                print(f"  -> target_size_px = {PARAMS['target_size_px']}")
            elif cmd == 'g':
                PARAMS['target_size_px'] = max(20, PARAMS['target_size_px'] - 5)
                cal.set_param('target_size_px', PARAMS['target_size_px'])
                print(f"  -> target_size_px = {PARAMS['target_size_px']}")
            elif cmd == 'p':
                print("  -> Test pick-and-place (direct)...")
                cal.trigger_pick(scan=False)
            elif cmd == 'c':
                print("  -> Test scan 360 + pick...")
                cal.trigger_pick(scan=True)
            elif cmd == ' ' or cmd == 'space':
                cal.stop_robot()
                print("  -> STOP")
            elif cmd == 'q':
                break
            else:
                print("  Commande inconnue")

    except KeyboardInterrupt:
        pass
    finally:
        cal.running = False
        cal.stop_robot()
        print("\nCalibration terminee. Au revoir !")


if __name__ == '__main__':
    main()
