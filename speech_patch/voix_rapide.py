# encoding: utf-8
"""voix_rapide.py — phrases FIXES pré-enregistrées, jouées sans délai.

Pourquoi : le module vocal (speech_offline_patch) recharge le modèle de voix
à CHAQUE phrase (~5 s mesurées le 10/11 entre l'arrêt sur obstacle et
« Obstacle »). Ici, chaque phrase fixe est synthétisée une seule fois
(au démarrage, en arrière-plan) dans ~/speech_patch/sons/, puis jouée
directement avec aplay (~0,1 s). Les fichiers restent d'un démarrage à l'autre.

Si le fichier n'est pas (encore) prêt, la phrase passe par le chemin
normal (topic /tts_node/tts_text) : jamais de phrase perdue.
"""
import hashlib
import os
import subprocess
import threading

DOSSIER = '/home/ubuntu/speech_patch/sons'
ENV_AUDIO = dict(os.environ, XDG_RUNTIME_DIR='/run/user/1000')

# Même synthèse que speech_offline_patch, mais toutes les phrases d'un coup
# (le modèle n'est chargé qu'une fois).
_SCRIPT = """
import sys, os, json, wave
import numpy as np
sys.path.insert(0, '/home/ubuntu/.local/lib/python3.10/site-packages')
from speech.speech_offline_patch import OfflineRealTimeTTS
tts = OfflineRealTimeTTS(language='fr')
for texte, chemin in json.loads(sys.argv[1]):
    a = tts._tts.generate(texte, sid=0, speed=1.0)
    s = (np.array(a.samples, dtype=np.float32) * 32767).astype(np.int16)
    w = wave.open(chemin + '.tmp', 'wb')
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(a.sample_rate))
    w.writeframes(s.tobytes()); w.close()
    os.replace(chemin + '.tmp', chemin)
"""


def chemin_son(texte, dossier=DOSSIER):
    h = hashlib.sha1(texte.strip().encode('utf-8')).hexdigest()[:12]
    return os.path.join(dossier, f'{h}.wav')


class VoixRapide:
    def __init__(self, phrases, repli, journal=None, dossier=DOSSIER):
        """phrases : textes fixes à préparer ; repli(texte) : envoi normal au TTS."""
        self.repli = repli
        self.journal = journal or (lambda m: None)
        self.dossier = dossier
        os.makedirs(dossier, exist_ok=True)
        a_faire = [(t, chemin_son(t, dossier)) for t in phrases
                   if not os.path.exists(chemin_son(t, dossier))]
        if a_faire:
            threading.Thread(target=self._preparer, args=(a_faire,), daemon=True).start()

    def _preparer(self, a_faire):
        import json
        try:
            r = subprocess.run(['python3', '-c', _SCRIPT, json.dumps(a_faire)],
                               capture_output=True, timeout=120)
            ok = sum(os.path.exists(c) for _, c in a_faire)
            self.journal(f'voix rapide : {ok}/{len(a_faire)} phrases préparées'
                         + ('' if r.returncode == 0 else f' (erreur : {r.stderr[-200:]!r})'))
        except Exception as e:  # le repli TTS reste disponible
            self.journal(f'voix rapide : préparation impossible ({e})')

    def dire(self, texte):
        c = chemin_son(texte, self.dossier)
        if os.path.exists(c):
            try:
                subprocess.Popen(['aplay', '-q', c], env=ENV_AUDIO,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass
        self.repli(texte)
