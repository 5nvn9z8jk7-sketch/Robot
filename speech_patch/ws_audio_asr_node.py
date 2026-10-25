#!/usr/bin/env python3
# encoding: utf-8
"""
ws_audio_asr_node.py v2 - Recoit de l'audio via WebSocket depuis un PC,
fait l'ASR sherpa-onnx FR localement, publie sur /vocal_detect/asr_result.

v2: seuil VAD abaisse a 100 + logs debug energie
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

from speech import speech
from speech.speech_offline_patch import OfflineRealTimeASR

WS_PORT = 9092
SAMPLE_RATE = 16000
ENERGY_THRESHOLD = 50
SILENCE_CHUNKS = 4
MAX_CHUNKS = 30
MIN_CHUNKS = 2


class WSAudioASRNode(Node):
    def __init__(self):
        super().__init__('ws_audio_asr')

        lang = os.environ.get('SPEECH_LANG', 'fr')
        self.get_logger().info('Initialisation ASR offline (lang=' + lang + ')...')
        self._asr = OfflineRealTimeASR(lang=lang)
        self.get_logger().info('ASR pret')

        self._pub_asr = self.create_publisher(String, '/vocal_detect/asr_result', 10)
        self._clients = {}

        self._loop = asyncio.new_event_loop()
        self._ws_thread = threading.Thread(target=self._run_ws_server, daemon=True)
        self._ws_thread.start()

        self.get_logger().info('Serveur WebSocket sur port ' + str(WS_PORT) + ' (VAD threshold=' + str(ENERGY_THRESHOLD) + ')')
        self.get_logger().info('En attente de connexion PC...')

    def _run_ws_server(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._ws_main())
        self._loop.run_forever()

    async def _ws_main(self):
        async def handler(ws):
            addr = ws.remote_address
            self.get_logger().info('Client connecte: ' + str(addr))
            self._clients[ws] = {"chunks": [], "silence_count": 0, "energy_log": 0}
            try:
                async for message in ws:
                    if isinstance(message, bytes):
                        await self._handle_audio(ws, message)
                    elif isinstance(message, str):
                        try:
                            data = json.loads(message)
                            if data.get('type') == 'ping':
                                await ws.send(json.dumps({'type': 'pong'}))
                        except:
                            pass
            except websockets.exceptions.ConnectionClosed:
                pass
            finally:
                self._clients.pop(ws, None)
                self.get_logger().info('Client deconnecte: ' + str(addr))

        async with websockets.serve(handler, '0.0.0.0', WS_PORT):
            await asyncio.Future()

    async def _handle_audio(self, ws, data: bytes):
        state = self._clients.get(ws)
        if state is None:
            return

        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        energy = float(np.sqrt(np.mean(samples ** 2)) * 32768)

        state["energy_log"] += 1
        if state["energy_log"] % 10 == 0:
            speech = energy > ENERGY_THRESHOLD
            self.get_logger().info('VAD energy=' + str(round(energy,1)) + ' threshold=' + str(ENERGY_THRESHOLD) + ' speech=' + str(speech) + ' chunks=' + str(len(state["chunks"])))

        is_speech = energy > ENERGY_THRESHOLD

        if is_speech:
            state["chunks"].append(samples)
            state["silence_count"] = 0
        else:
            if state["chunks"]:
                state["silence_count"] += 1

        if state["silence_count"] >= SILENCE_CHUNKS and len(state["chunks"]) >= MIN_CHUNKS:
            audio = np.concatenate(state["chunks"])
            n_chunks = len(state["chunks"])
            state["chunks"] = []
            state["silence_count"] = 0
            self.get_logger().info('Transcription de ' + str(n_chunks) + ' chunks (' + str(n_chunks * 0.5) + 's)...')

            def transcribe():
                try:
                    text = self._transcribe(audio)
                    if text:
                        self.get_logger().info('ASR: "' + text + '"')
                        msg = String()
                        msg.data = text
                        self._pub_asr.publish(msg)
                        asyncio.run_coroutine_threadsafe(
                            ws.send(json.dumps({'type': 'transcript', 'text': text})),
                            self._loop
                        )
                    else:
                        self.get_logger().info('ASR: (vide)')
                except Exception as e:
                    self.get_logger().error('Erreur ASR: ' + str(e))

            threading.Thread(target=transcribe, daemon=True).start()

        if len(state["chunks"]) >= MAX_CHUNKS:
            audio = np.concatenate(state["chunks"])
            state["chunks"] = []
            state["silence_count"] = 0

            def transcribe():
                try:
                    text = self._transcribe(audio)
                    if text:
                        self.get_logger().info('ASR (max): "' + text + '"')
                        msg = String()
                        msg.data = text
                        self._pub_asr.publish(msg)
                except Exception as e:
                    self.get_logger().error('Erreur ASR: ' + str(e))

            threading.Thread(target=transcribe, daemon=True).start()

    def _transcribe(self, audio: np.ndarray) -> str:
        if self._asr._recognizer is None:
            return ""
        try:
            stream = self._asr._recognizer.create_stream()
            stream.accept_waveform(SAMPLE_RATE, audio)
            stream.input_finished()
            while self._asr._recognizer.is_ready(stream):
                self._asr._recognizer.decode_stream(stream)
            return self._asr._recognizer.get_result(stream).strip()
        except Exception as e:
            self.get_logger().error('Erreur transcription: ' + str(e))
            return ""


def main():
    rclpy.init()
    node = WSAudioASRNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
