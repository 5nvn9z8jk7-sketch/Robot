#!/usr/bin/env python3
# encoding: utf-8
"""
pc_audio_asr_server.py — Serveur WebSocket pour ASR depuis un PC.

Reçoit de l'audio brut (int16 PCM, 16kHz, mono) via WebSocket depuis un
navigateur PC, fait la VAD + ASR (sherpa-onnx FR) localement, publie le
texte sur /vocal_detect/asr_result, et renvoie la transcription au client.

Protocole WebSocket (port 9091):
  - Messages binaires = chunks audio int16 PCM 16kHz mono
  - Messages texte JSON = reponses {"type": "transcript", "text": "..."}

Usage: python3 pc_audio_asr_server.py
"""

import asyncio
import json
import os
import sys
import threading
import time

import numpy as np

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

import websockets

from speech import speech  # applique le patch
from speech.speech_offline_patch import OfflineRealTimeASR, DEFAULT_SHERPA_DIR

WS_PORT = 9091
SAMPLE_RATE = 16000
ENERGY_THRESHOLD = 300    # seuil VAD (bruit de fond ~160)
SILENCE_CHUNKS = 6        # ~3s de silence = fin de phrase (chunks de 0.5s)
MAX_CHUNKS = 30           # ~15s max par phrase
MIN_CHUNKS = 3            # minimum 1.5s pour transcrire


class PCAudioASRNode(Node):
    def __init__(self):
        super().__init__('pc_audio_asr_server')

        lang = os.environ.get('SPEECH_LANG', 'fr')
        sherpa_dir = os.environ.get('SHERPA_DIR', DEFAULT_SHERPA_DIR)

        self.get_logger().info(f'Initialisation ASR offline (lang={lang})...')
        self._asr = OfflineRealTimeASR(language=lang, sherpa_dir=sherpa_dir)
        self._recognizer = self._asr._recognizer

        if self._recognizer is None:
            self.get_logger().error('ERREUR: Recognizer sherpa-onnx non initialise!')
        else:
            self.get_logger().info('Recognizer sherpa-onnx pret')

        self.asr_pub = self.create_publisher(String, '/vocal_detect/asr_result', 10)
        self.get_logger().info(f'Serveur WebSocket ASR sur port {WS_PORT}')

    def transcribe(self, audio_chunks):
        """Transcrit une liste de chunks int16 16kHz. Retourne le texte."""
        if not self._recognizer or not audio_chunks:
            return ''
        try:
            s = np.concatenate(audio_chunks).astype(np.float32) / 32768.0
            if len(s) < int(SAMPLE_RATE * 0.5):
                return ''
            stream = self._recognizer.create_stream()
            stream.accept_waveform(SAMPLE_RATE, s)
            stream.input_finished()
            while self._recognizer.is_ready(stream):
                self._recognizer.decode_stream(stream)
            text = self._recognizer.get_result(stream).strip()
            if text:
                self.get_logger().info(f'ASR PC: \"{text}\"')
            return text
        except Exception as e:
            self.get_logger().error(f'Erreur transcription: {e}')
            return ''

    def publish_result(self, text):
        """Publie le texte sur /vocal_detect/asr_result."""
        if text and text.strip():
            msg = String()
            msg.data = text.strip()
            self.asr_pub.publish(msg)
            self.get_logger().info(f'>>> PUBLIE: \"{text}\"')


class ClientSession:
    """Etat VAD par client WebSocket."""
    def __init__(self):
        self.audio_chunks = []
        self.silence_count = 0
        self.speaking = False


async def handle_client(websocket, asr_node):
    """Gere un client WebSocket: recoit audio, VAD, ASR, renvoie texte."""
    session = ClientSession()
    asr_node.get_logger().info(f'Client connecte: {websocket.remote_address}')

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # Chunk audio int16 PCM 16kHz mono
                try:
                    audio = np.frombuffer(message, dtype=np.int16)
                except Exception:
                    continue

                energy = float(np.abs(audio.flatten()).mean()) if len(audio) > 0 else 0

                if energy > ENERGY_THRESHOLD:
                    session.audio_chunks.append(audio.flatten())
                    session.silence_count = 0
                    if not session.speaking:
                        session.speaking = True
                        asr_node.get_logger().info(f'Debut parole (energy={energy:.0f})')
                elif session.speaking:
                    session.silence_count += 1
                    session.audio_chunks.append(audio.flatten())
                    if session.silence_count >= SILENCE_CHUNKS:
                        # Fin de phrase
                        session.speaking = False
                        n_chunks = len(session.audio_chunks)
                        asr_node.get_logger().info(
                            f'Fin parole: {n_chunks} chunks, transcription...')
                        if n_chunks >= MIN_CHUNKS:
                            text = asr_node.transcribe(session.audio_chunks)
                            if text:
                                asr_node.publish_result(text)
                                await websocket.send(json.dumps({
                                    'type': 'transcript',
                                    'text': text
                                }))
                            else:
                                await websocket.send(json.dumps({
                                    'type': 'transcript',
                                    'text': ''
                                }))
                        session.audio_chunks = []
                        session.silence_count = 0

                # Trop long -> forcer la transcription
                if len(session.audio_chunks) >= MAX_CHUNKS:
                    session.speaking = False
                    if len(session.audio_chunks) >= MIN_CHUNKS:
                        text = asr_node.transcribe(session.audio_chunks)
                        if text:
                            asr_node.publish_result(text)
                            await websocket.send(json.dumps({
                                'type': 'transcript',
                                'text': text
                            }))
                    session.audio_chunks = []
                    session.silence_count = 0

            elif isinstance(message, str):
                # Message texte (control)
                try:
                    data = json.loads(message)
                    if data.get('type') == 'ping':
                        await websocket.send(json.dumps({'type': 'pong'}))
                except Exception:
                    pass

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # Transcrire ce qui reste si le client part en parlant
        if session.speaking and len(session.audio_chunks) >= MIN_CHUNKS:
            text = asr_node.transcribe(session.audio_chunks)
            if text:
                asr_node.publish_result(text)
        asr_node.get_logger().info(f'Client deconnecte: {websocket.remote_address}')


def ros_spin_thread(node):
    """Thread pour faire tourner rclpy en parallele du serveur WebSocket."""
    rclpy.spin(node)


def main():
    rclpy.init()
    asr_node = PCAudioASRNode()

    # Thread ROS2
    ros_thread = threading.Thread(target=ros_spin_thread, args=(asr_node,), daemon=True)
    ros_thread.start()

    # Serveur WebSocket
    async def run_server():
        async with websockets.serve(
            lambda ws: handle_client(ws, asr_node),
            '0.0.0.0', WS_PORT,
            max_size=10 * 1024 * 1024,  # 10 MB max par message
            ping_interval=30,
            ping_timeout=60,
        ):
            asr_node.get_logger().info(f'Serveur WebSocket ASR demarre sur port {WS_PORT}')
            await asyncio.Future()  # run forever

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass
    finally:
        asr_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
