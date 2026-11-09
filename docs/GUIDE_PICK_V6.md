# Guide Pick-and-Place v6 — calibration par démonstration

## Pourquoi la v5 attrapait dans le vide

| # | Problème v5 | Effet observé |
|---|-------------|---------------|
| 1 | La caméra est **montée sur le bras**, mais le bras n'était jamais remis dans une pose fixe avant la détection (après un pick, ou après T/G/F/H/N au clavier, la caméra regarde ailleurs) | Calibration fausse dès le 2e essai, `camera_to_gripper_offset` impossible à régler |
| 2 | `simple_grip=True` par défaut : l'ajustement de distance était **sauté** | Le bras descend là où le robot se trouve, + 5 cm en aveugle |
| 3 | Mouvements « durée × vitesse » sans retour (5 cm = 0,5 s, avalé par l'accélération) | Distances et rotations imprécises |
| 4 | Le dernier cube détecté restait en mémoire pour toujours | Le robot vise un cube « fantôme » quand il sort du champ |
| 5 | « attrape cube » déclenchait **aussi** `autonomous_mission_node` (mot-clé `attrape`) | Deux programmes pilotent roues + bras en même temps → zigzag gauche/droite |
| 6 | Annonce « cube attrapé » sans vérification | Faux succès |

## Ce que fait la v6

1. `teach_pick_v6.py` : tu poses le cube **entre les doigts** de la pince au sol, le bras remonte en pose d'observation et le script mémorise **où le cube apparaît dans l'image**. C'est la cible.
2. `pick_and_place_node_v6.py` : bras toujours en pose d'observation → le robot se déplace en continu (20 Hz, crabe + avance) jusqu'à ce que le cube soit sur la cible à ±5 px → même descente que pendant la calibration → vérifie que le cube n'est plus au sol (sinon 2e essai).
3. `simple_color_detect_v3.py` : publie un message vide quand il n'y a pas de cube, filtre de forme (carré), seuils réglables, image de debug.
4. `autonomous_mission_node.py` : ne réagit plus à « attrape cube » (seulement « attrape tous », « mission »…), mots-clés en mots entiers.
5. `robot_watchdog.py` et `deploy_all.sh` : lancent v3 + v6 au lieu de v2 + v5.

Plus besoin de `camera_to_gripper_offset`, `gripper_reach`, `target_size_px` ni de mesure au mètre.

## Installation sur le robot

Depuis le PC (dossier du dépôt) :

```bash
scp speech_patch/pick_calib.py speech_patch/teach_pick_v6.py speech_patch/pick_and_place_node_v6.py \
    speech_patch/simple_color_detect_v3.py speech_patch/autonomous_mission_node.py \
    speech_patch/robot_watchdog.py speech_patch/deploy_all.sh robot:/home/ubuntu/speech_patch/
```

## Étape 1 — Arrêter tout ce qui gêne

```bash
ssh robot
pkill -f robot_watchdog; pkill -f pick_and_place_node; pkill -f simple_color_detect
pkill -f joystick_control; pkill -f line_following; pkill -f object_tracking
pkill -f self_driving; pkill -f lidar_controller; pkill -f voice_control_move
pkill -f autonomous_mission_node
source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash
```

## Étape 2 — Lancer la détection v3 et vérifier

```bash
setsid nohup python3 -u /home/ubuntu/speech_patch/simple_color_detect_v3.py >/tmp/color.log 2>&1 < /dev/null &
ros2 topic echo /color_detect_node/color_info
```

- Cube devant le robot → un `data:` avec `x`, `y`. Sans cube → `data: []`.
- Si détections parasites ou cube non vu : regarder l'image de debug (via NoMachine : `ros2 run rqt_image_view rqt_image_view /color_detect_node/debug_image`) et ajuster :
  `ros2 param set /simple_color_detect s_min 130` (plus strict) ou `90` (plus permissif), idem `v_min`, `min_area`.
- Évite les objets rouges/orangés/roses dans le champ et la lumière directe du soleil.

## Étape 3 — Calibration par démonstration (2 minutes)

```bash
ssh -t robot
source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash
cd /home/ubuntu/speech_patch && python3 teach_pick_v6.py
```

1. Le bras descend, pince ouverte. Ajuste si besoin (`3 -10`, `2 +20`, `4 +10`…) pour que les doigts soient à ~1 cm du sol. `f` ferme la pince pour tester la prise, `o` la rouvre.
2. `ok`, puis pose le cube **pile au centre** entre les doigts → Entrée.
3. Le bras remonte (le cube reste au sol), le script mesure et sauvegarde `pick_calib.json`.

Ne pas bouger le robot pendant cette étape. Refaire la calibration si tu changes de cube ou de sol.

## Étape 4 — Tester

```bash
setsid nohup python3 -u /home/ubuntu/speech_patch/pick_and_place_node_v6.py >/tmp/pick_v6.log 2>&1 < /dev/null &
tail -f /tmp/pick_v6.log
```

Place le cube à ~15-25 cm devant le robot, puis touche **P** dans l'interface web (ou dis « attrape le cube »).
Dans les logs : `cube=(x,y) err=(ex,ey)px` doit tendre vers 0, puis `En position`.

## Réglages si besoin (sans redémarrer)

```bash
ros2 param set /pick_and_place_node_v6 <param> <valeur>
```

| Symptôme | Réglage |
|----------|---------|
| Le robot s'écarte du cube sur le côté au lieu de s'en rapprocher | `invert_x true` |
| Le robot recule au lieu d'avancer | `invert_y true` |
| Il oscille autour du cube | baisser `kx` / `ky` (ex : `0.0015`) |
| Il s'approche mais ne « valide » jamais | `tol_px 8` ou augmenter `min_lin` (0.035) |
| Pas de mouvement latéral (châssis non mecanum) | `use_strafe false` |
| La pince se ferme juste devant / derrière le cube | refaire `teach_pick_v6.py` en posant le cube bien au centre |
| Le cube glisse de la pince | `gripper_close` à 600 dans `pick_calib.json` (jamais > 700) |

Quand tout marche, relance le tout normalement avec `bash /home/ubuntu/speech_patch/deploy_all.sh` (le watchdog relance maintenant v3 + v6).
