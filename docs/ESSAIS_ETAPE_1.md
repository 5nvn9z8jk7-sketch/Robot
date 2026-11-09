# Étape 1 — Essais du gardien de sécurité

**Au premier résultat anormal : ESPACE, on s'arrête, on note, on ne continue pas.**

Commandes dans l'Invite de commandes (`cmd`), depuis `C:\Users\bloiz\projets\Robot`. Copier seulement les lignes qui commencent par `ssh`, `scp`, `git`, `cd`.

Robot au sol, 1,5 m libre devant, une main sur ESPACE.

## Ce qui change

- Nos programmes (keypad, pick, mission, pont vocal) ne pilotent plus les roues directement : tout passe par `gardien_securite.py`.
- **ESPACE, 0, 5 et le mot « stop » verrouillent l'arrêt général.** Le robot dit « Arrêt général » et ne bouge plus jusqu'à **Entrée** (ou bouton REPRENDRE, ou le mot « reprends »).
- Obstacle dans le sens de marche (avant ou côtés) : ralenti à partir de 0,60 m, arrêt à 0,30 m (distances mesurées depuis le lidar, au centre du robot).
- Marche arrière : l'arrière n'est pas vu par le lidar → 0,10 m/s au plus, 5 s d'affilée au plus.
- Nouveau badge « Sécurité » sur la page.

## F1 — Installation

```bat
git fetch
git checkout etape-1-securite
git pull
scp speech_patch\maj_etape1.sh robot:/tmp/
ssh robot "sed -i 's/\r$//' /tmp/maj_etape1.sh && bash /tmp/maj_etape1.sh"
```

Attendu : `1 processus` pour les 4 programmes, et dans « Qui publie » la ligne `gardien_securite` (et plus `pick_and_place_node_v6`, `autonomous_mission_node`, `llm_move_bridge`).

Puis relancer `speech_patch\start_interface.bat` et recharger la page avec **Ctrl+F5**. Badge attendu : « Sécurité: OK ».

## F2 — Déplacements manuels

Z, Q, S, D, A, E : le robot bouge comme avant. S (recul) est plus lent : normal.

## F3 — Arrêt général verrouillé

1. Maintenir Z (avance), puis ESPACE → arrêt, « Arrêt général », badge rouge.
2. Z → **ne bouge pas**.
3. Entrée → « Je reprends », badge vert ; Z → bouge.
4. Même chose avec le mot « stop » puis « reprends » envoyés à la main :
   ```bat
   ssh robot "source /opt/ros/humble/setup.zsh && ros2 topic pub --once -w 3 /vocal_detect/asr_result std_msgs/msg/String 'data: stop'"
   ssh robot "source /opt/ros/humble/setup.zsh && ros2 topic pub --once -w 3 /vocal_detect/asr_result std_msgs/msg/String 'data: reprends'"
   ```

## F4 — Obstacle devant

1. Carton posé à ~1 m devant le robot.
2. Z par appuis successifs (chaque appui = 2 s d'avance).
3. Attendu : le robot ralentit à l'approche et **s'arrête de lui-même**, dit « Obstacle », badge orange.
4. Mesurer au mètre la distance entre l'**avant du robot** et le carton : ______ cm (sert à régler le seuil).
5. Q/D (rotation) doivent rester possibles ; S permet de reculer.

## F5 — Obstacle sur le côté (crabe)

Carton à ~50 cm à gauche, touche A (crabe gauche) : arrêt avant le carton. Z (avance) reste possible.

## F6 — Pick toujours fonctionnel

Cube à ~50 cm, **P** : le robot doit attraper le cube comme avant (le cube est plus bas que le lidar, il n'est pas vu comme obstacle). Puis refaire P et ESPACE pendant l'approche : arrêt.

## F7 — Refus pendant l'arrêt

ESPACE (verrou), puis P → le robot dit « Arrêt général actif. Dis reprends d'abord. » et ne bouge pas. Entrée pour reprendre.

## F8 — Redémarrage

Éteindre, rallumer, attendre 3 min, refaire le relevé :
```bat
scp speech_patch\verif_etat_robot.sh robot:/tmp/
ssh robot "sed -i 's/\r$//' /tmp/verif_etat_robot.sh && bash /tmp/verif_etat_robot.sh" > %TEMP%\verif_robot_etape1.txt
```
Attendu : `gardien_securite` présent et seul de nos programmes à publier sur `/controller/cmd_vel`.

## Limites connues (assumées)

- Le cube (plus bas que le lidar) et tout objet bas ne sont pas vus comme obstacles : la caméra de profondeur sera ajoutée plus tard.
- Les 5 programmes Hiwonder (`self_driving`, `joystick_control`, `lidar_app`, `line_following`, `object_tracking`) publient encore directement sur les roues ; ils sont inactifs tant qu'on ne lance pas leurs modes depuis l'application Hiwonder. Pendant un arrêt général, le gardien les contre en publiant des zéros à 20 Hz.
- Le bras n'est pas bloqué par le gardien : seul le pick l'interrompt (validé à l'étape 0).
