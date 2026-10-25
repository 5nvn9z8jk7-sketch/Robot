#!/usr/bin/env python3
# encoding: utf-8
"""
llm_move_bridge_node v3 — Pont ASR -> mouvement fiable + LLM pour conversation.

Architecture :
  /vocal_detect/asr_result (ASR)
       |
       +---> mots-cles de mouvement -> execution immediate + TTS confirmation
       |
       +---> salutations -> TTS direct
       |
       +---> commandes pick_and_place -> IGNOREES (gerees par pick_and_place_node)
       |
       +---> agent_process (LLM) -> reponse conversationnelle -> TTS
            (mais pas si la derniere commande etait pick_and_place)

Souscrit :
  /vocal_detect/asr_result  (std_msgs/String) — texte ASR
  /agent_process/result     (std_msgs/String) — reponse LLM (TTS only)
  /vocal_detect/wakeup       (std_msgs/Bool)   — interruption

Publie :
  /controller/cmd_vel       (geometry_msgs/Twist) — commandes moteurs
  /tts_node/tts_text         (std_msgs/String)     — reponse vocale
"""
import re
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from geometry_msgs.msg import Twist

DEFAULT_LINEAR_SPEED = 0.2   # m/s
DEFAULT_ANGULAR_SPEED = 1.0  # rad/s
DEFAULT_DURATION = 2.0       # secondes

# Mots-cles ASR -> direction
KEYWORD_ACTIONS = [
    (['stop', 'arrete', 'arreter', 'stoppe', 'stopper', 'pause', 'halt'], 'stop'),
    (['recule', 'reculer', 'arriere', 'derriere', 'back'], 'backward'),
    (['avance', 'avancer', 'avant', 'devant', 'forward', 'marche', 'vas-y', 'go'], 'forward'),
    (['gauche', 'left'], 'turn_left'),
    (['droite', 'right'], 'turn_right'),
]

WAKE_WORDS = ['robot', 'robo', 'hiwonder', 'rosorin', 'ros orin', 'hey robot', 'ok robot', 'hey robo']

TTS_CONFIRM = {
    'forward': "J'avance",
    'backward': "Je recule",
    'turn_left': "Je tourne a gauche",
    'turn_right': "Je tourne a droite",
    'stop': "J'arrete",
}

GREETINGS = {
    'bonjour': "Bonjour ! Je suis le robot ROSOrin. Que puis-je faire pour toi ?",
    'salut': "Salut ! Comment ca va ?",
    'hello': "Hello ! I'm here.",
    'hiwonder': "Oui ? Je suis le robot Hiwonder, pret a t'aider.",
    'hey': "Hey ! Je t'ecoute.",
    'coucou': "Coucou !",
    'qui es-tu': "Je suis le robot ROSOrin, un robot intelligent.",
    'qui es tu': "Je suis le robot ROSOrin, un robot intelligent.",
    'comment ca va': "Ca va tres bien, merci ! Et toi ?",
    'comment ça va': "Ca va tres bien, merci ! Et toi ?",
    'merci': "De rien ! Avec plaisir.",
}

# Mots-cles pick_and_place — ces commandes sont gerees par pick_and_place_node
# Le bridge ne doit PAS les envoyer au LLM ni y reagir
PAP_KEYWORDS = ['cube', 'objet', 'balle', 'block', 'bloc', 'cherche', 'chercher',
                'trouve', 'trouver', 'va chercher', 'va ramasser', 'ramasse le', 'attrape le',
                'attraper le', 'prends le', 'prendre le', 'saisis le']


class LLMMoveBridge(Node):
    def __init__(self):
        super().__init__('llm_move_bridge')

        self.interrupt = False
        self._lock = threading.Lock()
        self._moving = False
        self._last_move_time = 0.0
        self._llm_response = ''
        self._last_asr_text = ''
        self._last_asr_is_pap = False

        self.cmd_vel_pub = self.create_publisher(Twist, '/controller/cmd_vel', 1)
        self.tts_text_pub = self.create_publisher(String, '/tts_node/tts_text', 1)

        self.create_subscription(
            String, '/vocal_detect/asr_result', self._asr_cb, 1)
        self.create_subscription(
            String, '/agent_process/result', self._llm_cb, 1)
        self.create_subscription(
            Bool, '/vocal_detect/wakeup', self._wakeup_cb, 1)

        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

        self.get_logger().info('llm_move_bridge v3 pret — commandes vocales directes + LLM conversation')

    def _asr_cb(self, msg):
        text = msg.data.strip()
        if not text:
            return
        self.get_logger().info(f'ASR: "{text}"')
        if not text:
            return
        self.get_logger().info(f'ASR: "{text}"')

        text_lower = text.lower()

        # Detecter si c'est une commande pick_and_place
        is_pap = any(kw in text_lower for kw in PAP_KEYWORDS)
        with self._lock:
            self._last_asr_text = text_lower
            self._last_asr_is_pap = is_pap

        if is_pap:
            self.get_logger().info('Commande pick_and_place detectee — ignoree par le bridge (geree par pick_and_place_node)')
            return  # Ne pas traiter comme mouvement ni conversation

        self._handle_asr_text(text)

    def _llm_cb(self, msg):
        with self._lock:
            # Ne pas enregistrer la reponse LLM si la derniere commande etait pick_and_place
            if self._last_asr_is_pap:
                self.get_logger().info('Reponse LLM ignoree (commande pick_and_place en cours)')
                return
            self._llm_response = msg.data

    def _wakeup_cb(self, msg):
        with self._lock:
            if self._moving:
                self.get_logger().info('wakeup interrupt')
                self.interrupt = bool(msg.data)

    def _detect_command(self, text):
        text_lower = text.lower()

        duration = 0.0
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:seconde|secondes|sec|s)\b', text_lower)
        if m:
            duration = float(m.group(1).replace(',', '.'))

        distance = 0.0
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:metre|metres|metres|m)\b', text_lower)
        if m:
            distance = float(m.group(1).replace(',', '.'))

        for keywords, direction in KEYWORD_ACTIONS:
            for kw in keywords:
                if kw in text_lower:
                    return direction, distance, duration

        return None

    def _handle_asr_text(self, text):
        text_lower = text.lower()

        # 1. Salutations -> TTS direct
        for keyword, response in GREETINGS.items():
            if keyword in text_lower:
                self.get_logger().info(f'Salutation detectee: "{keyword}"')
                msg = String()
                msg.data = response
                self.tts_text_pub.publish(msg)
                return

        # 2. Commande de mouvement
        cmd = self._detect_command(text)
        if cmd is None:
            return  # Pas une commande -> laisse le LLM gerer

        direction, distance, duration = cmd
        self.get_logger().info(
            f'Commande detectee: {direction} (dist={distance}, dur={duration})')

        confirm = TTS_CONFIRM.get(direction, 'OK')
        msg = String()
        msg.data = confirm
        self.tts_text_pub.publish(msg)

        threading.Thread(
            target=self._execute_movement,
            args=(direction, distance, duration),
            daemon=True
        ).start()

    def _execute_movement(self, direction, distance, duration):
        with self._lock:
            self._moving = True
            self._last_move_time = time.time()

        try:
            if direction == 'stop':
                self.cmd_vel_pub.publish(Twist())
                self.get_logger().info('Stop envoye')
                return

            if distance > 0:
                speed = DEFAULT_ANGULAR_SPEED if 'turn' in direction else DEFAULT_LINEAR_SPEED
                final_duration = distance / speed
            elif duration > 0:
                final_duration = duration
            else:
                final_duration = DEFAULT_DURATION

            self.get_logger().info(
                f'Mouvement: {direction}, duree: {final_duration:.2f}s')

            twist = Twist()
            if direction == 'forward':
                twist.linear.x = DEFAULT_LINEAR_SPEED
            elif direction == 'backward':
                twist.linear.x = -DEFAULT_LINEAR_SPEED
            elif direction == 'turn_left':
                twist.angular.z = DEFAULT_ANGULAR_SPEED
            elif direction == 'turn_right':
                twist.angular.z = -DEFAULT_ANGULAR_SPEED

            self.cmd_vel_pub.publish(twist)

            start = time.time()
            while time.time() - start < final_duration:
                with self._lock:
                    if self.interrupt:
                        self.interrupt = False
                        self.get_logger().info('Mouvement interrompu')
                        break
                time.sleep(0.1)

        finally:
            self.cmd_vel_pub.publish(Twist())
            with self._lock:
                self._moving = False
            self.get_logger().info('Mouvement termine, stop envoye')

    def _process_loop(self):
        while rclpy.ok():
            with self._lock:
                response = self._llm_response
                self._llm_response = ''

            if response:
                self._tts_from_llm(response)

            time.sleep(0.05)

    def _tts_from_llm(self, response_str):
        start = response_str.find('{')
        if start >= 0:
            depth = 0
            end = start
            for i, ch in enumerate(response_str[start:], start):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            try:
                import json
                data = json.loads(response_str[start:end])
                text = data.get('response', '')
                if text:
                    self.get_logger().info(f'LLM TTS: {text[:80]}')
                    msg = String()
                    msg.data = text
                    self.tts_text_pub.publish(msg)
                    return
            except Exception:
                pass

        if len(response_str) < 200:
            self.get_logger().info(f'LLM TTS (brut): {response_str[:80]}')
            msg = String()
            msg.data = response_str
            self.tts_text_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = LLMMoveBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
