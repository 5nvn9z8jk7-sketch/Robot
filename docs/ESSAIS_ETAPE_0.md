# Étape 0 — Essais sur le robot

À faire dans l'ordre. **Au premier résultat anormal : on s'arrête, on note ce qui s'est passé, on ne continue pas.**

Toutes les commandes se tapent dans PowerShell sur le PC. `ssh robot` doit fonctionner (réseau local ou Tailscale).

Pendant tous les essais : robot au sol, 1 m de place libre autour, une main prête sur ESPACE dans le keypad.

---

## E0 — Relevé de départ (lecture seule, ne bouge rien)

```powershell
ssh robot "curl -fsSL https://raw.githubusercontent.com/5nvn9z8jk7-sketch/Robot/etape-0-menage/speech_patch/verif_etat_robot.sh | bash" > $env:TEMP\verif_robot.txt
```

Le relevé est enregistré dans `verif_robot.txt` (dossier temporaire du PC). Il sert de point de comparaison.

## E1 — Installation des 2 fichiers corrigés

```powershell
ssh robot "curl -fsSL https://raw.githubusercontent.com/5nvn9z8jk7-sketch/Robot/etape-0-menage/speech_patch/maj_etape0.sh | bash"
```

Attendu : `processus pick v6 en cours : 1`. Le script affiche aussi les commandes de retour arrière.

Sur le PC, dans le dossier local du projet : `git fetch` puis `git checkout etape-0-menage` (pour avoir le nouveau keypad et le nouveau `start_interface.bat`).

## E2 — Interface

Lancer `start_interface.bat`.
- Attendu : « Nœud moteurs actif » (et plus jamais « actif » quand il ne l'est pas).
- Touche **O** : le journal affiche « Pince : pas encore disponible ».

## E3 — Arrêt d'urgence pendant une saisie

1. Cube rouge posé à ~50 cm devant le robot.
2. Touche **P**. Dès que le robot commence à avancer : **ESPACE**.
3. Attendu : roues arrêtées en moins d'1 seconde, le robot dit « Arrêt », et dans le journal :
   ```powershell
   ssh robot "grep -a 'ARRET' /tmp/pick_v6.log | tail -3"
   ```
4. Recommencer avec la voix : dire « stop » pendant l'approche.
5. Recommencer une fois pendant la descente du bras (le bras doit s'immobiliser, pas finir sa séquence).

## E4 — Rotation en boucle odométrie

1. Cube à ~50 cm, décalé d'environ 30 cm vers la gauche.
2. Touche **P**, laisser faire jusqu'au bout.
3. Attendu : le robot se centre en 1 à 3 rotations sans osciller, puis attrape.
   ```powershell
   ssh robot "grep -a 'Rotation' /tmp/pick_v6.log | tail -5"
   ```
   Les lignes doivent indiquer `(boucle odom)`, pas `(chrono, odom absente)`.

## E5 — Déclencheurs (sans micro, phrases envoyées directement)

Pour chaque phrase, envoyer la commande puis regarder si le pick démarre. Remplacer `PHRASE` (sans guillemets supplémentaires), par exemple `'data: attrape le cube rouge'` :

```powershell
ssh robot "source /opt/ros/humble/setup.bash && ros2 topic pub --once /vocal_detect/asr_result std_msgs/msg/String 'data: PHRASE'"
```

| Phrase | Attendu |
|---|---|
| `attrape le cube rouge` | le pick démarre (« Je cherche le cube rouge ») |
| `trouve la balle rouge` | rien ne bouge |
| `regarde le cube` | rien ne bouge |
| `attrape tous les cubes` | le pick ne démarre PAS (c'est la mission qui répond). **Envoyer `stop` juste après** : la mission n'est pas encore fiable (étape 3). |

## E6 — Redémarrage complet

1. Éteindre puis rallumer le robot. Attendre 3 minutes.
2. Refaire le relevé E0 (dans un autre fichier) :
   ```powershell
   ssh robot "curl -fsSL https://raw.githubusercontent.com/5nvn9z8jk7-sketch/Robot/etape-0-menage/speech_patch/verif_etat_robot.sh | bash" > $env:TEMP\verif_robot_reboot.txt
   ```
3. Attendu : 1 seul `robot_watchdog`, 1 seul `camera_supervisor`, 1 seul `pick_and_place_node_v6`, 0 `voice_pick_node`, 0 ancien pick (v1 à v5).

---

## Si tout est bon

On fusionne la branche `etape-0-menage` dans `main` (ce qui fusionne aussi la PR #3), puis on passe à l'étape 1 (arrêt global + anti-collision lidar).
