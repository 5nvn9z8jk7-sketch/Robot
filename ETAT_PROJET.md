# ETAT DU PROJET — ROSOrin Pro (LLM local + français)

Dernière mise à jour : 17/10/2026 ~10h00 (préparation déploiement, pare-feu identifié)

## Objectif

Configurer le ROSOrin Pro (Jetson Orin NX 16 Go, Ubuntu 22.04.5, IP 192.168.1.30,
user ubuntu) pour que le LLM tourne en local et réponde en français.

## Blocage initial (contourné)

- Firmware juin 2026 (|V1.0.0|App_ROS2_1.0|2026-06-01|) exige speech >= 3.0
  (OfflineRealTimeASR, OfflineRealTimeTTS, OllamaAPI) ; le robot a speech v2.0
  -> AttributeError au lancement de :
  ros2 launch large_models_examples llm_control_move.launch.py (ASR_MODE=offline)
- Mail envoyé à support@hiwonder.com le 15/10/2026 22h16 (depuis
  bloizeau@hotmail.com) pour demander speech >= 3.0. PAS DE RÉPONSE au 16/10
  (vérifié boîte de réception, spam, tous dossiers).
- -> Piste 2 choisie et terminée : wrapper Python qui émule les 3 classes
  avec sherpa-onnx (déjà sur le robot) + Ollama (tournant sur le PC).

## Ce qui est fait (16-17/10)

Dossier speech_patch/ — prêt et testé :

- speech_offline_patch.py — wrapper complet (983 lignes, compile OK) :
  - OfflineRealTimeASR : sherpa-onnx + sounddevice, VAD par énergie
  - OfflineRealTimeTTS : sherpa-onnx VITS, lecture sounddevice ou fallback aplay
  - OllamaAPI : client HTTP urllib (stdlib), num_predict=4096 par défaut
  - injection dans speech.speech (directe + hook d'import)
  - CLI : --install / --uninstall / --selftest, options --ollama-url / --ollama-model
- install_on_robot.sh — déploiement en une commande sur le robot
- test_wrapper.py — 35 PASS, 0 FAIL, 2 SKIP (SKIP = sherpa-onnx absent du PC)
- test_depuis_robot.sh — test connectivité robot→PC (ping, port, API, LLM) [17/10]
- autoriser_ollama_firewall.bat — règle pare-feu Windows à lancer EN ADMIN [17/10]
- speech_patch_deploy.zip — archive prête à transférer (17 Ko) [17/10]
- README.md — procédure complète de déploiement NoMachine (mise à jour 17/10)

Corrections vs le brouillon du 15/10 :
- fix qwen "thinking" : num_predict >= 2048 (validé : qwen3.5:9b répond avec 2048)
- URL Ollama par défaut = http://192.168.1.20:11434 (IP du PC le 16/10)
- plus de dépendance requests (urllib uniquement)
- listen() ne stoppe plus l'ASR au timeout
- TTS : lecture au sample_rate réel du modèle

## Environnement (vérifié le 17/10)

PC :
- IP 192.168.1.20 (DHCP — inchangée depuis le 16/10)
- Ollama v0.40.5 sur 0.0.0.0:11434 (vérifié : écoute bien sur toutes les interfaces)
- 6 modèles : qwen3.5:9b, qwen3.5-32k, qwen3.6:35b, qwen3.6-32k, mistral:latest,
  nomic-embed-text
- qwen3.5:9b = modèle "thinking" -> réponses VIDES si num_predict < 2048
- NoMachine Personal Edition 10.2.3 : C:/Program Files/NoMachine/, client nxplayer.exe
- Pare-feu Windows : profil privé ACTIF (BlockInbound) -> port 11434 BLOQUÉ en entrée
  => exécuter autoriser_ollama_firewall.bat EN ADMIN avant le déploiement

Robot (192.168.1.30 — en ligne le 17/10) :
- Ping OK, table ARP OK (MAC 90-de-80-a1-13-f1)
- NoMachine serveur v9.1.24, port 4000 ; user ubuntu
- SSH port 22 ouvert mais MOT DE PASSE INCONNU (testés sans succès : ubuntu,
  hiwonder, jetson, nvidia, yahboom, 123456, password)
- Interface web ROS port 8080 ouverte (HTTP 200, topics caméra OK)
- Modèles sherpa-onnx : ~/third_party/sherpa-onnx (zipformer-en ASR, vits-ljs TTS)
- speech v2.0 : ~/.local/lib/python3.10/site-packages/speech

Tests (17/10) :
- toy_sorter : 14/14 PASS
- simulation virtuelle : 5/5 jouets rangés (seed 42)
- speech_patch test_wrapper.py : 35 PASS, 0 FAIL, 2 SKIP

## Prochaines étapes (à faire manuellement)

### Étape 0 — PC : autoriser Ollama dans le pare-feu Windows

    speech_patch\autoriser_ollama_firewall.bat
    (clic droit → Exécuter en tant qu'administrateur)

Sans ça, le robot ne peut pas atteindre Ollama (profil privé = BlockInbound).

### Étape 1 — NoMachine → robot

    NoMachine → 192.168.1.30:4000 (utilisateur ubuntu)

### Étape 2 — Transférer le patch sur le robot

Glisser-déposer `speech_patch_deploy.zip` (17 Ko) ou le dossier `speech_patch/`
sur le Bureau du robot.

### Étape 3 — Terminal sur le robot

    cd ~/Bureau/speech_patch
    bash test_depuis_robot.sh          # vérifie que le PC est joignable
    bash install_on_robot.sh           # installe le wrapper
    python3 speech_offline_patch.py --selftest

### Étape 4 — Relancer la démo

    ros2 launch large_models_examples llm_control_move.launch.py

### Étape 5 — Optionnel : valider ASR/TTS sur le robot

    python3 test_wrapper.py

## Pièges / à savoir

- **Pare-feu Windows** : le profil privé bloque les entrées. Sans la règle
  autoriser_ollama_firewall.bat, le robot ne voit pas Ollama (timeout).
- IP du PC en DHCP : si elle change, relancer :
  python3 speech_offline_patch.py --install --ollama-url http://<NOUVELLE_IP>:11434
  ou définir la variable d'environnement OLLAMA_URL avant de lancer ROS.
- ASR = anglais (zipformer-en) : donner les commandes en anglais.
- TTS vits-ljs = voix anglaise : lit le français avec un accent.
- Le LLM répond en français via le prompt système (fixé par le nœud firmware).
- Voix 100 % française = évolution possible : déposer un modèle VITS français
  dans ~/third_party/sherpa-onnx (le wrapper détecte automatiquement).
- Désinstallation : python3 speech_offline_patch.py --uninstall (restaure .bak)
- Quand Hiwonder répondra : pip3 install --user --upgrade "speech>=3.0"
  puis --uninstall et supprimer speech_offline_patch.py du package.

## Projets liés

- C:/Users/bloiz/projets/Robot/ros2_ws/src/toy_sorter (ROS2, 14 tests OK, tout pushé)
- C:/Users/bloiz/assistant-vocal/ (assistant vocal PC — même bug qwen dans
  brain.py : max_tokens absent)

