#!/usr/bin/env python3
# simple_asr_node.py — Nœud ASR autonome pour remplacer vocal_detect
# Capture micro USB a 48kHz, resample a 16kHz, ASR sherpa-onnx FR
# Publie sur /vocal_detect/asr_result (String) et /vocal_detect/wakeup (Bool)
#
# Usage: python3 simple_asr_node.py
# Env:  SPEECH_LANG=fr  SHERPA_DIR=~/third_party/sherpa-onnx

import os
import sys
import time
import queue
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool, Int32

import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly

# Charger le patch speech et le recognizer
from speech import speech  # noqa: F401 — applique auto_patch
from speech.speech_offline_patch import OfflineRealTimeASR, _find_sherpa_models, DEFAULT_SHERPA_DIR

# Paramètres audio
RECORD_RATE = 48000    # rate native du micro USB
TARGET_RATE = 16000    # rate attendu par sherpa-onnx
DEVICE_INDEX = 0       # USB PnP Audio Device
CHUNK_DURATION = 0.5   # secondes par chunk
ENERGY_THRESHOLD = 100  # seuil VAD (abaisse, le mic USB a des niveaux bas)
SILENCE_CHUNKS = 4      # ~2s de silence = fin de phrase
MAX_CHUNKS = 40         # ~20s max par phrase


class SimpleASRNode(Node):
    def __init__(self):
        super().__init__('simple_asr')

        lang = os.environ.get('SPEECH_LANG', 'fr')
        sherpa_dir = os.environ.get('SHERPA_DIR', '~/third_party/sherpa-onnx')
        timeout = int(os.environ.get('ASR_TIMEOUT', '30'))

        # Forcer le device 0 (USB mic) comme default input
        sd.default.device = (DEVICE_INDEX, None)
        self.get_logger().info(f'Audio device: input={DEVICE_INDEX} ({sd.query_devices(DEVICE_INDEX)["name"]})')

        self.get_logger().info(f'Initialisation ASR offline (lang={lang})...')

        # Creer le recognizer via OfflineRealTimeASR (pour la logique de chargement modele)
        self._asr_helper = OfflineRealTimeASR(language=lang, sherpa_dir=sherpa_dir)
        self._recognizer = self._asr_helper._recognizer

        if self._recognizer is None:
            self.get_logger().error('ERREUR: Recognizer sherpa-onnx non initialise!')
        else:
            self.get_logger().info('Recognizer sherpa-onnx pret')

        # Publishers — memes topics que l'ancien vocal_detect
        self.asr_pub = self.create_publisher(String, '/vocal_detect/asr_result', 10)
        self.wakeup_pub = self.create_publisher(Bool, '/vocal_detect/wakeup', 10)
        self.angle_pub = self.create_publisher(Int32, '/vocal_detect/angle', 10)

        self.timeout = timeout
        self.running = True
        self._audio_queue = queue.Queue()
        self._stop_flag = False

        # Service pour activer/desactiver l'ecoute (compatibilite)
        from std_srvs.srv import SetBool
        self.enable_wakeup = True
        self.create_service(SetBool, '~/enable_wakeup', self.enable_wakeup_srv)

        # Thread d'ecoute ASR
        self.asr_thread = threading.Thread(target=self._asr_loop, daemon=True)
        self.asr_thread.start()

        self.get_logger().info('SimpleASRNode pret — ecoute en continu (48kHz -> 16kHz)')

    def enable_wakeup_srv(self, request, response):
        self.enable_wakeup = request.data
        self.get_logger().info(f'enable_wakeup = {request.data}')
        response.success = True
        return response

    def _resample(self, audio_48k):
        """Downmix stereo->mono + resample 48kHz -> 16kHz.
        audio_48k: int16 array shape (N, 2) stereo ou (N,) mono."""
        # Downmix stereo -> mono si necessaire
        if audio_48k.ndim == 2 and audio_48k.shape[1] == 2:
            mono = audio_48k.mean(axis=1)
        else:
            mono = audio_48k.flatten()
        # Resample 48kHz -> 16kHz (ratio 1/3)
        resampled = resample_poly(mono.astype(np.float32), TARGET_RATE, RECORD_RATE)
        return resampled.astype(np.int16)

    def _transcribe(self, chunks_16k):
        """Transcrit une liste de chunks 16kHz int16. Retourne le texte."""
        if not self._recognizer or not chunks_16k:
            return ""
        try:
            s = np.concatenate(chunks_16k).astype(np.float32) / 32768.0
            if len(s) < int(TARGET_RATE * 0.3):
                return ""
            stream = self._recognizer.create_stream()
            stream.accept_waveform(TARGET_RATE, s)
            stream.input_finished()
            # sherpa-onnx 1.12.x streaming: decoder en boucle tant que is_ready
            while self._recognizer.is_ready(stream):
                self._recognizer.decode_stream(stream)
            # get_result(stream) retourne un str directement
            text = self._recognizer.get_result(stream).strip()
            if text:
                self.get_logger().info(f'ASR: "{text}"')
            return text
        except Exception as e:
            self.get_logger().error(f'Erreur transcription: {e}')
            return ""

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback sounddevice: met les chunks 48kHz dans la queue."""
        if self._stop_flag:
            raise sd.CallbackStop()
        self._audio_queue.put(indata.copy())

    def _asr_loop(self):
        """Boucle principale: capture 48kHz -> resample 16kHz -> VAD -> ASR -> publie."""
        cs = int(RECORD_RATE * CHUNK_DURATION)  # chunk size at 48kHz

        while self.running and rclpy.ok():
            try:
                if not self.enable_wakeup:
                    time.sleep(0.1)
                    continue

                self.get_logger().info('Ecoute en cours... (parle maintenant)')
                self.wakeup_pub.publish(Bool(data=True))

                audio_chunks_16k = []   # chunks resamples a 16kHz
                silence_count = 0
                t0 = time.time()

                with sd.InputStream(
                    samplerate=RECORD_RATE,
                    channels=2,  # stereo — le mic USB ne supporte pas mono via ALSA
                    dtype='int16',
                    blocksize=cs,
                    device=DEVICE_INDEX,
                    callback=self._audio_callback,
                ):
                    while not self._stop_flag and self.running:
                        # Timeout global
                        if time.time() - t0 > self.timeout:
                            break

                        try:
                            chunk_48k = self._audio_queue.get(timeout=0.1)
                        except queue.Empty:
                            continue

                        # Resample 48kHz -> 16kHz
                        chunk_16k = self._resample(chunk_48k)

                        # VAD: energie
                        energy = float(np.abs(chunk_16k.flatten()).mean())

                        # Debug: log energy every 10 chunks (~5s)
                        if not hasattr(self, '_dbg_counter'):
                            self._dbg_counter = 0
                        self._dbg_counter += 1
                        if self._dbg_counter % 10 == 0:
                            self.get_logger().info(f'  [VAD] energy={energy:.1f} threshold={ENERGY_THRESHOLD} chunks={len(audio_chunks_16k)}')

                        if energy > ENERGY_THRESHOLD:
                            audio_chunks_16k.append(chunk_16k.flatten())
                            silence_count = 0
                        elif audio_chunks_16k:
                            silence_count += 1
                            audio_chunks_16k.append(chunk_16k.flatten())
                            if silence_count >= SILENCE_CHUNKS:
                                # Fin de phrase detectee
                                break

                        # Trop long -> force la transcription
                        if len(audio_chunks_16k) >= MAX_CHUNKS:
                            break

                # Transcrire si on a de l'audio
                if audio_chunks_16k and len(audio_chunks_16k) > 2:
                    total_samples = sum(len(c) for c in audio_chunks_16k)
                    duration_s = total_samples / TARGET_RATE
                    self.get_logger().info(f'  [VAD] audio capture: {len(audio_chunks_16k)} chunks, {duration_s:.1f}s')
                    text = self._transcribe(audio_chunks_16k)
                    if text and text.strip():
                        msg = String()
                        msg.data = text.strip()
                        self.asr_pub.publish(msg)
                        self.get_logger().info(f'>>> PUBLIE: "{text}"')
                    else:
                        self.get_logger().info('(parole detectee mais pas de transcription)')
                else:
                    self.get_logger().info('(pas de parole detectee)')

                # Vider la queue
                while not self._audio_queue.empty():
                    try:
                        self._audio_queue.get_nowait()
                    except queue.Empty:
                        break

            except Exception as e:
                self.get_logger().error(f'Erreur boucle ASR: {e}')
                import traceback
                traceback.print_exc()
                time.sleep(1)

    def destroy_node(self):
        self.running = False
        self._stop_flag = True
        super().destroy_node()


def main():
    rclpy.init()
    node = SimpleASRNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
