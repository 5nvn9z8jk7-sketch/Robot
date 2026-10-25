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

Support multilingue (francais par defaut) :
  - ASR : detecte automatiquement les modeles zipformer fr/en dans SHERPA_DIR
  - TTS : detecte automatiquement les modeles VITS fr/en dans SHERPA_DIR
  - LLM : prompt systeme en francais pour forcer les reponses en francais

Deploiement sur le robot (une seule commande fait tout) :

    python3 speech_offline_patch.py --install

Autres commandes :

    python3 speech_offline_patch.py --uninstall     restaure speech.py
    python3 speech_offline_patch.py --selftest      diagnostic rapide
    python3 speech_offline_patch.py --download-fr   telecharge modeles francais

Variables d environnement (optionnelles) :

    OLLAMA_URL    URL du serveur Ollama (defaut http://192.168.1.20:11434)
    OLLAMA_MODEL  modele par defaut (defaut qwen3.5:9b)
    SHERPA_DIR    dossier des modeles sherpa-onnx (defaut ~/third_party/sherpa-onnx)
    SPEECH_LANG   langue par defaut : fr ou en (defaut fr)
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

# Langue par defaut pour ASR/TTS/LLM (fr = francais, en = anglais)
DEFAULT_LANGUAGE = os.environ.get("SPEECH_LANG", "fr")

# Si SPEECH_FORCE_FR=1, un prefixe francais est AJOUTE devant le prompt systeme
# fourni par l'appelant (utile car le firmware Hiwonder fixe un prompt chinois
# ou anglais). Le prefixe force la reponse en francais sans ecraser les
# instructions specifiques du firmware (ex: format JSON pour les mouvements).
FORCE_FRENCH_PROMPT = os.environ.get("SPEECH_FORCE_FR", "1") == "1"

# Prefixe ajoute devant le prompt systeme du firmware quand SPEECH_FORCE_FR=1.
# Il force le LLM a repondre en francais ET rappelle le format JSON attendu
# par le noeud llm_control_move pour les commandes de mouvement.
FRENCH_SYSTEM_PREFIX = (
    "IMPORTANT : Tu dois TOUJOURS repondre en francais, de maniere concise et naturelle. "
    "Quand l'utilisateur demande un mouvement du robot (avancer, reculer, tourner, stop), "
    "tu dois repondre UNIQUEMENT avec un objet JSON sur une seule ligne, sans texte autour, "
    "dans ce format exact :\n"
    '{"action": "move(\'forward\', 1, 0)", "response": "OK"}\n'
    "Actions disponibles :\n"
    "- move('forward', vitesse, 0) : avancer (vitesse 0.1 a 1.0)\n"
    "- move('backward', vitesse, 0) : reculer\n"
    "- move('left', 0, vitesse) : tourner a gauche\n"
    "- move('right', 0, vitesse) : tourner a droite\n"
    "- move('stop', 0, 0) : s'arreter\n"
    "Le champ 'response' doit contenir ta reponse en francais (ex: 'J'avance'). "
    "Pour les autres questions (pas de mouvement), reponds normalement en francais, "
    "en une ou deux phrases maximum.\n\n"
)

# Prompt systeme par defaut (utilise quand aucun prompt n'est fourni par l'appelant).
# Inclut les instructions de mouvement en JSON pour le noeud llm_control_move.
DEFAULT_SYSTEM_PROMPT = (
    "Tu es un assistant vocal pour un robot. "
    "Reponds toujours en francais, de maniere concise et naturelle. "
    "Quand l'utilisateur demande un mouvement (avancer, reculer, tourner, stop), "
    "reponds UNIQUEMENT avec un objet JSON sur une seule ligne, sans texte autour, "
    "dans ce format exact :\n"
    '{"action": "move(\'forward\', 1, 0)", "response": "OK"}\n'
    "Actions : move('forward', v, 0), move('backward', v, 0), "
    "move('left', 0, v), move('right', 0, v), move('stop', 0, 0). "
    "Le champ 'response' contient ta reponse en francais. "
    "Pour les autres questions, reponds normalement en francais, "
    "en une ou deux phrases maximum."
)

# URLs des modeles sherpa-onnx francais a telecharger (sur le robot)
# Source : https://github.com/k2-fsa/sherpa-onnx/releases
SHERPA_FR_MODELS = {
    "asr_streaming": {
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
               "sherpa-onnx-streaming-zipformer-fr-2023-02-20.tar.bz2",
        "dir": "sherpa-onnx-streaming-zipformer-fr-2023-02-20",
        "size_mb": 80,
    },
    "tts_vits": {
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
               "vits-piper-fr_FR-siwis-medium.tar.bz2",
        "dir": "vits-piper-fr_FR-siwis-medium",
        "size_mb": 60,
    },
}


def _detect_lang(path_str):
    """Detecte la langue d'un modele a partir de son chemin/nom.
    Retourne 'fr', 'en' ou 'unknown'."""
    s = path_str.lower()
    # Francais : fr, french, fr_fr, fr-fr, siwis (voix fr), piper-fr
    if any(k in s for k in ("-fr", "_fr", "fr_", "french", "fr-fr", "fr_fr",
                            "siwis", "piper-fr", "fr_fr", "frfr")):
        # Exclure les faux positifs (ex: "fromage")
        if "fr" in s:
            return "fr"
    # Anglais : en, english, ljspeech, libritts, en-us, en-us, ljs
    if any(k in s for k in ("-en", "_en", "en_", "english", "en-us", "en_us",
                            "ljspeech", "libritts", "enus", "vits-ljs", "-ljs")):
        return "en"
    return "unknown"


def _find_sherpa_models(sherpa_dir=None):
    """Cherche les modeles ASR (zipformer/paraformer) et TTS (vits) sherpa-onnx.

    Retourne un dict avec les modeles classes par langue :
        asr_models  : {lang: {"model": ..., "tokens": ..., "encoder": ..., ...}}
        tts_models  : {lang: {"model": ..., "tokens": ..., "voices": ..., ...}}
        asr_model   : modele ASR par defaut (compat ancienne API)
        tts_model   : modele TTS par defaut (compat ancienne API)
        ...
    """
    base = Path(os.path.expanduser(sherpa_dir or DEFAULT_SHERPA_DIR))
    result = {
        "asr_models": {},   # {lang: {...}}
        "tts_models": {},   # {lang: {...}}
        "asr_model": None, "asr_tokens": None,
        "asr_encoder": None, "asr_decoder": None, "asr_joiner": None,
        "tts_model": None, "tts_tokens": None, "tts_voices": None,
        "tts_lexicon": None, "tts_dict_dir": None,
        "base_dir": str(base),
    }
    if not base.exists():
        return result

    # Collecte tous les .onnx avec leur chemin complet
    onnx_files = list(base.rglob("*.onnx"))

    # --- TTS : vits ou tts dans le nom OU le chemin ---
    for item in onnx_files:
        full = str(item).lower()
        name = item.name.lower()
        if "vits" in name or "tts" in name or "vits" in full:
            lang = _detect_lang(str(item))
            if lang not in result["tts_models"]:
                result["tts_models"][lang] = {"model": str(item)}
            if result["tts_model"] is None:
                result["tts_model"] = str(item)
            # Preferer le francais pour le modele par defaut
            if lang == "fr":
                result["tts_model"] = str(item)

    # --- ASR : zipformer/paraformer/transducer dans le chemin complet ---
    for item in onnx_files:
        full = str(item).lower()
        name = item.name.lower()
        # Cherche dans le chemin complet (dossier parent peut contenir "zipformer")
        if any(k in full for k in ("zipformer", "paraformer", "transducer", "asr")):
            lang = _detect_lang(str(item))
            if lang not in result["asr_models"]:
                result["asr_models"][lang] = {}
            entry = result["asr_models"][lang]
            # Modele unique (fichier .onnx avec zipformer dans le nom)
            if "zipformer" in name or "paraformer" in name:
                if "model" not in entry:
                    entry["model"] = str(item)
                if result["asr_model"] is None:
                    result["asr_model"] = str(item)
                if lang == "fr":
                    result["asr_model"] = str(item)
            # Modele transducer separe : encoder/decoder/joiner
            elif "encoder" in name and "encoder" not in entry:
                entry["encoder"] = str(item)
                if result["asr_encoder"] is None:
                    result["asr_encoder"] = str(item)
                if lang == "fr":
                    result["asr_encoder"] = str(item)
            elif "decoder" in name and "decoder" not in entry:
                entry["decoder"] = str(item)
                if result["asr_decoder"] is None:
                    result["asr_decoder"] = str(item)
                if lang == "fr":
                    result["asr_decoder"] = str(item)
            elif "joiner" in name and "joiner" not in entry:
                entry["joiner"] = str(item)
                if result["asr_joiner"] is None:
                    result["asr_joiner"] = str(item)
                if lang == "fr":
                    result["asr_joiner"] = str(item)

    # Si on a encoder+decoder+joiner, completer asr_model par langue
    for lang, entry in result["asr_models"].items():
        if entry.get("encoder") and entry.get("decoder") and entry.get("joiner"):
            entry["model"] = entry["encoder"]  # sera gere par _init_recognizer

    # --- Tokens ---
    for item in base.rglob("tokens.txt"):
        parent = item.parent
        parent_str = str(parent).lower()
        lang = _detect_lang(parent_str)
        # TTS tokens : meme dossier que le modele TTS
        if result["tts_model"] and parent == Path(result["tts_model"]).parent:
            if result["tts_tokens"] is None:
                result["tts_tokens"] = str(item)
            # Aussi dans le dict par langue
            for tl, tentry in result["tts_models"].items():
                if tentry.get("model") and parent == Path(tentry["model"]).parent:
                    tentry["tokens"] = str(item)
        # ASR tokens : meme dossier que encoder ou modele ASR unique
        elif result["asr_encoder"] and parent == Path(result["asr_encoder"]).parent:
            if result["asr_tokens"] is None:
                result["asr_tokens"] = str(item)
            for al, aentry in result["asr_models"].items():
                if aentry.get("encoder") and parent == Path(aentry["encoder"]).parent:
                    aentry["tokens"] = str(item)
                elif aentry.get("model") and parent == Path(aentry["model"]).parent:
                    aentry["tokens"] = str(item)
        elif result["asr_model"] and parent == Path(result["asr_model"]).parent:
            if result["asr_tokens"] is None:
                result["asr_tokens"] = str(item)
            for al, aentry in result["asr_models"].items():
                if aentry.get("model") and parent == Path(aentry["model"]).parent:
                    aentry["tokens"] = str(item)
        elif result["asr_tokens"] is None:
            result["asr_tokens"] = str(item)
            # Essaie de l'attribuer par langue
            for al, aentry in result["asr_models"].items():
                if "tokens" not in aentry and al == lang:
                    aentry["tokens"] = str(item)

    # --- TTS voices/lexicon/dict par langue ---
    for item in base.rglob("*"):
        n = item.name.lower()
        item_lang = _detect_lang(str(item))
        if item.is_file() and ("voices" in n or n.endswith(".bin")):
            if result["tts_voices"] is None:
                result["tts_voices"] = str(item)
            for tl, tentry in result["tts_models"].items():
                if "voices" not in tentry and (tl == item_lang or tl == "unknown"):
                    tentry["voices"] = str(item)
        elif item.is_file() and "lexicon" in n:
            if result["tts_lexicon"] is None:
                result["tts_lexicon"] = str(item)
            for tl, tentry in result["tts_models"].items():
                if "lexicon" not in tentry and (tl == item_lang or tl == "unknown"):
                    tentry["lexicon"] = str(item)
        elif item.is_dir() and "espeak" in n:
            if result["tts_dict_dir"] is None:
                result["tts_dict_dir"] = str(item)
            for tl, tentry in result["tts_models"].items():
                if "dict_dir" not in tentry:
                    tentry["dict_dir"] = str(item)

    # Completer les tokens manquants par langue avec les tokens generaux
    for aentry in result["asr_models"].values():
        if "tokens" not in aentry and result["asr_tokens"]:
            aentry["tokens"] = result["asr_tokens"]
    for tentry in result["tts_models"].values():
        if "tokens" not in tentry and result["tts_tokens"]:
            tentry["tokens"] = result["tts_tokens"]

    return result


# ============================================================
# OfflineRealTimeASR
# ============================================================

class OfflineRealTimeASR:
    """ASR offline temps reel : sherpa-onnx + sounddevice, VAD par energie.

    API : start(), stop(), listen(timeout), get_result(), result_text,
    is_listening, set_callback(cb), transcribe_file(path)

    Selection du modele par langue : si language='fr' (defaut), cherche un
    modele zipformer francais dans SHERPA_DIR. Sinon retombe sur l'anglais.
    """

    def __init__(self, model_dir=None, sherpa_dir=None, language=None,
                 sample_rate=16000, **kwargs):
        self.sample_rate = sample_rate
        self.language = language or DEFAULT_LANGUAGE
        self._listening = False
        self._stop_flag = False
        self._audio_queue = queue.Queue()
        self._result_text = ""
        self._callback = None
        self._recognizer = None
        self._lock = threading.Lock()

        self.models = _find_sherpa_models(sherpa_dir)

        # Selection du modele ASR selon la langue demandee
        asr_models = self.models.get("asr_models", {})
        entry = None
        if model_dir:
            # Modele explicite fourni par l'appelant
            asr_model = model_dir
            asr_tokens = self.models.get("asr_tokens")
            self._init_recognizer(asr_model, asr_tokens)
            return
        # Cherche le modele pour la langue demandee, sinon fallback
        for lang in (self.language, "fr", "en", "unknown"):
            if lang in asr_models and asr_models[lang].get("model"):
                entry = asr_models[lang]
                break
        if entry is None:
            # Fallback sur l'ancienne cle
            asr_model = self.models.get("asr_model")
            asr_tokens = self.models.get("asr_tokens")
            if asr_model and asr_tokens:
                self._init_recognizer(asr_model, asr_tokens)
            else:
                print("[OfflineRealTimeASR] Modeles ASR non trouves dans %s"
                      % (sherpa_dir or DEFAULT_SHERPA_DIR))
            return

        asr_model = entry.get("model")
        asr_tokens = entry.get("tokens") or self.models.get("asr_tokens")
        enc = entry.get("encoder")
        dec = entry.get("decoder")
        joi = entry.get("joiner")
        if asr_model and asr_tokens:
            self._init_recognizer(asr_model, asr_tokens,
                                  encoder=enc, decoder=dec, joiner=joi)
        else:
            print("[OfflineRealTimeASR] Modele ASR incomplet pour langue=%s"
                  % self.language)

    def _init_recognizer(self, model_path, tokens_path,
                         encoder=None, decoder=None, joiner=None):
        try:
            import sherpa_onnx
        except ImportError:
            print("[OfflineRealTimeASR] sherpa_onnx non installe")
            return
        try:
            # Detecter si c'est un modele streaming (dossier avec "streaming" dans le nom)
            is_streaming = "streaming" in model_path.lower()
            self._is_streaming = is_streaming
            mn = os.path.basename(model_path).lower()
            if "paraformer" in mn:
                if is_streaming:
                    self._recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
                        model=model_path, tokens=tokens_path)
                else:
                    self._recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
                        model=model_path, tokens=tokens_path)
            else:
                md = os.path.dirname(model_path)
                # Utiliser encoder/decoder/joiner fournis, sinon chercher dans le dossier
                enc = encoder
                dec = decoder
                joi = joiner
                if not (enc and dec and joi):
                    # Cherche encoder/decoder/joiner dans le dossier du modele
                    # Essayer d'abord les noms generiques, puis les noms avec epoch
                    for key, patterns in (("encoder", ("encoder.onnx", "encoder.int8.onnx", "encoder-epoch-*.onnx", "encoder-epoch-*.int8.onnx")),
                                          ("decoder", ("decoder.onnx", "decoder.int8.onnx", "decoder-epoch-*.onnx", "decoder-epoch-*.int8.onnx")),
                                          ("joiner", ("joiner.onnx", "joiner.int8.onnx", "joiner-epoch-*.onnx", "joiner-epoch-*.int8.onnx"))):
                        if key == "encoder" and enc: continue
                        if key == "decoder" and dec: continue
                        if key == "joiner" and joi: continue
                        for pat in patterns:
                            if "*" in pat:
                                import glob
                                matches = sorted(glob.glob(os.path.join(md, pat)))
                                # Preferer la version non-int8
                                for m in matches:
                                    if ".int8." not in m:
                                        if key == "encoder": enc = m
                                        elif key == "decoder": dec = m
                                        else: joi = m
                                        break
                                if (key == "encoder" and enc) or (key == "decoder" and dec) or (key == "joiner" and joi):
                                    continue
                                if matches:
                                    if key == "encoder": enc = matches[0]
                                    elif key == "decoder": dec = matches[0]
                                    else: joi = matches[0]
                            else:
                                p = os.path.join(md, pat)
                                if os.path.exists(p):
                                    if key == "encoder": enc = p
                                    elif key == "decoder": dec = p
                                    else: joi = p
                                    break
                if enc and dec and joi:
                    if is_streaming:
                        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                            encoder=enc, decoder=dec, joiner=joi, tokens=tokens_path)
                    else:
                        self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                            encoder=enc, decoder=dec, joiner=joi, tokens=tokens_path)
                else:
                    # Modele unique (zipformer recent)
                    if is_streaming:
                        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                            model=model_path, tokens=tokens_path)
                    else:
                        try:
                            self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                                model=model_path, tokens=tokens_path)
                        except TypeError:
                            self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                                encoder=model_path, decoder=model_path,
                                joiner=model_path, tokens=tokens_path)
            mode = "streaming (OnlineRecognizer)" if is_streaming else "offline (OfflineRecognizer)"
            print("[OfflineRealTimeASR] Recognizer initialise [%s, lang=%s]: %s"
                  % (mode, self.language, model_path))
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

    def asr(self, timeout=None):
        """Alias de listen() pour compatibilite firmware Hiwonder v3.0.

        Le noeud vocal_detect appelle : self.asr.asr()
        Bloque jusqu'a obtenir une phrase transcrite.
        """
        return self.listen(timeout=timeout)

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

    Selection du modele par langue : si language='fr' (defaut), cherche un
    modele VITS francais (ex: vits-piper-fr_FR-siwis). Sinon retombe sur
    l'anglais (ex: vits-ljs).
    """

    def __init__(self, model_dir=None, sherpa_dir=None, voice=0, speed=1.0,
                 speaker_id=None, sample_rate=None, language=None, **kwargs):
        self.speed = float(speed) if speed else 1.0
        if speaker_id is not None:
            self.speaker_id = int(speaker_id)
        else:
            try:
                self.speaker_id = int(voice)
            except (TypeError, ValueError):
                self.speaker_id = 0
        self.sample_rate = sample_rate  # None = sample_rate du modele
        self.language = language or DEFAULT_LANGUAGE
        self._tts = None
        self._playing = False
        self._lock = threading.Lock()

        self.models = _find_sherpa_models(sherpa_dir)

        # Selection du modele TTS selon la langue demandee
        tts_models = self.models.get("tts_models", {})
        entry = None
        if model_dir:
            tm = model_dir
        else:
            for lang in (self.language, "fr", "en", "unknown"):
                if lang in tts_models and tts_models[lang].get("model"):
                    entry = tts_models[lang]
                    break
            if entry:
                tm = entry.get("model")
            else:
                tm = self.models.get("tts_model")

        if tm:
            # Mettre a jour les tokens/voices/lexicon depuis l'entry par langue
            if entry:
                self._tts_entry = entry
            self._init_tts(tm)
        else:
            print("[OfflineRealTimeTTS] Modele VITS non trouve dans %s (lang=%s)"
                  % (sherpa_dir or DEFAULT_SHERPA_DIR, self.language))

    def _init_tts(self, model_path):
        try:
            import sherpa_onnx
        except ImportError:
            print("[OfflineRealTimeTTS] sherpa_onnx non installe")
            return
        try:
            md = os.path.dirname(model_path)
            # Priorite aux fichiers du dossier du modele, puis ceux de l'entry par langue
            entry = getattr(self, "_tts_entry", {})
            tokens = os.path.join(md, "tokens.txt")
            if not os.path.exists(tokens):
                tokens = entry.get("tokens") or self.models.get("tts_tokens") or self.models.get("asr_tokens") or ""
            lexicon = os.path.join(md, "lexicon.txt")
            if not os.path.exists(lexicon):
                lexicon = entry.get("lexicon") or self.models.get("tts_lexicon") or ""
            data_dir = os.path.join(md, "espeak-ng-data")
            if not os.path.isdir(data_dir):
                data_dir = entry.get("dict_dir") or self.models.get("tts_dict_dir") or ""
            voices = entry.get("voices") or self.models.get("tts_voices") or ""

            self._tts = None
            last_err = "aucune tentative"

            # Essayer la config explicite avec plusieurs combinaisons
            vits_configs = [
                {"model": model_path, "lexicon": lexicon, "data_dir": data_dir, "tokens": tokens},
                {"model": model_path, "lexicon": lexicon, "dict_dir": data_dir, "tokens": tokens},
                {"model": model_path, "tokens": tokens, "lexicon": lexicon},
                {"model": model_path, "tokens": tokens},
                {"model": model_path},
            ]
            model_configs = [
                {"vits": None, "voices": voices},  # vits sera remplace
                {"vits": None, "sid": self.speaker_id},
                {"vits": None},
            ]

            for vc_kw in vits_configs:
                vc_kw = {k: v for k, v in vc_kw.items() if v}
                try:
                    vits_config = sherpa_onnx.OfflineTtsVitsModelConfig(**vc_kw)
                except Exception as e:
                    last_err = "VitsModelConfig %s: %s" % (list(vc_kw.keys()), e)
                    continue
                for mc_kw in model_configs:
                    mc_kw = dict(mc_kw)
                    mc_kw["vits"] = vits_config
                    mc_kw = {k: v for k, v in mc_kw.items() if v is not None}
                    try:
                        model_config = sherpa_onnx.OfflineTtsModelConfig(**mc_kw)
                    except Exception as e:
                        last_err = "ModelConfig %s: %s" % (list(mc_kw.keys()), e)
                        continue
                    try:
                        tts_config = sherpa_onnx.OfflineTtsConfig(model=model_config)
                        self._tts = sherpa_onnx.OfflineTts(tts_config)
                        print("[OfflineRealTimeTTS] TTS initialise (config, lang=%s): %s"
                              % (self.language, model_path))
                        return
                    except Exception as e:
                        last_err = "OfflineTts(config): %s" % e
                        continue

            # Fallback : ancienne API kwargs directs
            if self._tts is None:
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
                        print("[OfflineRealTimeTTS] TTS initialise (kwargs, lang=%s): %s"
                              % (self.language, model_path))
                        return
                    except Exception as e:
                        last_err = "kwargs %s: %s" % (list(kw.keys()), e)
                        continue

            if self._tts is not None:
                print("[OfflineRealTimeTTS] TTS initialise (lang=%s): %s"
                      % (self.language, model_path))
            else:
                print("[OfflineRealTimeTTS] Impossible d initialiser le TTS")
                print("[OfflineRealTimeTTS] Derniere erreur: %s" % last_err)
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

    def tts(self, text, sid=None, blocking=True):
        """Alias de say() pour compatibilite firmware (tts_node appelle .tts())."""
        if sid is not None:
            self.set_voice(sid)
        self.say(text, blocking=blocking)

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

    @staticmethod
    def _clean_text_for_tts(text):
        """Nettoie le texte pour eviter les crashes ONNX du modele VITS.

        Le modele vits-piper-fr_FR-siwis-medium plante sur certaines
        sequences (ponctuation collee ou espacee, texte trop court, etc.).
        Cette fonction normalise le texte pour maximiser les chances de succes.
        """
        import re
        if not text:
            return text
        # Normaliser les espaces
        text = text.strip()
        # Typographie francaise : espace avant ! ? : ;
        text = re.sub(r'\s*([!?:;])\s*', r' \1 ', text)
        # Espaces multiples -> simple
        text = re.sub(r'\s+', ' ', text).strip()
        # Point final si absent (aide le modele)
        if text and text[-1] not in '.!?':
            text += '.'
        return text

    def _synthesize_and_play(self, text):
        """Synthetise via subprocess avec timeout pour eviter les hangs ONNX."""
        import subprocess
        import tempfile
        import os

        with self._lock:
            self._playing = True
        try:
            clean = self._clean_text_for_tts(text)
            if not clean:
                return

            # Script de synthese a executer en subprocess
            synth_script = (
                "import sys;"
                "sys.path.insert(0, '/home/ubuntu/.local/lib/python3.10/site-packages');"
                "from speech.speech_offline_patch import OfflineRealTimeTTS;"
                "import wave, numpy as np;"
                "tts = OfflineRealTimeTTS(language='fr');"
                "audio = tts._tts.generate(sys.argv[1], sid=0, speed=1.0);"
                "s = (np.array(audio.samples, dtype=np.float32) * 32767).astype(np.int16);"
                "wf = wave.open(sys.argv[2], 'wb');"
                "wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(int(audio.sample_rate));"
                "wf.writeframes(s.tobytes()); wf.close()"
            )

            # Creer un fichier WAV temporaire
            fd, wav_path = tempfile.mkstemp(suffix='.wav', dir='/tmp')
            os.close(fd)
            os.unlink(wav_path)  # le subprocess va le creer

            # Tentative 1 : texte nettoye
            try:
                result = subprocess.run(
                    ['python3', '-u', '-c', synth_script, clean, wav_path],
                    capture_output=True, timeout=15,
                )
                if result.returncode == 0 and os.path.exists(wav_path) and os.path.getsize(wav_path) > 44:
                    self.play_file(wav_path)
                    os.unlink(wav_path)
                    return
                else:
                    print("[OfflineRealTimeTTS] Echec subprocess (rc=%d): %s" % (result.returncode, result.stderr.decode('utf-8', errors='replace')[:150]))
            except subprocess.TimeoutExpired:
                print("[OfflineRealTimeTTS] Timeout synthese (texte nettoye), texte: %s" % clean[:60])
            except Exception as e:
                print("[OfflineRealTimeTTS] Erreur subprocess: %s" % str(e)[:100])

            # Tentative 2 : sans ponctuation
            import re
            no_punct = re.sub(r'[!?:;.,]', '', clean).strip()
            if no_punct and no_punct != clean:
                try:
                    result = subprocess.run(
                        ['python3', '-u', '-c', synth_script, no_punct, wav_path],
                        capture_output=True, timeout=15,
                    )
                    if result.returncode == 0 and os.path.exists(wav_path) and os.path.getsize(wav_path) > 44:
                        self.play_file(wav_path)
                        os.unlink(wav_path)
                        return
                except subprocess.TimeoutExpired:
                    print("[OfflineRealTimeTTS] Timeout synthese (sans ponctuation)")
                except Exception as e:
                    print("[OfflineRealTimeTTS] Erreur subprocess 2: %s" % str(e)[:100])

            # Tentative 3 : texte brut original
            if text != clean:
                try:
                    result = subprocess.run(
                        ['python3', '-u', '-c', synth_script, text, wav_path],
                        capture_output=True, timeout=15,
                    )
                    if result.returncode == 0 and os.path.exists(wav_path) and os.path.getsize(wav_path) > 44:
                        self.play_file(wav_path)
                        os.unlink(wav_path)
                        return
                except subprocess.TimeoutExpired:
                    print("[OfflineRealTimeTTS] Timeout synthese (texte brut)")
                except Exception as e:
                    print("[OfflineRealTimeTTS] Erreur subprocess 3: %s" % str(e)[:100])

            # Nettoyage
            try:
                if os.path.exists(wav_path):
                    os.unlink(wav_path)
            except:
                pass

            print("[OfflineRealTimeTTS] Toutes les tentatives ont echoue. Texte: %s" % text[:80])
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
        # Priorite a la variable d'environnement OLLAMA_URL (force l'URL du PC)
        env_url = os.environ.get("OLLAMA_URL", "")
        if env_url:
            url = env_url
        self.url = (url or DEFAULT_OLLAMA_URL).rstrip("/")
        self.model = model or kwargs.get("model_name") or DEFAULT_OLLAMA_MODEL
        # Prompt systeme : si l'appelant ne fournit rien, utiliser le prompt
        # francais par defaut pour forcer les reponses en francais.
        sp = kwargs.get("system_prompt")
        if sp is None or sp == "":
            sp = DEFAULT_SYSTEM_PROMPT
        self.system_prompt = sp
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
        if FORCE_FRENCH_PROMPT:
            base_sp = system if system else self.system_prompt
            sp = FRENCH_SYSTEM_PREFIX + (base_sp or "")
        else:
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

    def llm(self, prompt, system="", temperature=0.1,
            max_tokens=DEFAULT_MAX_TOKENS, model=None, **kwargs):
        """Alias de generate() pour compatibilite firmware Hiwonder v3.0.

        Le noeud agent_process appelle : self.client.llm(prompt, system, model=...)
        """
        return self.generate(prompt, system=system or None,
                             temperature=temperature,
                             max_tokens=max_tokens, model=model)

    def stream_chat(self, messages=None, callback=None, system=None,
                    temperature=0.1, max_tokens=DEFAULT_MAX_TOKENS, model=None):
        """Chat en streaming : callback(delta) appele pour chaque morceau."""
        import urllib.request
        if FORCE_FRENCH_PROMPT:
            base_sp = system if system else self.system_prompt
            sp = FRENCH_SYSTEM_PREFIX + (base_sp or "")
        else:
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
    # 3. Branchement : dans speech.py si existe, sinon auto_patch dans __init__.py
    if os.path.exists(speech_py):
        # Cas classique : speech.py existe
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

        # 4a. Exposition au niveau du package (from speech import OllamaAPI)
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
    else:
        # Cas .so : speech.py n'existe pas, on branche auto_patch dans __init__.py
        print("speech.py absent (module .so detecte), branchement auto_patch dans __init__.py")
        with open(init_py, "r", encoding="utf-8") as f:
            current = f.read()
        if _INSTALL_MARKER in current:
            print("__init__.py : patch deja present")
        else:
            block = NL.join([
                "",
                _INSTALL_MARKER,
                "try:",
                "    from .speech_offline_patch import auto_patch",
                "    auto_patch()",
                "except Exception:",
                "    import traceback",
                "    traceback.print_exc()",
                "# === FIN PATCH OFFLINE HIWONDER ===",
                "",
            ])
            with open(init_py, "a", encoding="utf-8") as f:
                f.write(block)
            print("auto_patch() ajoute a la fin de __init__.py")

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
    print("Langue par defaut : %s" % DEFAULT_LANGUAGE)

    # Afficher les modeles par langue
    asr_models = found.get("asr_models", {})
    tts_models = found.get("tts_models", {})
    for lang in ("fr", "en", "unknown"):
        if lang in asr_models:
            a = asr_models[lang]
            print("    ASR [%s] : %s" % (lang, a.get("model") or "NON TROUVE"))
            if a.get("encoder"):
                print("        encoder : %s" % a["encoder"])
                print("        decoder : %s" % (a.get("decoder") or "NON TROUVE"))
                print("        joiner  : %s" % (a.get("joiner") or "NON TROUVE"))
            print("        tokens  : %s" % (a.get("tokens") or "NON TROUVE"))
        if lang in tts_models:
            t = tts_models[lang]
            print("    TTS [%s] : %s" % (lang, t.get("model") or "NON TROUVE"))

    # Compat ancienne API
    print("    ASR (defaut) : %s" % (found["asr_model"] or "NON TROUVE"))
    print("    TTS (defaut) : %s" % (found["tts_model"] or "NON TROUVE"))

    has_asr = found["asr_model"] or found.get("asr_encoder") or any(
        a.get("model") for a in asr_models.values())
    has_tts = found["tts_model"] or any(
        t.get("model") for t in tts_models.values())
    if not has_asr:
        ok = False
    if not has_tts:
        ok = False

    # Verifier si les modeles francais sont presents
    has_fr_asr = "fr" in asr_models and asr_models["fr"].get("model")
    has_fr_tts = "fr" in tts_models and tts_models["fr"].get("model")
    if DEFAULT_LANGUAGE == "fr":
        if not has_fr_asr:
            print("ATTENTION : pas de modele ASR francais trouve. "
                  "Lancer --download-fr pour les telecharger.")
        if not has_fr_tts:
            print("ATTENTION : pas de modele TTS francais trouve. "
                  "Lancer --download-fr pour les telecharger.")

    print("Selftest : %s" % ("OK" if ok else "PROBLEMES DETECTES"))
    return ok


def download_french_models(sherpa_dir=None, force=False):
    """Telecharge les modeles sherpa-onnx francais (ASR + TTS) sur le robot.

    A executer SUR LE ROBOT : python3 speech_offline_patch.py --download-fr
    Telecharge dans ~/third_party/sherpa-onnx/ :
      - ASR streaming zipformer francais (~80 Mo)
      - TTS VITS piper fr_FR siwis (~60 Mo)
    """
    import subprocess
    import tarfile
    import tempfile

    base = os.path.expanduser(sherpa_dir or DEFAULT_SHERPA_DIR)
    os.makedirs(base, exist_ok=True)
    print("Dossier cible : %s" % base)

    for key, info in SHERPA_FR_MODELS.items():
        target_dir = os.path.join(base, info["dir"])
        marker = os.path.join(target_dir, ".complete")
        if os.path.exists(marker) and not force:
            print("[%s] Deja telecharge (%s)" % (key, info["dir"]))
            continue

        url = info["url"]
        print("[%s] Telechargement : %s (~%d Mo)" % (key, url, info["size_mb"]))
        print("      -> %s" % target_dir)

        fd, tmp_path = tempfile.mkstemp(suffix=".tar.bz2")
        os.close(fd)
        try:
            # Telechargement avec barre de progression simple
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 256)  # 256 Ko
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded * 100 // total
                            print("\r      Progression : %d%%" % pct, end="", flush=True)
                print()

            # Extraction
            print("[%s] Extraction..." % key)
            os.makedirs(base, exist_ok=True)
            with tarfile.open(tmp_path, "r:bz2") as tf:
                tf.extractall(base)
            # Creer le marqueur
            os.makedirs(target_dir, exist_ok=True)
            with open(marker, "w") as f:
                f.write("ok\n")
            print("[%s] OK : %s" % (key, target_dir))
        except Exception as e:
            print("[%s] ERREUR : %s" % (key, e))
            return False
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    print("Telechargement termine. Modeles francais dans %s" % base)
    return True


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        print("Commandes :")
        print("  --install [--ollama-url URL] [--ollama-model MODELE]")
        print("  --uninstall")
        print("  --selftest [--ollama-url URL]")
        print("  --download-fr [--force]   telecharge modeles ASR/TTS francais")
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
    if cmd == "--download-fr":
        return 0 if download_french_models(force="--force" in argv) else 1
    print("Commande inconnue : %s (voir --help)" % cmd)
    return 1


if __name__ == "__main__":
    sys.exit(main())

