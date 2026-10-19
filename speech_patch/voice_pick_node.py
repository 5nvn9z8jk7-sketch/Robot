#!/usr/bin/env python3
# encoding: utf-8
"""
voice_pick_node â ContrÃ´le vocal du bras pour attraper/dÃ©poser des objets.

Ãcoute /vocal_detect/asr_result (notre ASR) et exÃ©cute les actions
de bras prÃ©-enregistrÃ©es (voice_pick, voice_give, etc.) via ActionGroupController.

Commandes vocales :
  "attrape" / "prends" / "ramasse" / "pick"  -> action voice_pick
  "donne" / "donne moi" / "viens"           -> action voice_give
  "lÃ¢che" / "pose" / "dÃ©pose" / "place"     -> action place_basket
"""
import re
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from servo_controller_msgs.msg import ServosPosition
from servo_controller.action_group_controller import ActionGroupController

ACTION_GROUPS_PATH = '/home/ubuntu/software/arm_pc/ActionGroups'

# Mots-clÃ©s -> nom d'action
PICK_KEYWORDS = ['attrape', 'attraper', 'prends', 'prendre', 'ramasse', 'ramasser',
                 'pick', 'saisis', 'saisir', 'cube', 'balle', 'objet']
GIVE_KEYWORDS = ['donne', 'donnemoi', 'donne moi', 'pass', 'viens', 'give', 'tends']
PLACE_KEYWORDS = ['pose', 'dÃ©pose', 'depose', 'lÃ¢che', 'lache', 'place', 'mets', 'met']
INIT_KEYWORDS = ['init', 'reset', 'position initiale', 'repos']


class VoicePickNode(Node):
    def __init__(self):
        super().__init__('voice_pick_node')

        self.controller = ActionGroupController(
            self.create_publisher(ServosPosition, 'servo_controller', 1),
            ACTION_GROUPS_PATH
        )
        self.tts_pub = self.create_publisher(String, '/tts_node/tts_text', 1)

        self.create_subscription(
            String, '/vocal_detect/asr_result', self._asr_callback, 1)

        self._lock = threading.Lock()
        self._busy = False

        self.get_logger().info('voice_pick_node pret â commandes: attrape, donne, pose')

    def _say(self, text):
        msg = String()
        msg.data = text
        self.tts_pub.publish(msg)

    def _asr_callback(self, msg):
        text = msg.data.strip().lower()
        if not text:
            return

        self.get_logger().info(f'ASR: "{text}"')

        # Ignorer les commandes pick_and_place (gérées par pick_and_place_node)
        if any(kw in text for kw in PAP_KEYWORDS):
            self.get_logger().info('Commande pick_and_place détectée, ignorée par voice_pick_node')
            return

        with self._lock:
            if self._busy:
                self.get_logger().info('Deja en cours, ignore')
                return
            self._busy = True

        # Lancer l'action dans un thread sÃ©parÃ© (non-bloquant)
        threading.Thread(target=self._handle_command, args=(text,), daemon=True).start()

    def _handle_command(self, text):
        try:
            action = None
            response = None

            # DÃ©tecter la commande
            if any(kw in text for kw in PICK_KEYWORDS):
                action = 'voice_pick'
                response = "J'attrape l'objet !"
            elif any(kw in text for kw in GIVE_KEYWORDS):
                action = 'voice_give'
                response = "Je te le donne !"
            elif any(kw in text for kw in PLACE_KEYWORDS):
                action = 'place_basket'
                response = "Je le pose."
            elif any(kw in text for kw in INIT_KEYWORDS):
                action = 'init'
                response = "Retour Ã  la position initiale."

            if action is None:
                self.get_logger().info('Pas une commande de bras reconnue')
                return

            self.get_logger().info(f'Action: {action}')
            self._say(response)

            # ExÃ©cuter l'action
            self.controller.run_action(action)
            self.get_logger().info(f'Action {action} terminee')

        except Exception as e:
            self.get_logger().error(f'Erreur: {e}')
        finally:
            with self._lock:
                self._busy = False


def main(args=None):
    rclpy.init(args=args)
    node = VoicePickNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
