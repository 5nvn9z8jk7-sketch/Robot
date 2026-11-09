# État du projet

Dernière mise à jour : 09/11/2026 — étape 0 : relevé E0 fait, installation (E1) prête.

## Relevé du robot du 09/11 (E0)

- Boot automatique OK (1 entrée crontab, 1 watchdog, 1 superviseur caméra).
- Caméra sur USB 3 : 6 943 images en 10 min, 0 gel, 0 relance, 0 erreur -71 → **rebranchement du 01/11 validé**.
- Capteurs : /odom 30 Hz, /scan 10 Hz, /imu 46 Hz, RGB 8 Hz, profondeur 12 Hz, détection couleur 10 Hz. Batterie 11,74 V.
- Déjà installés : Nav2 (dont `nav2_collision_monitor`), slam_toolbox, cartographer, cartes `~/ros2_ws/src/slam/maps/map_01..03`, `web_video_server`, `yolo`, OpenClaw.
- **8 publieurs sur `/controller/cmd_vel`** : nos 3 nœuds + 5 nœuds Hiwonder lancés au boot (`self_driving`, `joystick_control`, `lidar_app`, `line_following`, `object_tracking`) → à traiter à l'étape 1.
- Aucun publieur sur `/vocal_detect/asr_result` : ni micro robot ni micro PC actifs.
- Écarts robot / GitHub : `autonomous_mission_node.py` = version du 28/10 (« attrape » lançait mission + pick ensemble) ; `robot_watchdog.py` modifié sur le robot (2 corrections, intégrées au dépôt) ; `llm_move_bridge_node.py` identique (fins de ligne seulement).

## Plan (issu de l'audit du 05/11)

| Étape | Contenu | État |
|---|---|---|
| 0 | Remise en ordre : PR #3 (arrêt pick v6), ménage, lanceurs, doc | **préparée** sur la branche `etape-0-menage`, essais : [`docs/ESSAIS_ETAPE_0.md`](docs/ESSAIS_ETAPE_0.md) |
| 1 | Sécurité commune : arrêt global, priorité des commandes, anti-collision lidar | à faire |
| 2 | Routeur d'ordres unique (grammaire fixe + LLM), mêmes ordres voix robot / voix PC / page | à faire |
| 3 | Compétences fiables : déplacements mesurés, pick, dépose bac, recherche avec profondeur | à faire |
| 4 | Navigation avec carte (SLAM + Nav2), lieux nommés, retour base | à faire (prérequis : IMU) |
| 5 | Page Web unique servie par le robot, un seul chemin micro PC | à faire |
| 6 | Options : mot de réveil, vision-langage, paquet ROS 2 propre | plus tard |

## Étape 0 — ce qui a changé

- PR #3 incluse : arrêt d'urgence du pick v6 (« stop », touches 0/ESPACE), rotation en boucle odométrie, déclencheurs resserrés, images périmées ignorées.
- `robot_watchdog.py` : `pkill` avec motif entre crochets (il pouvait tuer sa propre commande).
- `start_interface.bat` : ne relance plus le contrôleur moteurs « nu » (cassait imu_raw et odom) ; « INACTIF » n'est plus pris pour « ACTIF ».
- `robot_keypad.html` : touche O (pince) désactivée tant qu'aucun nœud ne la traite ; P n'annonce plus une dépose inexistante.
- Rangement : 46 diagnostics ponctuels, 13 anciens lanceurs (dont ceux qui lançaient le pick v1 et `voice_pick_node`) et 4 nœuds remplacés déplacés dans `speech_patch/archive/`. Documentation ancienne dans `docs/historique/`.
- Nouveaux outils : `verif_etat_robot.sh` (relevé lecture seule), `maj_etape0.sh` (installation avec sauvegarde et retour arrière de 3 fichiers : pick v6, watchdog, mission).
- `.gitattributes` : fins de ligne LF forcées pour les scripts (le clone Windows les convertissait).

## Points ouverts connus

- IMU : correcteur compilé dans `~/imu_calib_ws`, non intégré au démarrage ; accélération au repos ≈ 9,38 m/s² (attendu ≈ 9,81).
- Dépose du cube dans le bac blanc (23 cm) : séquence non écrite ni testée.
- Sur le robot, les anciens fichiers restent dans `/home/ubuntu/speech_patch/` tant qu'ils ne sont pas supprimés à la main (sans danger s'ils ne sont pas lancés).

## Rappels techniques durables

- `bash -c 'source …'` obligatoire dans les scripts lancés par Python (dash ne connaît pas `source`) ; `bash -lc` ne source pas ROS sur ce robot.
- `pkill -f` : toujours un motif entre crochets (`'[p]ick_and_place_node_v6'`) et jamais le chemin du programme dans la même commande ssh.
- Relance manuelle du contrôleur : uniquement avec `-r __ns:=/ --params-file ~/speech_patch/params_ros_robot_controller.yaml` (le watchdog le fait).
- Le shell de connexion ssh du robot est zsh : dans une commande `ssh robot "..."`, utiliser `source /opt/ros/humble/setup.zsh` (ou passer par `bash -c`).
- Convention roues observée : `linear.x > 0` = avance.
