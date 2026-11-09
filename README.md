# Robot — Hiwonder ROSOrin Pro

Robot mobile (roues mecanum, Jetson Orin NX, ROS 2 Humble) avec bras 6 axes, lidar, caméra RGB + profondeur Aurora 930 et micro WonderEcho Pro.

**Objectif** : lui donner des ordres à la voix (micro du robot ou du PC) ou depuis une page Web, et qu'il les exécute seul avec tous ses capteurs.

L'état détaillé est dans [`ETAT_PROJET.md`](ETAT_PROJET.md). Le plan de travail vient de l'[audit du 05/11/2026](docs/AUDIT_2026-11-05.md).

## Ce qui fonctionne aujourd'hui

| Fonction | Fichier | Remarque |
|---|---|---|
| Saisie du cube rouge | `speech_patch/pick_and_place_node_v6.py` | calibrée par démonstration (`teach_pick_v6.py` → `pick_calib.json`) |
| Détection couleur | `speech_patch/simple_color_detect_v3.py` | ~10 Hz sur l'image RGB |
| Surveillance des nœuds | `speech_patch/robot_watchdog.py` | relance automatique, démarrage au boot via crontab |
| Surveillance caméra | `speech_patch/camera_supervisor.py` | reset USB automatique |
| Ordres simples à la voix | `speech_patch/llm_move_bridge_node.py` | avance, recule, tourne, stop, salutations |
| Voix française hors ligne | `speech_patch/speech_offline_patch.py` | ASR + TTS sherpa-onnx, LLM Ollama sur le PC |
| Micro du PC | `speech_patch/pc_mic_sender.py` → `ws_audio_asr_node.py` | port 9092 |
| Page de commande | `speech_patch/robot_keypad.html` | lancée par `start_interface.bat` sur le PC |

Pas encore fiable : la mission « attrape tous les cubes », le retour à la base, la dépose dans le bac, l'évitement d'obstacles (voir l'audit).

## Démarrage

Le robot démarre tout seul : la crontab lance `speech_patch/start_watchdogs.sh`, qui lance les superviseurs, qui lancent les nœuds.

Sur le PC : double-clic sur `speech_patch/start_interface.bat`, puis ouvrir `http://localhost:8888/robot_keypad.html`.

Vérifier l'état du robot (lecture seule), dans l'Invite de commandes (`cmd`) depuis le dossier du dépôt :

```bat
scp speech_patch\verif_etat_robot.sh robot:/tmp/
ssh robot "sed -i 's/\r$//' /tmp/verif_etat_robot.sh && bash /tmp/verif_etat_robot.sh" > %TEMP%\verif_robot.txt
```

## Organisation du dépôt

```
README.md, ETAT_PROJET.md   état actuel
docs/                       audit, guides valides, essais par étape
docs/historique/            anciens comptes rendus de session (référence)
speech_patch/               code déployé sur le robot (/home/ubuntu/speech_patch)
speech_patch/archive/       anciennes versions, diagnostics ponctuels, anciens lanceurs
ros2_ws/src/toy_sorter/     simulation « range-jouets » (non reliée au robot réel)
sim/, training/             simulation et entraînement YOLO
```

Règle : les fichiers actifs de `speech_patch/` gardent leur nom et leur place, car le démarrage automatique et le watchdog les appellent par leur chemin sur le robot.
