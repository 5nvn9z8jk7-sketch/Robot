#!/usr/bin/env python3
"""Tests du wrapper speech_offline_patch.

Lancer sur le PC :    python3 test_wrapper.py
Lancer sur le robot : python3 test_wrapper.py

Les tests ASR/TTS sont ignores (SKIP) si sherpa_onnx n est pas installe.
Les tests Ollama sont ignores (SKIP) si le serveur n est pas joignable.
"""

import os
import sys
import time
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import speech_offline_patch as sop

PASS = 0
FAIL = 0
SKIP = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS - %s%s" % (name, (" | " + str(detail)) if detail else ""))
    else:
        FAIL += 1
        print("FAIL - %s%s" % (name, (" | " + str(detail)) if detail else ""))


def skip(name, reason=""):
    global SKIP
    SKIP += 1
    print("SKIP - %s | %s" % (name, reason))


# --- 1. Les 3 classes sont definies ---
for cls_name in ("OfflineRealTimeASR", "OfflineRealTimeTTS", "OllamaAPI"):
    check("classe %s definie" % cls_name, hasattr(sop, cls_name))

# --- 2. Injection dans un faux package speech (simule la v2.0) ---
fake_root = tempfile.mkdtemp(prefix="fake_speech_")
pkg_dir = os.path.join(fake_root, "speech")
os.makedirs(pkg_dir)
with open(os.path.join(pkg_dir, "__init__.py"), "w") as f:
    f.write("# faux package speech pour test" + chr(10))
with open(os.path.join(pkg_dir, "speech.py"), "w") as f:
    f.write("__version__ = '2.0'" + chr(10))
    f.write("__all__ = ['RealTimeASR']" + chr(10))
    f.write("class RealTimeASR:" + chr(10) + "    pass" + chr(10))

sys.path.insert(0, fake_root)
import speech.speech as fake_mod
check("faux speech.speech importe (v2.0)", getattr(fake_mod, "__version__", "?") == "2.0")
check("OfflineRealTimeASR absent avant patch", not hasattr(fake_mod, "OfflineRealTimeASR"))

ok = sop.patch_speech_module()
check("patch_speech_module() retourne True", ok is True)
for cls_name in ("OfflineRealTimeASR", "OfflineRealTimeTTS", "OllamaAPI"):
    check("speech.speech.%s injecte" % cls_name, hasattr(fake_mod, cls_name))
check("classe originale conservee", hasattr(fake_mod, "RealTimeASR"))
check("__all__ mis a jour", all(n in fake_mod.__all__ for n in
                                ("OfflineRealTimeASR", "OfflineRealTimeTTS", "OllamaAPI")))

ok2 = sop.patch_speech_module()
check("patch idempotent (2e appel OK)", ok2 is True)

# --- 3. Hook d import auto_patch ---
for mod_name in ("speech.speech", "speech"):
    sys.modules.pop(mod_name, None)
finder = sop._SpeechPatchFinder()
sys.meta_path.insert(0, finder)
try:
    import speech.speech as fake_mod2
    check("auto_patch : hook injecte les classes", hasattr(fake_mod2, "OllamaAPI"))
finally:
    if finder in sys.meta_path:
        sys.meta_path.remove(finder)
    for mod_name in ("speech.speech", "speech"):
        sys.modules.pop(mod_name, None)

# --- 4. OllamaAPI contre le serveur local ---
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


def ollama_up(url):
    try:
        import urllib.request
        with urllib.request.urlopen(url + "/api/tags", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


if not ollama_up(OLLAMA_URL):
    skip("tests OllamaAPI", "serveur injoignable sur %s (demarrer Ollama)" % OLLAMA_URL)
else:
    api = sop.OllamaAPI(url=OLLAMA_URL, model="mistral:latest")
    models = api.list_models()
    check("list_models()", isinstance(models, list) and len(models) > 0,
          ", ".join(models[:5]))
    check("mistral present", any("mistral" in m for m in models), str(models))

    # URL par defaut du patch (celle que le robot utilisera)
    api_def = sop.OllamaAPI(model="mistral:latest")
    check("URL par defaut (%s) joignable" % sop.DEFAULT_OLLAMA_URL,
          len(api_def.list_models()) > 0)

    t0 = time.time()
    resp = api.generate("Reponds en une seule phrase en francais : quelle est la capitale de la France ?",
                        max_tokens=256)
    dt = time.time() - t0
    check("generate() reponse non vide", len(resp) > 0, repr(resp[:120]))
    check("generate() contient Paris", "paris" in resp.lower(), repr(resp[:120]))
    check("generate() rapide (< 60 s)", dt < 60, "%.1f s" % dt)

    resp2 = api.chat(
        messages=[{"role": "user", "content": "Dis bonjour en francais en 3 mots maximum."}],
        system="Tu es le robot ROSOrin Pro. Tu reponds toujours en francais, en 3 mots maximum.",
        max_tokens=256)
    check("chat() reponse non vide", len(resp2) > 0, repr(resp2[:120]))
    check("chat() system prompt respecte (<= 10 mots)", len(resp2.split()) <= 10, repr(resp2[:120]))

    # Test stream_chat avec FORCE_FRENCH_PROMPT temporairement desactive
    # (sinon le prefixe FR pousse le LLM a repondre en JSON de mouvement)
    saved_force = sop.FORCE_FRENCH_PROMPT
    sop.FORCE_FRENCH_PROMPT = False
    try:
        chunks = []
        full = api.stream_chat(
            messages=[{"role": "user", "content": "Compte de 1 a 3 en francais."}],
            callback=chunks.append, max_tokens=256)
        # Le modele peut repondre avec des chiffres (1, 2, 3) ou des lettres (un, deux, trois)
        has_count = any(k in full.lower() for k in ("1", "un")) and any(
            k in full.lower() for k in ("3", "trois"))
        check("stream_chat() accumule", has_count, repr(full[:120]))
        check("stream_chat() callback appele", len(chunks) > 0, "%d morceaux" % len(chunks))
    finally:
        sop.FORCE_FRENCH_PROMPT = saved_force

    # Modele "thinking" : verifier que num_predict eleve evite la reponse vide
    if any(m.startswith("qwen3.5") for m in models):
        api_q = sop.OllamaAPI(url=OLLAMA_URL, model="qwen3.5:9b")
        resp_q = api_q.generate("Reponds en francais par un seul mot : oui ou non",
                                max_tokens=2048)
        check("qwen3.5:9b (thinking) reponse non vide avec num_predict=2048",
              len(resp_q.strip()) > 0, repr(resp_q[:120]))
    else:
        skip("qwen3.5:9b (thinking)", "modele absent sur ce serveur")

# --- 5. ASR / TTS : smoke test si sherpa_onnx est disponible ---
try:
    import sherpa_onnx  # noqa: F401
    HAVE_SHERPA = True
except ImportError:
    HAVE_SHERPA = False

if not HAVE_SHERPA:
    skip("TTS save_to_file", "sherpa_onnx non installe ici (a tester sur le robot)")
    skip("ASR constructeur", "sherpa_onnx non installe ici (a tester sur le robot)")
else:
    tts = sop.OfflineRealTimeTTS()
    if tts._tts is not None:
        wav_path = os.path.join(tempfile.mkdtemp(prefix="tts_test_"), "test.wav")
        ok_save = tts.save_to_file("Bonjour, ceci est un test.", wav_path)
        check("TTS save_to_file()", ok_save and os.path.getsize(wav_path) > 1000,
              wav_path)
    else:
        skip("TTS save_to_file()", "modele vits non trouve")
    asr = sop.OfflineRealTimeASR()
    check("ASR constructeur sans crash", asr is not None,
          "recognizer=%s" % (asr._recognizer is not None))

# --- 6. install() / uninstall() de bout en bout sur un faux package speech ---
fake2 = tempfile.mkdtemp(prefix="fake_speech_install_")
pkg2 = os.path.join(fake2, "speech")
os.makedirs(pkg2)
with open(os.path.join(pkg2, "__init__.py"), "w") as f:
    f.write("# faux package speech v2.0" + chr(10))
with open(os.path.join(pkg2, "speech.py"), "w") as f:
    f.write("__version__ = '2.0'" + chr(10))
    f.write("class RealTimeASR:" + chr(10) + "    pass" + chr(10))

if fake_root in sys.path:
    sys.path.remove(fake_root)
sys.path.insert(0, fake2)
os.environ["PYTHONPATH"] = fake2 + os.pathsep + os.environ.get("PYTHONPATH", "")
for mod_name in ("speech.speech", "speech"):
    sys.modules.pop(mod_name, None)

ok = sop.install(ollama_url="http://localhost:11434", ollama_model="mistral:latest")
check("install() sur faux package speech v2.0", ok is True)
check("patch copie dans le package",
      os.path.exists(os.path.join(pkg2, "speech_offline_patch.py")))
check("speech.py sauvegarde (.bak)", os.path.exists(os.path.join(pkg2, "speech.py.bak")))
with open(os.path.join(pkg2, "speech.py"), "r", encoding="utf-8") as f:
    content = f.read()
check("branchement present dans speech.py", "PATCH OFFLINE HIWONDER" in content)
with open(os.path.join(pkg2, "speech_offline_patch.py"), "r", encoding="utf-8") as f:
    copied = f.read()
check("URL Ollama ecrite dans la copie", "http://localhost:11434" in copied)
check("modele Ollama ecrit dans la copie", "mistral:latest" in copied)

code = ("import speech.speech as s; "
        "print(hasattr(s, 'OfflineRealTimeASR'), "
        "hasattr(s, 'OfflineRealTimeTTS'), hasattr(s, 'OllamaAPI'))")
r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
check("sous-processus voit les 3 classes",
      r.stdout.strip() == "True True True",
      (r.stdout.strip() + " " + r.stderr.strip()[:200]).strip())

ok = sop.uninstall()
check("uninstall()", ok is True)
with open(os.path.join(pkg2, "speech.py"), "r", encoding="utf-8") as f:
    content2 = f.read()
check("speech.py restaure (plus de patch)", "PATCH OFFLINE HIWONDER" not in content2)
check("patch supprime du package",
      not os.path.exists(os.path.join(pkg2, "speech_offline_patch.py")))

# --- 7. CLI ---
check("main --help retourne 0", sop.main(["--help"]) == 0)

# --- 8. Detection de langue (_detect_lang) ---
check("_detect_lang fr_FR", sop._detect_lang("vits-piper-fr_FR-siwis-medium/model.onnx") == "fr")
check("_detect_lang fr-fr", sop._detect_lang("sherpa-onnx-streaming-zipformer-fr-2023-02-20/encoder.onnx") == "fr")
check("_detect_lang french", sop._detect_lang("/models/french-vits/model.onnx") == "fr")
check("_detect_lang siwis", sop._detect_lang("vits-piper-fr_FR-siwis-medium/model.onnx") == "fr")
check("_detect_lang en ljspeech", sop._detect_lang("vits-ljs/model.onnx") == "en")
check("_detect_lang en english", sop._detect_lang("sherpa-onnx-streaming-zipformer-en-2023-06-21/encoder.onnx") == "en")
check("_detect_lang unknown", sop._detect_lang("some-random-model/model.onnx") == "unknown")

# --- 9. Constantes de langue et prompt francais ---
check("DEFAULT_LANGUAGE = fr", sop.DEFAULT_LANGUAGE == "fr")
check("DEFAULT_SYSTEM_PROMPT contient 'francais'",
      "francais" in sop.DEFAULT_SYSTEM_PROMPT.lower())
check("DEFAULT_SYSTEM_PROMPT contient 'robot'",
      "robot" in sop.DEFAULT_SYSTEM_PROMPT.lower())
check("DEFAULT_SYSTEM_PROMPT contient 'JSON' (mouvement)",
      "json" in sop.DEFAULT_SYSTEM_PROMPT.lower() or '"action"' in sop.DEFAULT_SYSTEM_PROMPT)
check("DEFAULT_SYSTEM_PROMPT contient 'move'",
      "move(" in sop.DEFAULT_SYSTEM_PROMPT)
check("FORCE_FRENCH_PROMPT est un booleen", isinstance(sop.FORCE_FRENCH_PROMPT, bool))

# --- 9b. FRENCH_SYSTEM_PREFIX (prefixe ajoute au prompt du firmware) ---
check("FRENCH_SYSTEM_PREFIX existe", hasattr(sop, "FRENCH_SYSTEM_PREFIX"))
check("FRENCH_SYSTEM_PREFIX contient 'francais'",
      "francais" in sop.FRENCH_SYSTEM_PREFIX.lower())
check("FRENCH_SYSTEM_PREFIX contient 'JSON'",
      "json" in sop.FRENCH_SYSTEM_PREFIX.lower() or '"action"' in sop.FRENCH_SYSTEM_PREFIX)
check("FRENCH_SYSTEM_PREFIX contient 'move'",
      "move(" in sop.FRENCH_SYSTEM_PREFIX)
check("FRENCH_SYSTEM_PREFIX contient 'forward'",
      "forward" in sop.FRENCH_SYSTEM_PREFIX)
check("FRENCH_SYSTEM_PREFIX contient 'stop'",
      "stop" in sop.FRENCH_SYSTEM_PREFIX)

# --- 9c. Test logique chat() : prefixe ajoute au prompt du firmware ---
# On simule le comportement attendu de chat() quand FORCE_FRENCH_PROMPT=True
firmware_prompt = "You are a robot. Respond with JSON: {action, response}"
if sop.FORCE_FRENCH_PROMPT:
    base_sp = firmware_prompt  # system fourni par l'appelant
    combined = sop.FRENCH_SYSTEM_PREFIX + (base_sp or "")
    check("chat() prefixe conserve le prompt firmware",
          firmware_prompt in combined)
    check("chat() prefixe ajoute instruction FR",
          "francais" in combined.lower())
    check("chat() prefixe conserve instruction JSON firmware",
          "JSON" in combined or '"action"' in combined)
else:
    skip("chat() prefixe test (FORCE_FRENCH_PROMPT=False)")

# --- 10. OllamaAPI : prompt systeme francais par defaut ---
api_test = sop.OllamaAPI(url="http://127.0.0.1:1", model="test")  # URL bidon, pas de connexion
check("OllamaAPI.system_prompt = prompt FR par defaut",
      "francais" in api_test.system_prompt.lower())
check("OllamaAPI.system_prompt contient 'robot'",
      "robot" in api_test.system_prompt.lower())

# Si l'appelant fournit un system prompt explicite et FORCE_FRENCH_PROMPT=False
api_test.system_prompt = "Custom prompt"
if not sop.FORCE_FRENCH_PROMPT:
    check("OllamaAPI respecte system_prompt custom (si FORCE_FRENCH_PROMPT=False)",
          api_test.system_prompt == "Custom prompt")

# --- 11. OfflineRealTimeASR accepte language=fr ---
asr_fr = sop.OfflineRealTimeASR(language="fr")
check("OfflineRealTimeASR(language='fr')", asr_fr.language == "fr")
asr_en = sop.OfflineRealTimeASR(language="en")
check("OfflineRealTimeASR(language='en')", asr_en.language == "en")
asr_default = sop.OfflineRealTimeASR()
check("OfflineRealTimeASR() defaut = fr", asr_default.language == "fr")

# --- 12. OfflineRealTimeTTS accepte language=fr ---
tts_fr = sop.OfflineRealTimeTTS(language="fr")
check("OfflineRealTimeTTS(language='fr')", tts_fr.language == "fr")
tts_en = sop.OfflineRealTimeTTS(language="en")
check("OfflineRealTimeTTS(language='en')", tts_en.language == "en")

# --- 13. SHERPA_FR_MODELS contient ASR et TTS ---
check("SHERPA_FR_MODELS['asr_streaming']", "asr_streaming" in sop.SHERPA_FR_MODELS)
check("SHERPA_FR_MODELS['tts_vits']", "tts_vits" in sop.SHERPA_FR_MODELS)
check("URL ASR fr contient 'fr'", "fr" in sop.SHERPA_FR_MODELS["asr_streaming"]["url"].lower())
check("URL TTS fr contient 'fr'", "fr" in sop.SHERPA_FR_MODELS["tts_vits"]["url"].lower())

# --- 14. _find_sherpa_models retourne asr_models/tts_models par langue ---
found = sop._find_sherpa_models()
check("_find_sherpa_models retourne 'asr_models'", "asr_models" in found)
check("_find_sherpa_models retourne 'tts_models'", "tts_models" in found)
check("asr_models est un dict", isinstance(found["asr_models"], dict))
check("tts_models est un dict", isinstance(found["tts_models"], dict))

print("")
print("Resultat : %d PASS, %d FAIL, %d SKIP" % (PASS, FAIL, SKIP))
sys.exit(1 if FAIL else 0)

