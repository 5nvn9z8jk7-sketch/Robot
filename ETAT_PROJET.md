# ETAT DU PROJET — ROSOrin Pro (LLM local + speech offline)

Dernière mise à jour : 17/10/2026 ~22h00 — **DÉPLOIEMENT RÉUSSI**, robot sans batterie

## Objectif

Configurer le ROSOrin Pro (Jetson Orin NX 16 Go, Ubuntu 22.04.5, IP 192.168.1.30,
user ubuntu) pour que le LLM tourne en local et réponde (français via prompt système).

## Blocage initial (RÉSOLU par contournement)

- Firmware juin 2026 (|V1.0.0|App_ROS2_1.0|2026-06-01|) exige speech >= 3.0
  (OfflineRealTimeASR, OfflineRealTimeTTS, OllamaAPI) ; le robot a speech v2.0
  avec un module compilé `speech.so` (pas de `speech.py`)
- Mail envoyé à support@hiwonder.com le 15/10/2026 — **pas de réponse**
- **Solution déployée** : wrapper Python `speech_offline_patch.py` qui émule
  les 3 classes avec sherpa-onnx (ASR/TTS) + Ollama (LLM)

## ✅ DÉPLOIEMENT RÉUSSI (17/10 ~21h55)

### Tous les nœuds speech fonctionnent :

| Nœud | Statut | Détails |
|------|--------|---------|
| `tts_node` | ✅ | `TTS initialise (config): vits-ljs.onnx` |
| `vocal_detect` | ✅ | `OnlineRecognizer` streaming initialisé |
| `agent_process` | ✅ | LLM répond : `Ready! 有什么我可以帮您的吗？` |
| `llm_control_move` | ✅ | Démarré, prêt pour commandes |

### Chaîne fonctionnelle :
```
Micro → ASR (sherpa-onnx streaming, anglais) → LLM (Ollama qwen3:1.7b)
      → Réponse texte → TTS (sherpa-onnx VITS, voix anglaise) → Haut-parleur
      → Actions mouvement (si hardware OK)
```

## Ce qui est fait

### Dossier speech_patch/ (déployé et fonctionnel) :

- `speech_offline_patch.py` — wrapper complet (~44 Ko) :
  - **OfflineRealTimeASR** : sherpa-onnx, supporte streaming (OnlineRecognizer)
    et offline (OfflineRecognizer), détection auto selon le chemin
  - **OfflineRealTimeTTS** : sherpa-onnx VITS, init robuste multi-fallbacks
  - **OllamaAPI** : client HTTP urllib, méthodes `chat()`, `generate()`,
    `llm()` (compat agent_process), `stream_chat()`
  - Injection dans `speech.speech` via `__init__.py` (module .so)
  - CLI : --install / --uninstall / --selftest
- `install_on_robot.sh` — déploiement (gère speech.py absent / speech.so)
- `test_wrapper.py` — 35 PASS, 0 FAIL, 2 SKIP
- `test_depuis_robot.sh` — test connectivité robot→PC
- `autoriser_ollama_firewall.bat` — règle pare-feu Windows (admin)
- `speech_patch_deploy.zip` — archive prête (19 Ko, gitignored)

### Corrections clés (17/10 soir) :

1. **Module speech.so** : le robot n'a pas `speech.py` mais `speech.so` (compilé).
   Le wrapper s'injecte via `__init__.py` avec `auto_patch()`.
2. **ASR streaming** : le modèle est `sherpa-onnx-streaming-zipformer-en`.
   Utilisation de `OnlineRecognizer` (pas `OfflineRecognizer`).
3. **Méthode `asr()`** ajoutée (alias de `listen()`) pour `vocal_detect`.
4. **Méthode `llm()`** ajoutée à OllamaAPI pour `agent_process`.
5. **Modèle qwen3:1.7b** téléchargé sur PC ET sur robot (config `offline_llm`).
6. **Détection sherpa-onnx** améliorée : cherche dans le chemin complet
   (dossier parent contient "zipformer"), supporte encoder/decoder/joiner.
7. **TTS init robuste** : multiples fallbacks pour différentes versions sherpa-onnx.
8. **OLLAMA_URL env var** prioritaire sur l'URL passée par le nœud.

## Environnement

### PC (192.168.1.20 — DHCP) :

- Ollama v0.40.5 sur 0.0.0.0:11434
- Modèles : qwen3.5:9b, qwen3.5-32k, qwen3.6:35b, qwen3.6-32k,
  mistral:latest, nomic-embed-text, **qwen3:1.7b** (ajouté 17/10)
- Pare-feu Windows : règle "Ollama 11434 (Robot ROSOrin)" créée
- NoMachine client : nxplayer.exe

### Robot (192.168.1.30 — sans batterie, à recharger) :

- NoMachine serveur v9.1.24, port 4000 ; user ubuntu
- Dossier `~/Desktop/speech_patch/` avec le wrapper à jour
- Package patché : `~/.local/lib/python3.10/site-packages/speech/`
  - `__init__.py` modifié (auto_patch)
  - `speech_offline_patch.py` copié (version 17/10 21h55)
  - `__init__.py.bak` sauvegarde
- `~/.bashrc` : `export OLLAMA_URL=http://192.168.1.20:11434` ajouté
- Modèles sherpa-onnx : `~/third_party/sherpa-onnx/`
  - ASR : `sherpa-onnx-streaming-zipformer-en-2023-06-21/` (streaming)
  - TTS : `vits-ljs/vits-ljs.onnx`
- Ollama local : modèles qwen3-vl:2b, qwen3:1.7b, qwen3:0.6b
- Speech v2.0 avec module compilé `speech.so`

## Commandes de reprise (quand batterie rechargée)

```bash
# 1. Allumer le robot, attendre le boot
# 2. NoMachine → 192.168.1.30:4000 (user ubuntu)
# 3. Terminal sur le robot :

cd ~/Desktop
source ~/.bashrc                    # charge OLLAMA_URL

# Vérifier que tout est en place :
python3 speech_patch/speech_offline_patch.py --selftest

# Lancer la démo :
ros2 launch large_models_examples llm_control_move.launch.py

# Parler en anglais au robot (ASR = anglais) :
#   "Move forward one meter"
#   "Turn left"
#   "Stop"
```

## Améliorations possibles

1. **Forcer LLM du PC** : `agent_process` utilise `localhost:11434` par défaut.
   Avec `OLLAMA_URL` défini, il utilisera le PC (gros modèles).
   Vérifier : `echo $OLLAMA_URL` doit afficher `http://192.168.1.20:11434`

2. **Voix française** : télécharger un modèle VITS français dans
   `~/third_party/sherpa-onnx/` (le wrapper détecte automatiquement)

3. **ASR français** : télécharger un modèle zipformer français
   (remplacer le modèle anglais)

4. **Réponse en français** : le LLM répond dans la langue du prompt système
   (fixé par le nœud firmware, en chinois actuellement)

5. **Hardware** : erreurs `SerialException` sur `ros_robot_controller` —
   câble USB ou contrôleur série à vérifier (moteurs/servos)

## Pièges / à savoir

- **IP PC en DHCP** : si elle change, mettre à jour `OLLAMA_URL` dans
  `~/.bashrc` et relancer
- **ASR = anglais** : parler en anglais
- **TTS = voix anglaise** : lit le chinois/français avec accent
- **qwen3:1.7b = thinking** : réponses vides si num_predict < 2048
  (le wrapper envoie 4096 par défaut)
- **Désinstallation** : `python3 speech_offline_patch.py --uninstall`
- **Terminal zsh** : le robot utilise zsh, pas bash (erreurs `shopt` normales)
- **Chemin `~`** : toujours utiliser `~` ou `/home/ubuntu`, pas `/` seul

## Git

Dernier commit : `7600a16` (17/10 ~22h00)
- `speech_patch : fix ASR streaming + méthode asr() + TTS init robuste`
- Tout est pushé sur `origin/main`

## Projets liés

- `ros2_ws/src/toy_sorter/` — Toy Sorter (14 tests OK, simulation fonctionnelle)
- `C:/Users/bloiz/assistant-vocal/` — assistant vocal PC (même bug qwen)

---

**Prochaine session** : recharger la batterie, tester les commandes vocales,
puis passer au projet toy_sorter.
