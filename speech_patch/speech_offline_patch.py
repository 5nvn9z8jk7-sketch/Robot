"""
speech_offline_patch.py - Wrapper pour emuler les classes offline manquantes
de la bibliotheque speech v3.0 sur le ROSOrin Pro (Jetson Orin NX, Ubuntu 22.04).

Contexte : le firmware de juin 2026 (|V1.0.0|App_ROS2_1.0|2026-06-01|) exige la
bibliotheque speech >= 3.0 et ses classes OfflineRealTimeASR, OfflineRealTimeTTS
et OllamaAPI, mais le robot a la v2.0 installee (sans ces classes). En attendant
la reponse du support Hiwonder (mail envoye le 15/10/2026), ce wrapper les emule :

  - OfflineRealTimeASR  : ASR offline via sherpa-onnx (zipformer, deja sur le robot)
  - OfflineRealTimeTTS  : TTS offline via sherpa-onnx (vits, deja sur le robot)
  - OllamaAPI           : client LLM local via Ollama en HTTP (serveur sur le PC)

Deploiement sur le robot (une seule commande fait tout) :

    python3 speech_offline_patch.py --install

Autres commandes :

    python3 speech_offline_patch.py --uninstall     restaure speech.py
    python3 speech_offline_patch.py --selftest      diagnostic rapide

Variables d environnement (optionnelles) :

    OLLAMA_URL    URL du serveur Ollama (defaut http://192.168.1.20:11434)
    OLLAMA_MODEL  modele par defaut (defaut qwen3.5:9b)
    SHERPA_DIR    dossier des modeles sherpa-onnx (defaut ~/third_party/sherpa-onnx)
"""

import os
import sys
import json
import time
import wave
import queue
import threading
import importlib
import importlib.util
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_SHERPA_DIR = os.path.expanduser(
    os.environ.get("SHERPA_DIR", "~/third_party/sherpa-onnx"))
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://192.168.1.20:11434")
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")

# Nombre max de tokens de sortie envoyes a Ollama. >= 2048 est OBLIGATOIRE avec
# les modeles "thinking" (qwen3.x) : en dessous, le budget part en reflexion
# interne et la reponse (content) revient vide.
DEFAULT_MAX_TOKENS = 4096


def _find_sherpa_models(sherpa_dir=None):
    """Cherche les modeles ASR (zipformer/paraformer) et TTS (vits) sherpa-onnx."""
    base = Path(os.path.expanduser(sherpa_dir or DEFAULT_SHERPA_DIR))
    result = {
        "asr_model": None, "asr_tokens": None,
        "tts_model": None, "tts_tokens": None, "tts_voices": None,
        "tts_lexicon": None, "tts_dict_dir": None,
        "base_dir": str(base),
    }
    if not base.exists():
        return result

    for item in base.rglob("*.onnx"):
        name = item.name.lower()
        if "vits" in name or "tts" in name:
            if result["tts_model"] is None:
                result["tts_model"] = str(item)
        elif any(k in name for k in ("zipformer", "transducer", "paraformer", "asr")):
            if result["asr_model"] is None:
                result["asr_model"] = str(item)

    for item in base.rglob("tokens.txt"):
        if result["tts_model"] and item.parent == Path(result["tts_model"]).parent:
            if result["tts_tokens"] is None:
                result["tts_tokens"] = str(item)
        elif result["asr_model"] and item.parent == Path(result["asr_model"]).parent:
            if result["asr_tokens"] is None:
                result["asr_tokens"] = str(item)
        elif result["asr_tokens"] is None:
            result["asr_tokens"] = str(item)

    for item in base.rglob("*"):
        n = item.name.lower()
        if item.is_file() and ("voices" in n or n.endswith(".bin")):
            if result["tts_voices"] is None:
                result["tts_voices"] = str(item)
        elif item.is_file() and "lexicon" in n:
            if result["tts_lexicon"] is None:
                result["tts_lexicon"] = str(item)
        elif item.is_dir() and "espeak" in n:
            if result["tts_dict_dir"] is None:
                result["tts_dict_dir"] = str(item)

    return result


# ============================================================
# OfflineRealTimeASR
# ============================================================

class OfflineRealTimeASR:
    """ASR offline temps reel : sherpa-onnx + sounddevice, VAD par energie.

    API : start(), stop(), listen(timeout), get_result(), result_text,
    is_listening, set_callback(cb), transcribe_file(path)
    """

    def __init__(self, model_dir=None, sherpa_dir=None, language="en",
                 sample_rate=16000, **kwargs):
        self.sample_rate = sample_rate
        self.language = language
        self._listening = False
        self._stop_flag = False
        self._audio_queue = queue.Queue()
        self._result_text = ""
        self._callback = None
        self._recognizer = None
        self._lock = threading.Lock()

        self.models = _find_sherpa_models(sherpa_dir)
        asr_model = model_dir or self.models.get("asr_model")
        asr_tokens = self.models.get("asr_tokens")
        if asr_model and asr_tokens:
            self._init_recognizer(asr_model, asr_tokens)
        else:
            print("[OfflineRealTimeASR] Modeles ASR non trouves dans %s"
                  % (sherpa_dir or DEFAULT_SHERPA_DIR))

    def _init_recognizer(self, model_path, tokens_path):
        try:
            import sherpa_onnx
        except ImportError:
            print("[OfflineRealTimeASR] sherpa_onnx non installe")
            return
        try:
            mn = os.path.basename(model_path).lower()
            if "paraformer" in mn:
                self._recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
                    model=model_path, tokens=tokens_path)
            else:
                md = os.path.dirname(model_path)
                enc = dec = joi = None
                for key, names in (("encoder", ("encoder.onnx", "encoder.int8.onnx")),
                                   ("decoder", ("decoder.onnx", "decoder.int8.onnx")),
                                   ("joiner", ("joiner.onnx", "joiner.int8.onnx"))):
                    for n in names:
                        p = os.path.join(md, n)
                        if os.path.exists(p):
                            if key == "encoder":
                                enc = p
                            elif key == "decoder":
                                dec = p
                            else:
                                joi = p
                            break
                if enc and dec and joi:
                    # sherpa-onnx : 3 fichiers separes
                    self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                        encoder=enc, decoder=dec, joiner=joi, tokens=tokens_path)
                else:
                    # sherpa-onnx recent : un seul fichier modele (zipformer)
                    try:
                        self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                            model=model_path, tokens=tokens_path)
                    except TypeError:
                        self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                            encoder=model_path, decoder=model_path,
                            joiner=model_path, tokens=tokens_path)
            print("[OfflineRealTimeASR] Recognizer initialise: %s" % model_path)
        except Exception as e:
            print("[OfflineRealTimeASR] Erreur init: %s" % e)

    @property
    def is_listening(self):
        return self._listening

    @property
    def result_text(self):
        with self._lock:
            return self._result_text

    def get_result(self):
        """Retourne le dernier texte reconnu et le consomme."""
        with self._lock:
            text = self._result_text
            self._result_text = ""
            return text

    def set_callback(self, cb):
        self._callback = cb

    def start(self):
        if self._listening:
            return
        self._listening = True
        self._stop_flag = False
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def stop(self):
        self._stop_flag = True
        self._listening = False
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    def listen(self, timeout=None):
        """Bloque jusqu a une phrase transcrite. Au timeout retourne ""
        mais CONTINUE d ecouter (ne stoppe pas le micro)."""
        self.start()
        t0 = time.time()
        while True:
            with self._lock:
                if self._result_text:
                    text = self._result_text
                    self._result_text = ""
                    return text
            if not self._listening:
                return ""
            if timeout and (time.time() - t0) > timeout:
                return ""
            time.sleep(0.05)

    def transcribe_file(self, audio_path):
        """Transcrit un fichier WAV (16 kHz mono) hors ligne."""
        if not self._recognizer:
            return ""
        try:
            import numpy as np
            stream = self._recognizer.create_stream()
            with wave.open(audio_path, "rb") as wf:
                s = np.frombuffer(wf.readframes(wf.getnframes()),
                                  dtype=np.int16).astype(np.float32) / 32768.0
                stream.accept_waveform(self.sample_rate, s)
            self._recognizer.decode_stream(stream)
            return stream.result.text.strip()
        except Exception as e:
            print("[OfflineRealTimeASR] Erreur transcription: %s" % e)
            return ""

    def _listen_loop(self):
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError:
            print("[OfflineRealTimeASR] sounddevice/numpy non installes")
            self._listening = False
            return

        cs = int(self.sample_rate * 0.5)   # blocs de 0,5 s
        st = 500                            # seuil d energie
        ms = 4                              # ~2 s de silence = fin de phrase
        max_chunks = 40                     # ~20 s max par phrase
        ab = []
        sc = 0

        def cb(indata, frames, ti, status):
            if self._stop_flag:
                raise sd.CallbackStop()
            self._audio_queue.put(indata.copy())

        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=1,
                                dtype="int16", blocksize=cs, callback=cb):
                while not self._stop_flag:
                    try:
                        chunk = self._audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    energy = float(np.abs(chunk.flatten()).mean())
                    if energy > st:
                        ab.append(chunk.flatten())
                        sc = 0
                    elif ab:
                        sc += 1
                        ab.append(chunk.flatten())
                        if sc >= ms:
                            self._transcribe_buffer(ab)
                            ab = []
                            sc = 0
                    if len(ab) >= max_chunks:
                        self._transcribe_buffer(ab)
                        ab = []
                        sc = 0
                if ab and len(ab) > 2:
                    self._transcribe_buffer(ab)
        except Exception as e:
            print("[OfflineRealTimeASR] Erreur boucle: %s" % e)
        finally:
            self._listening = False

    def _transcribe_buffer(self, chunks):
        if not self._recognizer or not chunks:
            return
        try:
            import numpy as np
            s = np.concatenate(chunks).astype(np.float32) / 32768.0
            if len(s) < int(self.sample_rate * 0.3):
                return
            stream = self._recognizer.create_stream()
            stream.accept_waveform(self.sample_rate, s)
            self._recognizer.decode_stream(stream)
            text = stream.result.text.strip()
            if text:
                with self._lock:
                    self._result_text = text
                if self._callback:
                    try:
                        self._callback(text)
                    except Exception:
                        pass
                print("[OfflineRealTimeASR] Reconnu: %s" % text)
        except Exception as e:
            print("[OfflineRealTimeASR] Erreur: %s" % e)


# ============================================================
# OfflineRealTimeTTS
# ============================================================

class OfflineRealTimeTTS:
    """TTS offline : sherpa-onnx VITS.

    API : say(text, blocking), save_to_file(text, path), play_file(path),
    set_voice(id), set_speed(s), stop(), is_playing
    """

    def __init__(self, model_dir=None, sherpa_dir=None, voice=0, speed=1.0,
                 speaker_id=None, sample_rate=None, **kwargs):
        self.speed = float(speed) if speed else 1.0
        if speaker_id is not None:
            self.speaker_id = int(speaker_id)
        else:
            try:
                self.speaker_id = int(voice)
            except (TypeError, ValueError):
                self.speaker_id = 0
        self.sample_rate = sample_rate  # None = sample_rate du modele
        self._tts = None
        self._playing = False
        self._lock = threading.Lock()

        self.models = _find_sherpa_models(sherpa_dir)
        tm = model_dir or self.models.get("tts_model")
        if tm:
            self._init_tts(tm)
        else:
            print("[OfflineRealTimeTTS] Modele VITS non trouve dans %s"
                  % (sherpa_dir or DEFAULT_SHERPA_DIR))

    def _init_tts(self, model_path):
        try:
            import sherpa_onnx
        except ImportError:
            print("[OfflineRealTimeTTS] sherpa_onnx non installe")
            return
        try:
            md = os.path.dirname(model_path)
            tokens = os.path.join(md, "tokens.txt")
            if not os.path.exists(tokens):
                tokens = self.models.get("tts_tokens") or self.models.get("asr_tokens") or ""
            lexicon = os.path.join(md, "lexicon.txt")
            if not os.path.exists(lexicon):
                lexicon = self.models.get("tts_lexicon") or ""
            data_dir = os.path.join(md, "espeak-ng-data")
            if not os.path.isdir(data_dir):
                data_dir = self.models.get("tts_dict_dir") or ""
            voices = self.models.get("tts_voices") or ""

            self._tts = None
            # API sherpa-onnx >= 1.10 (config explicite)
            try:
                try:
                    vits_config = sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=model_path, lexicon=lexicon,
                        data_dir=data_dir, tokens=tokens)
                except TypeError:
                    vits_config = sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=model_path, lexicon=lexicon,
                        dict_dir=data_dir, tokens=tokens)
                model_config = sherpa_onnx.OfflineTtsModelConfig(
                    vits=vits_config, voices=voices)
                tts_config = sherpa_onnx.OfflineTtsConfig(model=model_config)
                self._tts = sherpa_onnx.OfflineTts(tts_config)
            except (AttributeError, TypeError):
                # Ancienne API (kwargs directs)
                candidates = [
                    {"model": model_path, "tokens": tokens, "voices": voices,
                     "lexicon": lexicon, "dict_dir": data_dir, "num_threads": 2},
                    {"model": model_path, "voices": voices,
                     "lexicon": lexicon, "dict_dir": data_dir, "num_threads": 2},
                    {"model": model_path, "voices": voices, "num_threads": 2},
                    {"model": model_path},
                ]
                for kw in candidates:
                    kw = {k: v for k, v in kw.items() if v}
                    try:
                        self._tts = sherpa_onnx.OfflineTts(**kw)
                        break
                    except TypeError:
                        continue
            if self._tts is not None:
                print("[OfflineRealTimeTTS] TTS initialise: %s" % model_path)
            else:
                print("[OfflineRealTimeTTS] Impossible d initialiser le TTS")
        except Exception as e:
            print("[OfflineRealTimeTTS] Erreur init: %s" % e)

    @property
    def is_playing(self):
        with self._lock:
            return self._playing

    def set_voice(self, sid):
        self.speaker_id = int(sid)

    def set_speed(self, s):
        self.speed = float(s)

    def say(self, text, blocking=True):
        """Synthetise puis joue le texte. blocking=True attend la fin."""
        if not text or not text.strip():
            return
        if not self._tts:
            print("[OfflineRealTimeTTS] TTS non initialise, texte affiche: %s" % text[:80])
            return
        if blocking:
            self._synthesize_and_play(text)
        else:
            threading.Thread(target=self._synthesize_and_play,
                             args=(text,), daemon=True).start()

    def save_to_file(self, text, path):
        """Synthetise le texte et ecrit un fichier WAV 16 bits mono."""
        if not text or not text.strip() or not self._tts:
            return False
        try:
            import numpy as np
            audio = self._tts.generate(text, sid=self.speaker_id, speed=self.speed)
            s = (np.array(audio.samples, dtype=np.float32) * 32767).astype(np.int16)
            parent = os.path.dirname(os.path.abspath(path))
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(int(getattr(audio, "sample_rate", 22050)))
                wf.writeframes(s.tobytes())
            return True
        except Exception as e:
            print("[OfflineRealTimeTTS] Erreur sauvegarde: %s" % e)
            return False

    def play_file(self, path):
        """Joue un fichier WAV (stdlib uniquement)."""
        try:
            import numpy as np
            with wave.open(path, "rb") as wf:
                fs = wf.getframerate()
                raw = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            self._play_samples(samples, fs)
        except Exception as e:
            print("[OfflineRealTimeTTS] Erreur lecture %s: %s" % (path, e))

    def stop(self):
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

    def _synthesize_and_play(self, text):
        with self._lock:
            self._playing = True
        try:
            audio = self._tts.generate(text, sid=self.speaker_id, speed=self.speed)
            self._play_samples(audio.samples, int(audio.sample_rate))
        except Exception as e:
            print("[OfflineRealTimeTTS] Erreur synthese: %s" % e)
            print("[OfflineRealTimeTTS] Texte: %s" % text[:80])
        finally:
            with self._lock:
                self._playing = False

    def _play_samples(self, samples, sample_rate):
        # 1) sounddevice si disponible
        try:
            import sounddevice as sd
            sd.play(samples, sample_rate)
            sd.wait()
            return
        except ImportError:
            pass
        except Exception as e:
            print("[OfflineRealTimeTTS] sounddevice inutilisable (%s), fallback aplay" % e)
        # 2) fallback : WAV temporaire + aplay
        import subprocess
        import tempfile
        import numpy as np
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            s = (np.array(samples, dtype=np.float32) * 32767).astype(np.int16)
            with wave.open(tmp_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(int(sample_rate))
                wf.writeframes(s.tobytes())
            subprocess.run(["aplay", "-q", tmp_path], check=False)
            os.remove(tmp_path)
        except Exception as e:
            print("[OfflineRealTimeTTS] Erreur lecture audio: %s" % e)


# ============================================================
# OllamaAPI
# ============================================================

class OllamaAPI:
    """Client LLM Ollama en HTTP (stdlib urllib, aucune dependance).

    API : chat(messages, system, temperature, max_tokens), generate(prompt),
    stream_chat(messages, callback), list_models(), set_model(m),
    set_system_prompt(t), clear_history(), last_response
    """

    def __init__(self, url=None, model=None, api_key=None, **kwargs):
        url = url or kwargs.get("host") or kwargs.get("base_url")
        self.url = (url or DEFAULT_OLLAMA_URL).rstrip("/")
        self.model = model or kwargs.get("model_name") or DEFAULT_OLLAMA_MODEL
        self.system_prompt = kwargs.get("system_prompt", "") or ""
        self.timeout = kwargs.get("timeout", 180)
        self._last_response = ""
        self._history = []
        self._check_connection()

    def _check_connection(self):
        try:
            models = self.list_models()
            if models:
                print("[OllamaAPI] Connecte a %s - modeles: %s"
                      % (self.url, ", ".join(models[:8])))
            else:
                print("[OllamaAPI] %s repond mais aucun modele telecharge" % self.url)
        except Exception as e:
            print("[OllamaAPI] Serveur inaccessible a %s: %s" % (self.url, e))

    @property
    def last_response(self):
        return self._last_response

    def set_model(self, m):
        self.model = m

    def set_system_prompt(self, t):
        self.system_prompt = t

    def clear_history(self):
        self._history = []
        self._last_response = ""

    def list_models(self):
        try:
            d = self._request("GET", "/api/tags", timeout=5)
            return [m.get("name", "") for m in d.get("models", [])]
        except Exception as e:
            print("[OllamaAPI] Erreur list_models: %s" % e)
            return []

    def chat(self, messages=None, system=None, temperature=0.1,
             max_tokens=DEFAULT_MAX_TOKENS, model=None):
        """Conversation complete. Retourne le texte de la reponse."""
        sp = system if system is not None else self.system_prompt
        fm = []
        if sp:
            fm.append({"role": "system", "content": sp})
        if messages:
            fm.extend(messages)
        elif self._history:
            fm.extend(self._history)
        payload = {
            "model": model or self.model,
            "messages": fm,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            d = self._request("POST", "/api/chat", payload)
            c = d.get("message", {}).get("content", "") or ""
            self._last_response = c
            if messages:
                self._history = fm + [{"role": "assistant", "content": c}]
                if len(self._history) > 40:
                    self._history = self._history[-40:]
            return c
        except Exception as e:
            print("[OllamaAPI] Erreur chat: %s" % e)
            return ""

    def generate(self, prompt, system=None, temperature=0.1,
                 max_tokens=DEFAULT_MAX_TOKENS, model=None):
        """Genere une reponse a partir d un prompt simple."""
        return self.chat([{"role": "user", "content": prompt}],
                         system=system, temperature=temperature,
                         max_tokens=max_tokens, model=model)

    def stream_chat(self, messages=None, callback=None, system=None,
                    temperature=0.1, max_tokens=DEFAULT_MAX_TOKENS, model=None):
        """Chat en streaming : callback(delta) appele pour chaque morceau."""
        import urllib.request
        sp = system if system is not None else self.system_prompt
        fm = []
        if sp:
            fm.append({"role": "system", "content": sp})
        fm.extend(messages if messages else self._history)
        payload = {
            "model": model or self.model,
            "messages": fm,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        ft = ""
        try:
            req = urllib.request.Request(
                self.url + "/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        ch = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    delta = ch.get("message", {}).get("content", "")
                    if delta:
                        ft += delta
                        if callback:
                            callback(delta)
                    if ch.get("done", False):
                        break
            self._last_response = ft
        except Exception as e:
            print("[OllamaAPI] Erreur stream: %s" % e)
        return ft

    def _request(self, method, path, payload=None, timeout=None):
        import urllib.request
        data = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.url + path, data=data,
                                     headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
            body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


# ============================================================
# INJECTION DANS speech.speech
# ============================================================

_PATCHED_CLASSES = (OfflineRealTimeASR, OfflineRealTimeTTS, OllamaAPI)


def _inject_into(module):
    injected = []
    for cls in _PATCHED_CLASSES:
        if not hasattr(module, cls.__name__):
            setattr(module, cls.__name__, cls)
            injected.append(cls.__name__)
    if injected and hasattr(module, "__all__"):
        for n in injected:
            if n not in module.__all__:
                module.__all__.append(n)
    return injected


def patch_speech_module():
    """Injecte les classes offline dans speech.speech (s il est importable)."""
    try:
        import speech.speech as sm
    except ImportError:
        print("[speech_offline_patch] speech.speech non importable pour l instant")
        return False
    injected = _inject_into(sm)
    v = getattr(sm, "__version__", "?")
    if injected:
        print("[speech_offline_patch] Patch applique sur speech.speech v%s: %s"
              % (v, ", ".join(injected)))
    else:
        print("[speech_offline_patch] speech.speech v%s deja patche" % v)
    return True


class _SpeechPatchFinder:
    """Hook d import : injecte les classes des que speech.speech est importe."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "speech.speech":
            return None
        if self in sys.meta_path:
            sys.meta_path.remove(self)
        try:
            spec = importlib.util.find_spec(fullname)
        finally:
            if self not in sys.meta_path:
                sys.meta_path.insert(0, self)
        if spec is None or spec.loader is None:
            return None
        original_loader = spec.loader
        finder = self

        class _PatchLoader:
            def create_module(self, spec):
                if hasattr(original_loader, "create_module"):
                    return original_loader.create_module(spec)
                return None

            def exec_module(self, module):
                original_loader.exec_module(module)
                injected = finder._inject(module)
                for n in injected:
                    print("[speech_offline_patch] %s injecte (hook import)" % n)

        spec.loader = _PatchLoader()
        return spec

    def _inject(self, module):
        return _inject_into(module)


def auto_patch():
    """Injection immediate si speech.speech est deja importe, sinon hook d import."""
    if "speech.speech" in sys.modules:
        return patch_speech_module()
    if not any(isinstance(f, _SpeechPatchFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _SpeechPatchFinder())
        print("[speech_offline_patch] Hook d import installe")
    return True


# ============================================================
# DEPLOIEMENT SUR LE ROBOT
# ============================================================

_INSTALL_MARKER = "# === PATCH OFFLINE HIWONDER ==="


def _rewrite_defaults(file_path, url=None, model=None):
    """Reecrit DEFAULT_OLLAMA_URL / DEFAULT_OLLAMA_MODEL dans la copie installee."""
    import re
    if not url and not model:
        return
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    if url:
        content = re.sub(
            r"^DEFAULT_OLLAMA_URL = .*$",
            'DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_URL", "%s")' % url,
            content, count=1, flags=re.M)
    if model:
        content = re.sub(
            r"^DEFAULT_OLLAMA_MODEL = .*$",
            'DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "%s")' % model,
            content, count=1, flags=re.M)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)


def install(ollama_url=None, ollama_model=None):
    """Copie le patch dans le package speech et branche l injection.

    A executer SUR LE ROBOT : python3 speech_offline_patch.py --install
    """
    import shutil
    import subprocess
    try:
        import speech
    except ImportError:
        print("ERREUR : package speech introuvable.")
        print("Cette commande doit etre lancee sur le robot (user ubuntu).")
        return False

    speech_dir = os.path.dirname(os.path.abspath(speech.__file__))
    speech_py = os.path.join(speech_dir, "speech.py")
    init_py = os.path.join(speech_dir, "__init__.py")
    dest = os.path.join(speech_dir, "speech_offline_patch.py")

    print("Package speech : %s" % speech_dir)

    # 1. Copier le patch dans le package
    shutil.copyfile(os.path.abspath(__file__), dest)
    print("Patch copie : %s" % dest)
    _rewrite_defaults(dest, ollama_url, ollama_model)
    if ollama_url or ollama_model:
        print("Constantes Ollama mises a jour dans la copie installee")

    # 2. Sauvegardes (une seule fois)
    for target in (speech_py, init_py):
        bak = target + ".bak"
        if os.path.exists(target) and not os.path.exists(bak):
            shutil.copyfile(target, bak)
            print("Sauvegarde : %s" % bak)

    NL = chr(10)
    # 3. Branchement dans speech.py (idempotent)
    with open(speech_py, "r", encoding="utf-8") as f:
        current = f.read()
    if _INSTALL_MARKER in current:
        print("speech.py : patch deja present")
    else:
        block = NL.join([
            "",
            _INSTALL_MARKER,
            "try:",
            "    try:",
            "        from .speech_offline_patch import OfflineRealTimeASR, OfflineRealTimeTTS, OllamaAPI",
            "    except ImportError:",
            "        from speech_offline_patch import OfflineRealTimeASR, OfflineRealTimeTTS, OllamaAPI",
            "except Exception:",
            "    import traceback",
            "    traceback.print_exc()",
            "# === FIN PATCH OFFLINE HIWONDER ===",
            "",
        ])
        with open(speech_py, "a", encoding="utf-8") as f:
            f.write(block)
        print("Import du patch ajoute a la fin de speech.py")

    # 4. Exposition au niveau du package (from speech import OllamaAPI)
    with open(init_py, "r", encoding="utf-8") as f:
        current = f.read()
    if _INSTALL_MARKER not in current:
        block = NL.join([
            "",
            _INSTALL_MARKER,
            "try:",
            "    from .speech import OfflineRealTimeASR, OfflineRealTimeTTS, OllamaAPI",
            "except Exception:",
            "    pass",
            "# === FIN PATCH OFFLINE HIWONDER ===",
            "",
        ])
        with open(init_py, "a", encoding="utf-8") as f:
            f.write(block)
        print("Import du patch ajoute a la fin de __init__.py")

    # 5. Verification dans un sous-processus
    code = (
        "import speech.speech as s;"
        "print('OfflineRealTimeASR :', 'OK' if hasattr(s,'OfflineRealTimeASR') else 'MANQUANT');"
        "print('OfflineRealTimeTTS :', 'OK' if hasattr(s,'OfflineRealTimeTTS') else 'MANQUANT');"
        "print('OllamaAPI          :', 'OK' if hasattr(s,'OllamaAPI') else 'MANQUANT')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr)
        return False
    ok = "MANQUANT" not in r.stdout
    print("Installation : %s" % ("OK" if ok else "ECHOUEE"))
    return ok


def uninstall():
    """Restaure speech.py et __init__.py, supprime le patch du package."""
    import shutil
    try:
        import speech
    except ImportError:
        print("ERREUR : package speech introuvable.")
        return False
    speech_dir = os.path.dirname(os.path.abspath(speech.__file__))
    for name in ("speech.py", "__init__.py"):
        target = os.path.join(speech_dir, name)
        bak = target + ".bak"
        if os.path.exists(bak):
            shutil.copyfile(bak, target)
            print("Restaure : %s (depuis %s)" % (target, bak))
        elif os.path.exists(target):
            print("Pas de sauvegarde pour %s, fichier laisse tel quel" % target)
    patch_file = os.path.join(speech_dir, "speech_offline_patch.py")
    if os.path.exists(patch_file):
        os.remove(patch_file)
        print("Patch supprime : %s" % patch_file)
    cache = os.path.join(speech_dir, "__pycache__")
    if os.path.isdir(cache):
        for f in os.listdir(cache):
            if f.startswith("speech"):
                try:
                    os.remove(os.path.join(cache, f))
                except OSError:
                    pass
    print("Desinstallation terminee.")
    return True


def selftest(ollama_url=None):
    """Diagnostic rapide : injection, Ollama, modeles sherpa-onnx."""
    print("=== Selftest speech_offline_patch ===")
    ok = True

    try:
        import speech.speech as sm
        for cls in _PATCHED_CLASSES:
            present = hasattr(sm, cls.__name__)
            print("speech.speech.%-18s : %s" % (cls.__name__, "OK" if present else "MANQUANT"))
            if not present:
                ok = False
    except ImportError:
        print("speech.speech non importable ici (normal sur le PC)")

    url = ollama_url or DEFAULT_OLLAMA_URL
    api = OllamaAPI(url=url)
    try:
        models = api.list_models()
        print("Ollama %-30s : %d modele(s)" % (url, len(models)))
        for m in models[:8]:
            print("    - %s" % m)
        if not models:
            ok = False
    except Exception as e:
        print("Ollama %s INJOIGNABLE : %s" % (url, e))
        print("  -> Sur le PC : OLLAMA_HOST=0.0.0.0 + pare-feu Windows (port 11434)")
        ok = False

    found = _find_sherpa_models()
    print("Sherpa-onnx : %s" % found["base_dir"])
    print("    ASR : %s" % (found["asr_model"] or "NON TROUVE"))
    print("    TTS : %s" % (found["tts_model"] or "NON TROUVE"))
    if not found["asr_model"]:
        ok = False
    if not found["tts_model"]:
        ok = False

    print("Selftest : %s" % ("OK" if ok else "PROBLEMES DETECTES"))
    return ok


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        print("Commandes :")
        print("  --install [--ollama-url URL] [--ollama-model MODELE]")
        print("  --uninstall")
        print("  --selftest [--ollama-url URL]")
        return 0

    def opt(name):
        if name in argv:
            i = argv.index(name)
            if i + 1 < len(argv):
                return argv[i + 1]
        return None

    cmd = argv[0]
    if cmd == "--install":
        return 0 if install(ollama_url=opt("--ollama-url"),
                            ollama_model=opt("--ollama-model")) else 1
    if cmd == "--uninstall":
        return 0 if uninstall() else 1
    if cmd == "--selftest":
        return 0 if selftest(ollama_url=opt("--ollama-url")) else 1
    print("Commande inconnue : %s (voir --help)" % cmd)
    return 1


if __name__ == "__main__":
    sys.exit(main())

