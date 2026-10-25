# 📋 SESSION 25/10/2026 — Reprise projet, corrections pick-and-place, calibration

## Résumé exécutif

Session de debug et correction du pick-and-place v5. Le robot n'arrivait pas à attraper le cube (attrapait dans le vide). **2 bugs majeurs corrigés** + création d'outils de calibration.

---

## 🐛 Bugs corrigés

### 1. Filtre `min_y_pixel=100` rejetait tous les cubes
- **Symptôme** : Logs `Filtre: 1 objets, min_y=100, premier y=56 -> rejete=True`
- **Cause** : Le filtre exigeait que le cube soit dans la partie basse de l'image (y >= 100), mais le cube était à y=54-56
- **Correction** : `DEFAULT_MIN_Y_PIXEL = 100` → `0` dans `pick_and_place_node_v5.py` ligne 58

### 2. Crash au shutdown (`rclpy.shutdown already called`)
- **Symptôme** : `RCLError: failed to shutdown: rcl_shutdown already called`
- **Cause** : Quand le nœud est tué (pkill/SIGTERM), `ExternalShutdownException` n'est pas capturée, puis `rclpy.shutdown()` est appelé 2 fois
- **Correction** : Ajout `try/except` autour de `rclpy.shutdown()` dans :
  - `pick_and_place_node_v5.py` (ligne ~510)
  - `simple_color_detect_v2.py`
  - `autonomous_mission_node.py`

---

## 🔧 État actuel du robot (192.168.1.30)

### Nœuds actifs
```
/pick_and_place_node_v5    ✅ (corrigé, ne crash plus)
/simple_color_detect       ✅ (détecte cube rouge, publie /color_detect_node/color_info)
/autonomous_mission_node   ✅
/robot_watchdog            ✅ (PID 9315)
/tts_node                  ✅
/ros_robot_controller      ✅ (moteurs)
/aurora                    ✅ (caméra depth)
/llm_move_bridge           ✅
```

### Détection couleur (test OK)
```
color: red
x: 338, y: 140  (centre image = 320, 200)
width: 50, height: 54, radius: 27
```

### Paramètres pick-and-place v5 (à calibrer)
| Paramètre | Valeur actuelle | Description |
|-----------|-----------------|-------------|
| `camera_to_gripper_offset` | 0.10 m (10 cm) | **À MESURER** distance caméra→pince |
| `gripper_reach` | 0.15 m (15 cm) | Distance caméra→cube idéale |
| `target_size_px` | 80 px | Taille cible du cube |
| `min_y_pixel` | 0 (corrigé) | Filtre Y (0 = accepte tout) |
| `linear_speed` | 0.10 m/s | Vitesse avance |
| `angular_speed` | 0.5 rad/s | Vitesse rotation |
| `use_depth` | true | Utilise caméra depth |

---

## 🎯 Problème en cours : Calibration pick-and-place

**Symptôme** : Le robot bouge à droite/gauche du cube, descend le bras dans le vide, annonce "cube attrapé" alors que non.

**Cause probable** : `camera_to_gripper_offset` mal calibré (distance caméra-pince inconnue).

### Procédure de calibration (voir GUIDE_CALIBRATION_RAPIDE.md)

1. **Mesurer** la distance caméra→pince au mètre (bras en position prêt)
2. **Appliquer** : `ros2 param set /pick_and_place_node_v5 camera_to_gripper_offset <valeur>`
3. **Tester** avec cube à 20 cm, ajuster `gripper_reach`
4. **Vérifier** le centrage (cube à x=320 quand devant le robot)

### Commandes utiles
```bash
# Voir position cube en temps réel
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && ros2 topic echo /color_detect_node/color_info'"

# Modifier un paramètre
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && ros2 param set /pick_and_place_node_v5 camera_to_gripper_offset 0.08'"

# Redémarrer pick-and-place (avec nouveaux paramètres)
ssh robot "pkill -f pick_and_place_node; sleep 1; bash -lc 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && setsid nohup python3 /home/ubuntu/speech_patch/pick_and_place_node_v5.py --ros-args -p use_depth:=true -p min_y_pixel:=0 >/tmp/pick_v5.log 2>&1 < /dev/null & disown'"

# Voir les logs
ssh robot "tail -f /tmp/pick_v5.log"
```

---

## 🖥️ Interface Web et raccourcis Bureau

### Raccourcis sur le Bureau (C:\Users\bloiz\OneDrive\Desktop)
| Fichier | Description |
|---------|-------------|
| `Deployer Robot.lnk` | Transfère fichiers + lance nœuds (deploy_all.sh) |
| `Interface Web.lnk` | Lance serveur web (python -m http.server 8888) |
| `Robot Interface Web.url` | Ouvre http://localhost:8888/robot_keypad.html |
| `Calibrer Pick.bat` | Calibration interactive (ancien) |

### Adresse interface web
**http://localhost:8888/robot_keypad.html**

### Commandes clavier
| Touche | Action |
|--------|--------|
| ZQSD / flèches | Déplacer |
| ESPACE | Stop urgence |
| P | Attrape cube (direct) |
| C | Scan 360° + attrape |
| M | Mission autonome (tous les cubes) |
| R | Patrouille 2 min |
| B | Retour base |
| S | Status vocal |

---

## 📁 Fichiers créés/modifiés cette session

### Modifiés (corrections bugs)
- `speech_patch/pick_and_place_node_v5.py` — fix shutdown + min_y_pixel=0
- `speech_patch/simple_color_detect_v2.py` — fix shutdown
- `speech_patch/autonomous_mission_node.py` — fix shutdown
- `speech_patch/voice_bridge.py` — inversion vitesses (session précédente)
- `speech_patch/start_depth_camera.sh` — refonte (session précédente)

### Nouveaux fichiers
- `speech_patch/deploy_all.sh` — Script déploiement tout-en-un (résout les blocages SSH)
- `speech_patch/calibrate_pick_v5.py` — Calibration interactive WebSocket
- `speech_patch/robot_params_backup.txt` — Backup paramètres robot
- `GUIDE_CALIBRATION_RAPIDE.md` — Guide calibration pick-and-place
- `GUIDE_AUTONOME_COMPLET.md` — Doc système autonome complet
- `GUIDE_CALIBRATION_PICK.md` — Doc calibration (ancien)
- `GUIDE_PICK_V3.md` — Doc pick-and-place v3

### Raccourcis Bureau (OneDrive/Desktop)
- `Deployer Robot.bat` / `.lnk`
- `Interface Web.bat` / `.lnk`
- `Robot Interface Web.url`

---

## 🚀 Pour reprendre la prochaine fois

### 1. Vérifier que le robot est allumé
```bash
ping 192.168.1.30
ssh robot "echo OK"
```

### 2. Lancer les nœuds (si pas déjà fait)
Double-clic sur **Deployer Robot.lnk** sur le Bureau

### 3. Ouvrir l'interface web
Double-clic sur **Robot Interface Web.url** sur le Bureau
→ http://localhost:8888/robot_keypad.html

### 4. Continuer la calibration pick-and-place
Suivre **GUIDE_CALIBRATION_RAPIDE.md** :
1. Mesurer offset caméra-pince
2. Ajuster `camera_to_gripper_offset`
3. Tester avec cube à 20 cm
4. Ajuster `gripper_reach`

### 5. Commandes rapides SSH
```bash
# État des nœuds
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && ros2 node list'"

# Logs pick-and-place
ssh robot "tail -f /tmp/pick_v5.log"

# Détection couleur
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && ros2 topic echo /color_detect_node/color_info --once'"

# Test mouvement manuel
python3 speech_patch/voice_bridge.py "Avance"
```

---

## 📊 Architecture du système

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   PC (Windows)  │────▶│  Ollama LLM     │────▶│  Interprétation  │
│  Interface Web  │     │  (192.168.1.20) │     │  commandes FR   │
│  localhost:8888 │     └─────────────────┘     └─────────────────┘
└─────────────────┘              │
                                 ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Robot (ARM)    │◀────│  rosbridge WS   │◀────│  voice_bridge   │
│  192.168.1.30   │     │  (port 9090)    │     │  (PC ou robot)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │
        ├── /ros_robot_controller  (moteurs)
        ├── /aurora                 (caméra depth)
        ├── /simple_color_detect    (détection cube rouge)
        ├── /pick_and_place_node_v5 (pick-and-place)
        ├── /autonomous_mission_node (mission multi-cubes)
        ├── /robot_watchdog         (auto-réparation)
        ├── /tts_node               (synthèse vocale)
        └── /gripper_controller     (bras/pince)
```

---

## ⚠️ Points d'attention

1. **Toujours sourcer ROS2** : `source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash`
2. **Paramètres non persistants** : Les `ros2 param set` sont perdus au redémarrage du nœud. Soit modifier le code, soit passer les params en ligne de commande.
3. **Ne pas lancer plusieurs fois** le même nœud (tuer avant : `pkill -f nom_du_noeud`)
4. **Le Bureau est sur OneDrive** : `C:\Users\bloiz\OneDrive\Desktop` (pas `C:\Users\bloiz\Desktop`)
