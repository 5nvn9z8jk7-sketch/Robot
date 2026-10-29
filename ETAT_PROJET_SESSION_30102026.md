# 📋 SESSION 30/10/2026 — Calibration pince v6 : LE ROBOT ATTRAPE LE CUBE 🏆

## Résumé exécutif

Calibration complète de la pince via la nouvelle chaîne **teach_pick_v6 → pick_calib.json → pick_and_place_node_v6**.
Après correction de 5 bugs (3 logiciels, 2 matériels), le pick complet fonctionne :
**détection → centrage → approche → avance exacte (odom) → prise validée.**

---

## ✅ Calibration finale (`speech_patch/pick_calib.json`, déployée sur le robot)

| Paramètre | Valeur | Signification |
|-----------|--------|---------------|
| servo_positions | {1:500, 2:40, 3:450, 4:230, 5:500} | bras posé, doigts ~1 cm du sol, bras pointant DROIT DEVANT |
| gripper_close | 560 | fermeture pince (prise testée OK) |
| target_x | 328 | cible caméra (compense ~2 cm d'offset pince/caméra à droite) |
| target_y / target_size | 113 / 60 px | signature cube à la position de référence (~20 cm devant) |
| extra_forward_m | 0.126 | avance à l'aveugle finale, boucle fermée sur /odom |
| noise_px | 0.6 | bruit de mesure |

**Méthode « plan B »** : le point de grip est SOUS le champ de la caméra (invisible).
On mesure une position de référence visible + distance au mètre → v6 centre le cube
sur la signature, avance exactement, puis descend la pince aux positions apprises.

---

## 🆕 Nouveaux fichiers (tous déployés sur le robot)

- `simple_color_detect_v3.py` — publie TOUJOURS (data:[] si rien) et **publie vide si >1 s
  sans frame fraîche** (une caméra morte ne fait plus publier une image gelée comme fraîche)
- `pick_calib.py` — bibliothèque de calibration partagée (load/save pick_calib.json)
- `teach_pick_v6.py` — outil interactif d'apprentissage (reprend les positions existantes,
  retries automatiques pendant que le watchdog caméra relance le flux)
- `pick_and_place_node_v6.py` — pick piloté par la calibration :
  - `_drive` en **boucle fermée sur /odom** (30 Hz) → distance exacte
  - relit pick_calib.json à chaque run (modifier la calibration sans redémarrer)
  - déclenchement : touche **P** du keypad ou « attrape le cube rouge » (topic /vocal_detect/asr_result)
- `camera_watchdog_v2.sh` — **déployé sur le robot** (relance la caméra en boucle)
- scripts diagnostic : `test_servo_camera.sh`, `test_arm_up_camera.sh`, `run_factory_action.sh`,
  `probe_servo_state.sh`, `probe_serial_ports.sh`

## 🔧 Corrections de la session

1. **Keypad : servos muets** — `position_unit: 'pwm'` → `'pulse'` (le contrôleur n'accepte que pulse)
2. **Convention cmd_vel inversée héritée de v5** — le robot reculait au lieu d'avancer.
   Convention réelle (keypad) : `+x = AVANCE`, `+z = GAUCHE`. v6 corrigé ; **v5 garde le bug**
3. **robot_watchdog.py** — mis à jour : lance v6 et v3 (plus v5/v2), ne gère plus la caméra
   (doublon avec camera_watchdog_v2)
4. **Images gelées** — voir v3 ci-dessus ; c'est ce qui faisait tourner le robot dans le vide
   sur une image morte pendant les picks

## 🔩 Pannes matérielles rencontrées (résolues)

1. **Bras pointant à 90° à gauche** : les 4 vis de la base du bras étaient desserrées →
   dévissées, bras réorienté, revissé (réf. usine : servo1=500 = avant, cf navigation_pick.d6a)
2. **Chaîne servo muette** (tous servos, lecture et écriture) après la réparation de la base →
   connecteur/câble, résolu après coupure/restauration d'alimentation
3. **Caméra aurora930 instable** : crash-loop ~1×/min (historique wdt_count:75) — le watchdog v2
   la relance en ~25 s ; survit aux mouvements de servos (testé). **À investiguer : câble USB / alim**

## 📐 Conventions vérifiées (pour les futures sessions)

- cmd_vel : `+x = avance`, `+z = gauche` (source : keypad web, validé utilisateur)
- servos : topic `/servo_controller`, `position_unit: "pulse"`, IDs 1-5 + 10 (pince)
- chaîne servo : topic → nœud servo_controller → `/ros_robot_controller/bus_servo/set_position` → board
- board : `/dev/rrc → ttyACM0` (règle udev **générique** `KERNEL=="ttyACM*"` — risque si un autre ttyACM énumère)
- `pkill -f` : TOUJOURS un pattern bracketé `[x]` ET jamais le chemin de lancement dans la
  même commande (self-kill vécu 4 fois)
- lancement de nœuds manuels : `bash -lc 'source …'` + `setsid nohup` (le shell distant est zsh)
- relance manuelle ros_robot_controller : `install/ros_robot_controller/lib/ros_robot_controller/ros_robot_controller --ros-args -r __ns:=/ --params-file /tmp/launch_params_XXX` (sourcer bash -lc !) ; après reboot c'est bringup qui le lance

## 🚀 Utilisation

```bash
# Tout est supervisé par les watchdogs (robot_watchdog + camera_watchdog_v2)
# Pick : touche P du keypad, ou :
ssh robot "bash -c 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && ros2 topic pub --once /vocal_detect/asr_result std_msgs/msg/String \"data: Attrape le cube rouge\"'"

# Recalibrer si besoin :
ssh -t robot   → python3 /home/ubuntu/speech_patch/teach_pick_v6.py

# Ajuster la calibration sans re-calibrer :
# éditer pick_calib.json (extra_forward_m, gripper_close max 700, target_x…)
```

## 📌 Reste à faire

- **Stabilité caméra** (matériel) : câble USB / alimentation de l'aurora930
- v5 : soit porter les corrections (cmd_vel, images gelées), soit l'abandonner pour v6
- Bouton P du keypad : OK après rechargement ; boutons vocaux nécessitent Ollama sur le PC (192.168.1.20:11434)
- Bug launch `deploy_watchdog.sh` : le watchdog meurt avec la session ssh → utiliser le pattern setsid
