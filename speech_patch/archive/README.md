# Archive — anciennes versions

Ces fichiers ne sont plus utilisés par les scripts de lancement. Ils sont gardés
pour référence (l'historique Git les conserve aussi).

| Fichier | Remplacé par |
|---|---|
| `pick_and_place_node.py`, `_v2` à `_v5`, `_v5_diag` | `../pick_and_place_node_v6.py` |
| `simple_color_detect.py`, `_v2` | `../simple_color_detect_v3.py` |
| `calibrate_pick.py`, `calibrate_pick_v5.py` | `../teach_pick_v6.py` + `../pick_calib.py` |
| `deploy_pick_v2.sh` à `_v4.sh` | `../start_watchdogs.sh` |
| `camera_watchdog.sh` | `../camera_supervisor.py` |
| `robot_params_backup.txt` | sauvegarde ponctuelle des paramètres du robot |

Attention : sur le robot, les anciens fichiers restent dans `/home/ubuntu/speech_patch/`
tant qu'ils ne sont pas supprimés à la main.

## Ajouts de l'étape 0 (09/11/2026)

| Dossier | Contenu | Pourquoi archivé |
|---|---|---|
| `diagnostics/` | scripts `check_*`, `debug_*`, `test_*`, `probe_*`, `grep_*`, `read_*`… | diagnostics ponctuels des sessions d'octobre, plus utilisés |
| `anciens_lanceurs/` | `restart_all.sh`, `launch_pap.sh`, `start_pick_and_place.sh`, `start_pick_place_demo.sh`, `deploy_all.sh`, `camera_watchdog_v2.sh`… | lançaient le pick v1 ou `voice_pick_node` (conflit avec v6), relançaient le contrôleur sans paramètres, ou faisaient doublon avec le watchdog. Le seul lanceur est désormais `../start_watchdogs.sh` (appelé au boot). |
| `anciens_noeuds/` | `voice_pick_node.py`, `pick_and_place_servo.py`, `calibration_measure_node.py`, `voice_bridge.py` | remplacés par `pick_and_place_node_v6.py` et `llm_move_bridge_node.py` |
