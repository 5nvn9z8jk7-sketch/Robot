# Archive — anciennes versions

Ces fichiers ne sont plus utilisés par les scripts de lancement. Ils sont gardés
pour référence (l'historique Git les conserve aussi).

| Fichier | Remplacé par |
|---|---|
| `pick_and_place_node.py`, `_v2` à `_v5`, `_v5_diag` | `../pick_and_place_node_v6.py` |
| `simple_color_detect.py`, `_v2` | `../simple_color_detect_v3.py` |
| `calibrate_pick.py`, `calibrate_pick_v5.py` | `../teach_pick_v6.py` + `../pick_calib.py` |
| `deploy_pick_v2.sh` à `_v4.sh` | `../deploy_all.sh` |
| `camera_watchdog.sh` | `../camera_watchdog_v2.sh` |
| `robot_params_backup.txt` | sauvegarde ponctuelle des paramètres du robot |

Attention : sur le robot, les anciens fichiers restent dans `/home/ubuntu/speech_patch/`
tant qu'ils ne sont pas supprimés à la main.
