#!/usr/bin/env python3
# encoding: utf-8
"""
pc_mic_sender.py v2 — Capture le micro du PC avec AGC (amplification auto)
et envoie l'audio au robot via WebSocket.

v2: Normalisation automatique du volume + seuil VAD plus bas

Usage:
    python3 pc_mic_sender.py [--robot 192.168.1.30] [--port 9092] [--device N] [--gain 3.0]
"""

import argparse
import asyncio
import json
import threading
import time

import numpy as np
import sounddevice as sd
import websockets

SAMPLE_RATE = 16000
CHUNK_SIZE = 8000  # 0.5s


class AGC:
    """Automatic Gain Control — amplifie si le niveau est faible."""
    def __init__(self, target_rms=0.05, max_gain=10.0, min_gain=0.5):
        self.target_rms = target_rms
        self.max_gain = max_gain
        self.min_gain = min_gain
        self.current_gain = 1.0
        self.smoothing = 0.95  # lissage

    def process(self, samples: np.ndarray) -> np.ndarray:
        rms = float(np.sqrt(np.mean(samples ** 2)))
        if rms > 0.0001:
            # Calculer le gain necessaire
            desired_gain = self.target_rms / rms
            desired_gain = max(self.min_gain, min(self.max_gain, desired_gain))
            # Lissage pour eviter les sauts
            self.current_gain = self.smoothing * self.current_gain + (1 - self.smoothing) * desired_gain
        else:
            self.current_gain = self.max_gain

        # Appliquer le gain avec limitation
        amplified = samples * self.current_gain
        # Limiter pour eviter la saturation
        amplified = np.clip(amplified, -1.0, 1.0)
        return amplified.astype(np.float32)


async def run(robot_host: str, port: int, device, duration: int, gain: float):
    uri = f'ws://{robot_host}:{port}'
    print(f'Connexion a {uri}...', flush=True)

    async with websockets.connect(uri) as ws:
        print(f'Connecte au robot! Parle maintenant...', flush=True)
        print(f'Duree: {duration}s | AGC: gain auto (x{gain}) | Ctrl+C pour arreter\n', flush=True)

        loop = asyncio.get_event_loop()
        audio_queue = asyncio.Queue(maxsize=200)
        agc = AGC(target_rms=0.05 * gain, max_gain=gain * 3)

        def audio_callback(indata, frames, time_info, status):
            mono = indata.flatten().astype(np.float32)
            # AGC: amplifier si faible
            amplified = agc.process(mono)
            pcm = (amplified * 32767).astype(np.int16).tobytes()
            try:
                loop.call_soon_threadsafe(audio_queue.put_nowait, pcm)
            except Exception:
                pass

        async def sender():
            while True:
                pcm = await audio_queue.get()
                await ws.send(pcm)

        async def receiver():
            try:
                async for message in ws:
                    if isinstance(message, str):
                        data = json.loads(message)
                        if data.get('type') == 'transcript':
                            print(f'  [ROBOT ASR] "{data["text"]}"', flush=True)
            except websockets.exceptions.ConnectionClosed:
                print('\nDeconnecte du robot', flush=True)

        send_task = asyncio.create_task(sender())
        recv_task = asyncio.create_task(receiver())

        def run_audio():
            with sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype='float32',
                blocksize=CHUNK_SIZE, device=device, callback=audio_callback,
            ):
                while not recv_task.done():
                    time.sleep(0.1)

        audio_thread = threading.Thread(target=run_audio, daemon=True)
        audio_thread.start()

        done, pending = await asyncio.wait(
            [send_task, recv_task],
            return_when=asyncio.FIRST_COMPLETED,
            timeout=duration,
        )
        for task in pending:
            task.cancel()

        print('\nFin', flush=True)


def main():
    parser = argparse.ArgumentParser(description='Envoie le micro PC au robot pour ASR (avec AGC)')
    parser.add_argument('--robot', default='192.168.1.30', help='IP du robot')
    parser.add_argument('--port', type=int, default=9092, help='Port WebSocket')
    parser.add_argument('--device', type=int, default=None, help='Index du micro')
    parser.add_argument('--duration', type=int, default=120, help='Duree max en secondes')
    parser.add_argument('--gain', type=float, default=3.0, help='Gain max AGC (defaut: 3.0)')
    args = parser.parse_args()

    devices = sd.query_devices()
    print('Microphones disponibles:')
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            marker = ' <-- utilise' if i == args.device else ''
            print(f'  [{i}] {d["name"]}{marker}')
    print()

    try:
        asyncio.run(run(args.robot, args.port, args.device, args.duration, args.gain))
    except KeyboardInterrupt:
        print('\nArret')
    except Exception as e:
        print(f'\nERREUR: {e}')
        print('Verifie que le robot a lance: python3 ws_audio_asr_node.py')


if __name__ == '__main__':
    main()
