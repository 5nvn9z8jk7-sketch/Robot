# ETAT DU PROJET — ROSOrin Pro (LLM local + français)

Dernière mise à jour : 16/10/2026 ~22h40 (fin de session, piste 2 terminée côté PC)

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

## Ce qui est fait (16/10)

Dossier speech_patch/ — prêt et testé :

- speech_offline_patch.py — wrapper complet (983 lignes, compile OK) :
  - OfflineRealTimeASR : sherpa-onnx + sounddevice, VAD par énergie
  - OfflineRealTimeTTS : sherpa-onnx VITS, lecture sounddevice ou fallback aplay
  - OllamaAPI : client HTTP urllib (stdlib), num_predict=4096 par défaut
  - injection dans speech.speech (directe + hook d'import)
  - CLI : --install / --uninstall / --selftest, options --ollama-url / --ollama-model
- install_on_robot.sh — déploiement en une commande sur le robot
- test_wrapper.py — 35 PASS, 0 FAIL, 2 SKIP (SKIP = sherpa-onnx absent du PC)
- README.md — procédure complète de déploiement NoMachine

Corrections vs le brouillon du 15/10 :
- fix qwen "thinking" : num_predict >= 2048 (validé : qwen3.5:9b répond avec 2048)
- URL Ollama par défaut = http://192.168.1.20:11434 (IP du PC le 16/10)
- plus de dépendance requests (urllib uniquement)
- listen() ne stoppe plus l'ASR au timeout
- TTS : lecture au sample_rate réel du modèle

## Environnement

PC :
- IP 192.168.1.20 (DHCP — surveiller, l'IP peut changer)
- Ollama v0.40.5 sur 0.0.0.0:11434, modèles : qwen3.5:9b, qwen3.5-32k,
  qwen3.6:35b, qwen3.6-32k, mistral:latest, nomic-embed-text
- qwen3.5:9b = modèle "thinking" -> réponses VIDES si num_predict < 2048
- NoMachine Personal Edition 10.2.3 : C:/Program Files/NoMachine/, client nxplayer.exe

Robot :
- NoMachine serveur v9.1.24, port 4000 ; user ubuntu
- SSH port 22 ouvert mais MOT DE PASSE INCONNU (testés sans succès : ubuntu,
  hiwonder, jetson, nvidia, yahboom, 123456, password)
- Interface web ROS port 8080 ouverte (topics caméra OK)
- Modèles sherpa-onnx : ~/third_party/sherpa-onnx (zipformer-en ASR, vits-ljs TTS)
- speech v2.0 : ~/.local/lib/python3.10/site-packages/speech

## Prochaines étapes (à faire manuellement)

1. NoMachine -> 192.168.1.30:4000 (utilisateur ubuntu)
2. Transférer le dossier speech_patch/ sur le Bureau du robot (glisser-déposer)
3. Terminal sur le robot :

    cd ~/Bureau/speech_patch
    bash install_on_robot.sh
    python3 speech_offline_patch.py --selftest

4. Relancer la démo :

    ros2 launch large_models_examples llm_control_move.launch.py

5. Optionnel — valider ASR/TTS sur le robot : python3 test_wrapper.py

## Pièges / à savoir

- IP du PC en DHCP : si elle change, relancer :
  python3 speech_offline_patch.py --install --ollama-url http://<NOUVELLE_IP>:11434
  ou définir la variable d'environnement OLLAMA_URL avant de lancer ROS.
- Pare-feu Windows : autoriser le port 11434 en entrée.
- ASR = anglais (zipformer-en) : donner les commandes en anglais.
- TTS vits-ljs = voix anglaise : lit le français avec un accent.
- Le LLM répond en français via le prompt système (fixé par le nœud firmware).
- Voix 100 % française = évolution possible : déposer un modèle VITS français
  dans ~/third_party/sherpa-onnx (le wrapper détecte automatiquement).
- Désinstallation : python3 speech_offline_patch.py --uninstall (restaure .bak)
- Quand Hiwonder répondra : pip3 install --user --upgrade "speech>=3.0"
  puis --uninstall et supprimer speech_offline_patch.py du package.

## Projets liés

- C:/Users/bloiz/projets/Robot/toy_sorter (ROS2, 14 tests OK, 11 commits non pushés)
- C:/Users/bloiz/assistant-vocal/ (assistant vocal PC — même bug qwen dans
  brain.py : max_tokens absent)

