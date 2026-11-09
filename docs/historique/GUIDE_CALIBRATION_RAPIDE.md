# 🎯 Guide de calibration rapide — Pick-and-Place V5

## Problème : Le robot attrape dans le vide

**Causes possibles :**
1. Offset caméra-pince mal réglé (le bras descend à côté du cube)
2. Distance (gripper_reach) mal réglée (trop loin / trop près)
3. Centrage incorrect (le robot n'est pas bien aligné avec le cube)

---

## Étape 1 : Mesurer l'offset caméra-pince (CRITIQUE)

L'offset c'est la distance **horizontale** entre le centre de la caméra et le centre de la pince quand le bras est en position "prêt".

```
    [CAMERA] ---- offset ---- [PINCE]
         |<------ 10 cm ------>|
              (à mesurer !)
```

### Comment mesurer :
1. **Lance le robot** et mets le bras en position "prêt" (position de préhension)
2. **Mesure au mètre** la distance entre :
   - Le centre de l'objectif caméra (lentille)
   - Le centre de la pince (entre les deux doigts)
3. **Note cette valeur** (ex: 8 cm, 10 cm, 12 cm...)

### Ajuster le paramètre :
```bash
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && ros2 param set /pick_and_place_node_v5 camera_to_gripper_offset 0.08'"
```
(Remplace `0.08` par ta mesure en mètres : 8cm = 0.08m)

---

## Étape 2 : Ajuster la distance de préhension (gripper_reach)

C'est la distance **idéale entre la caméra et le cube** quand le bras descend.

### Test :
1. Place un cube à **20 cm** devant le robot (mesure avec un mètre)
2. Lance un pick : appuie sur **P** dans l'interface web
3. Observe où le bras descend :
   - **Trop loin** (le bras passe au-dessus du cube) → augmente `gripper_reach`
   - **Trop près** (le bras cogne le cube) → diminue `gripper_reach`

### Ajuster :
```bash
# Si le bras descend trop loin (ex: à 25cm au lieu de 20cm)
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && ros2 param set /pick_and_place_node_v5 gripper_reach 0.18'"

# Si le bras descend trop près (ex: à 15cm au lieu de 20cm)
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && ros2 param set /pick_and_place_node_v5 gripper_reach 0.22'"
```

---

## Étape 3 : Vérifier le centrage (alignement gauche/droite)

Si le robot bouge à gauche/droite du cube, c'est que le centrage n'est pas bon.

### Test :
1. Place un cube **exactement devant** le robot (dans l'axe)
2. Lance un pick : appuie sur **P**
3. Le robot doit :
   - ✅ Avancer **tout droit** (pas de rotation)
   - ✅ S'arrêter **face au cube**
   - ✅ Descendre le bras **sur le cube**

### Si le robot tourne à gauche/droite :
Vérifie la caméra : le cube doit apparaître au **centre horizontal** de l'image (x=320).

```bash
# Voir la position du cube en temps réel
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && ros2 topic echo /color_detect_node/color_info'"
```

Si `x` n'est pas proche de 320 quand le cube est devant, la caméra est peut-être tournée. Ajuste la caméra ou le paramètre `cx`.

---

## Étape 4 : Vérification après préhension

Le robot annonce "cube attrapé" même quand il n'a rien. Pour vérifier :

1. Après un pick, **regarde si le cube est toujours au sol**
2. Si le cube est toujours là → le bras n'a pas attrapé
3. Si le cube a disparu → c'est bon !

---

## Récapitulatif des paramètres

| Paramètre | Défaut | Description | Ajustement |
|-----------|--------|-------------|------------|
| `camera_to_gripper_offset` | 0.10 | Distance caméra→pince (m) | Mesure physique |
| `gripper_reach` | 0.15 | Distance caméra→cube idéale (m) | Test et ajuster |
| `target_size_px` | 80 | Taille cible du cube (pixels) | Selon la distance |
| `linear_speed` | 0.12 | Vitesse d'avance (m/s) | Ralentir si imprécis |
| `angular_speed` | 0.6 | Vitesse de rotation (rad/s) | Ralentir si imprécis |

---

## Commandes rapides

```bash
# Voir tous les paramètres actuels
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && ros2 param list /pick_and_place_node_v5'"

# Voir un paramètre spécifique
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && ros2 param get /pick_and_place_node_v5 camera_to_gripper_offset'"

# Modifier un paramètre
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && ros2 param set /pick_and_place_node_v5 camera_to_gripper_offset 0.08'"

# Redémarrer le pick-and-place après modification
ssh robot "pkill -f pick_and_place_node; sleep 1; bash -lc 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && setsid nohup python3 /home/ubuntu/speech_patch/pick_and_place_node_v5.py --ros-args -p use_depth:=true -p gripper_reach:=0.15 -p camera_to_gripper_offset:=0.10 -p min_y_pixel:=0 >/tmp/pick_v5.log 2>&1 < /dev/null & disown'"
```

---

## Procédure de calibration complète

1. **Mesure** l'offset caméra-pince avec un mètre
2. **Règle** `camera_to_gripper_offset` à cette valeur
3. **Place** un cube à 20 cm devant le robot
4. **Lance** un test pick (touche P)
5. **Observe** où le bras descend
6. **Ajuste** `gripper_reach` jusqu'à ce que le bras descende exactement sur le cube
7. **Répète** les étapes 3-6 jusqu'à ce que le robot attrape le cube
8. **Teste** avec le cube à différentes positions (gauche, droite, plus loin, plus près)
