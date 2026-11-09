# 🤖 Pick-and-Place V3 — Scan 360° + Positionnement Intelligent

## Nouveautés par rapport à v2

| Fonction | v2 | v3 |
|----------|----|----|
| Détection cube | Face caméra uniquement | **Scan 360°** (tourne par paliers de 30°) |
| Distance | Fixe (calibrée manuellement) | **Auto-ajustée** par taille apparente du cube |
| Position | Avance une seule fois | **Avance/Recule** jusqu'à la bonne distance |
| Directions | Cube devant uniquement | **N'importe où autour du robot** |
| Précision | ±5 cm | **±2 cm** (tolérance 15% sur la taille) |

---

## Comment ça marche

```
1. SCAN 360°          Le robot tourne par paliers de 30°
    🔍                jusqu'à voir un cube rouge
         ↓
2. CENTRAGE           Le robot tourne pour mettre le cube
    🎯                au centre de sa caméra
         ↓
3. AJUSTEMENT         Le robot avance/recule selon la taille
    📏                du cube dans l'image:
                      • Cube trop petit = loin → AVANCE
                      • Cube trop grand = proche → RECULE
         ↓
4. PRÉHENSION         Le bras attrape le cube
    🤏
```

### Estimation de distance par taille

Sans caméra depth, le robot estime la distance par la **taille du cube dans l'image** :

| Taille cube (pixels) | Distance estimée |
|----------------------|------------------|
| 20 px | ~1.0 m (trop loin) |
| 40 px | ~0.5 m |
| **80 px** | **~0.25 m (cible)** |
| 120 px | ~0.17 m |
| 200 px | ~0.10 m (trop proche) |

> Le paramètre `target_size_px` définit la taille cible. Plus elle est grande, plus le robot s'arrête près du cube.

---

## Commandes vocales

| Dire | Action |
|------|--------|
| **"Attrape le cube rouge"** | Détection directe (cube devant) |
| **"Cherche le cube rouge"** | Scan 360° puis attrape |
| **"Va chercher le cube"** | Scan 360° puis attrape |
| **"Cherche autour de toi"** | Scan 360° puis attrape |

---

## Interface web

Deux boutons pour le pick-and-place :

| Bouton | Touche | Action |
|--------|--------|--------|
| 🔍 **CHERCHE (360°)** | **C** | Scan 360° + attrape |
| 🤏 **ATTRAPE (direct)** | **P** | Détection directe (cube devant) |

Le slider **"Taille cible cube"** ajuste `target_size_px` :
- Plus la valeur est **grande** → le robot s'arrête **plus près** du cube
- Plus la valeur est **petite** → le robot s'arrête **plus loin** du cube

---

## Déploiement (après recharge du robot)

```bash
cd C:\Users\bloiz\projets\Robot\speech_patch
bash deploy_pick_v3.sh
```

Ou manuellement :
```bash
# Transférer
scp pick_and_place_node_v3.py robot:/home/ubuntu/speech_patch/

# Sur le robot
ssh robot "bash -c '
source /home/ubuntu/ros2_ws/install/setup.bash
pkill -f pick_and_place_node 2>/dev/null
nohup python3 /home/ubuntu/speech_patch/pick_and_place_node_v3.py \
  --ros-args -p target_size_px:=80 -p gripper_reach:=0.18 \
  > /tmp/pick_v3.log 2>&1 &
'"
```

---

## Paramètres ajustables

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `target_size_px` | 80 | Taille cible du cube en pixels (~distance de préhension) |
| `gripper_reach` | 0.18 | Distance caméra-cube idéale (m) |
| `linear_speed` | 0.12 | Vitesse avance/recule (m/s) |
| `angular_speed` | 0.6 | Vitesse rotation (rad/s) |
| `scan_step_deg` | 30 | Angle de scan par palier (degrés) |
| `min_y_pixel` | 200 | Seuil Y minimum (partie basse = sol) |
| `size_tolerance` | 0.15 | Tolérance sur la taille (15%) |

Ajuster en temps réel :
```bash
ssh robot "bash -c 'source /home/ubuntu/ros2_ws/install/setup.bash && ros2 param set /pick_and_place_node_v3 target_size_px 100'"
```

---

## Calibration recommandée

1. **Place un cube rouge** à ~25 cm devant le robot
2. **Lance** : `"Cherche le cube rouge"`
3. **Observe** la taille détectée dans les logs : `ssh robot "tail -f /tmp/pick_v3.log"`
4. **Ajuste** `target_size_px` pour que le robot s'arrête à la bonne distance
5. **Teste** avec le cube à différentes positions (devant, côté, derrière)

---

## Dépannage

| Problème | Solution |
|----------|----------|
| Le robot tourne sans s'arrêter | Aucun cube rouge détecté → vérifie la détection couleur |
| Le robot avance trop loin | `target_size_px` trop petit → augmente-le |
| Le robot recule trop | `target_size_px` trop grand → diminue-le |
| Le bras ne touche pas le cube | `gripper_reach` mal réglé → ajuste `target_size_px` |
| Le robot perd le cube en tournant | `angular_speed` trop rapide → ralentis à 0.4 |
