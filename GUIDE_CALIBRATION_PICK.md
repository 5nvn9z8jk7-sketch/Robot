# 🎯 Guide de calibration Pick-and-Place (sans caméra depth)

## Prérequis

1. **Nœud `pick_and_place_node_v2` actif** sur le robot (déjà déployé)
2. **Cube rouge visible** par la caméra du robot
3. **Détection couleur active** : `ros2 topic echo /color_detect_node/color_info`

---

## Étape 1 : Placer le robot

Mets le robot au sol, face au cube rouge, à environ **30-50 cm** du cube.

```
    🤖 ←── 30-50 cm ──→ 🔴
   robot              cube
```

Vérifie que la détection voit le cube :
```bash
ssh robot "bash -lc 'source /home/ubuntu/ros2_ws/install/setup.bash && ros2 topic echo /color_detect_node/color_info --once'"
```
Tu dois voir `color: red` avec des coordonnées x, y.

---

## Étape 2 : Lancer la calibration

**Sur le PC**, double-clique sur :
```
Bureau → Calibrer Pick.bat
```

Ou en ligne de commande :
```bash
cd C:\Users\bloiz\projets\Robot\speech_patch
python calibrate_pick.py
```

---

## Étape 3 : Calibrer la distance

Menu interactif :

| Touche | Action |
|--------|--------|
| **Z / S** | Avancer / Reculer 10 cm |
| **A / E** | Avancer / Reculer 5 cm (ajustement fin) |
| **Q / D** | Tourner Gauche / Droite 10° |
| **Espace** | STOP immédiat |
| **G** | Tester le bras (préhension seule) |
| **+ / -** | Augmenter / Diminuer la distance fixe (±5 cm) |
| **V** | Voir la détection couleur actuelle |
| **T** | Tester la séquence complète |
| **X** | Quitter |

### Procédure de calibration :

1. **Ajuste la position** avec Z/S/Q/D pour que le robot soit bien face au cube
2. **Appuie sur V** pour vérifier que le cube rouge est détecté
3. **Appuie sur G** pour tester le bras seul (vérifier qu'il descend et remonte)
4. **Appuie sur T** pour tester la séquence complète
5. **Si le robot n'avance pas assez** → appuie sur **+** (augmente la distance)
6. **Si le robot avance trop** → appuie sur **-** (diminue la distance)
7. **Répète** jusqu'à ce que le bras attrape le cube

---

## Étape 4 : Ajuster les paramètres fins (optionnel)

Si besoin, ajuste directement sur le robot :

```bash
# Distance fixe à avancer après centrage (en mètres)
ssh robot "bash -lc 'source /home/ubuntu/ros2_ws/install/setup.bash && ros2 param set /pick_and_place_node_v2 fixed_distance_m 0.30'"

# Distance caméra-cube pour la préhension
ssh robot "bash -lc 'source /home/ubuntu/ros2_ws/install/setup.bash && ros2 param set /pick_and_place_node_v2 gripper_reach 0.15'"

# Vitesse d'avance
ssh robot "bash -lc 'source /home/ubuntu/ros2_ws/install/setup.bash && ros2 param set /pick_and_place_node_v2 linear_speed 0.10'"

# Voir tous les paramètres
ssh robot "bash -lc 'source /home/ubuntu/ros2_ws/install/setup.bash && ros2 param list /pick_and_place_node_v2'"
```

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `fixed_distance_m` | 0.25 | Distance totale à avancer après centrage |
| `gripper_reach` | 0.15 | Distance caméra-cube pour déclencher la préhension |
| `linear_speed` | 0.15 | Vitesse d'avance (m/s) |
| `angular_speed` | 0.8 | Vitesse de rotation (rad/s) |
| `min_y_pixel` | 200 | Seuil Y minimum (partie basse = sol) |

---

## Étape 5 : Utiliser dans l'interface web

Une fois calibré, utilise la touche **P** dans l'interface web :
```
http://localhost:8888/robot_keypad.html
```

Ou dis simplement au robot : **"Attrape le cube rouge"**

---

## Dépannage

| Problème | Solution |
|----------|----------|
| "Je ne vois pas de cube rouge" | Vérifie la détection avec V, rapproche le cube |
| Le robot tourne dans le vide | Le cube est perdu, repositionne-le devant le robot |
| Le bras ne bouge pas | Vérifie `/voice_pick_node` : `ros2 node list \| grep voice_pick` |
| Le robot avance trop/loin | Ajuste `fixed_distance_m` avec +/- ou `ros2 param set` |
| Nœud v2 non actif | Relance : `ssh robot "bash -lc 'source /home/ubuntu/ros2_ws/install/setup.bash && nohup python3 /home/ubuntu/speech_patch/pick_and_place_node_v2.py > /tmp/pick_v2.log 2>&1 &'"` |

---

## Fichiers créés

| Fichier | Description |
|---------|-------------|
| `pick_and_place_node_v2.py` | Nœud pick-and-place sans caméra depth |
| `calibrate_pick.py` | Script de calibration interactif |
| `deploy_pick_v2.sh` | Déploiement du nœud v2 sur le robot |
| `Bureau/Calibrer Pick.bat` | Raccourci pour lancer la calibration |
