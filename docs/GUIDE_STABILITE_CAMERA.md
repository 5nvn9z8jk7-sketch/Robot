# Stabilité caméra aurora930 — session 31/10/2026

## Le problème

Depuis le 30/10, la caméra plante environ une fois par minute. Elle est relancée en 25 s environ (`wdt_count:75`).

## Ce qu'on a trouvé dans le code (piste logicielle, la plus probable)

1. **`robot_watchdog.py` relançait ENCORE la caméra.** La note du 30/10 disait le contraire.
   Ce bloc teste `/depth_cam/depth0/image_raw` avec `timeout 2 ros2 topic hz`.
   Sur la Jetson, il faut souvent plus de 2 s rien que pour démarrer le CLI ros2 et trouver le topic.
   → Le test échoue alors que la caméra marche. Au bout de 60 s, il fait `pkill -9` sur la caméra.
   **Cela correspond au rythme d'un plantage par minute.**
2. **`camera_watchdog_v2.sh` a le même défaut** (`timeout 4`). En plus, il fait un reset USB à chaque fausse alerte.
3. **Deux watchdogs relancent la caméra en même temps** : ils peuvent se gêner (périphérique USB occupé, relances l'une sur l'autre).

## Les correctifs

| Fichier | Changement |
|---|---|
| `speech_patch/robot_watchdog.py` | Ne touche plus à la caméra. Pour réactiver l'ancien comportement : `WATCHDOG_MANAGE_CAMERA=1` |
| `speech_patch/camera_supervisor.py` | **NOUVEAU** superviseur unique. Il reste abonné en permanence, sans relancer le CLI ros2. Il détecte aussi les images gelées. Il ne relance qu'après 8 s sans image, avec 30 s de grâce après une relance. Il ne fait un reset USB qu'au 2e échec consécutif. Il note chaque panne et un extrait de dmesg dans `~/camera_events.log` |
| `speech_patch/start_camera_supervisor.sh` | Arrête les anciens `camera_watchdog*` et lance le superviseur. `--install-boot` le lance aussi à chaque démarrage |
| `speech_patch/diag_camera.sh` | Diagnostic en **lecture seule** : arbre USB, vitesse du port, veille USB, erreurs dmesg, nombre de relances, mode puissance, températures |
| `speech_patch/fix_usb_autosuspend.sh` | Désactive la veille USB. À lancer seulement si le diagnostic montre `power/control = auto` |

## Procédure (sur le PC, PowerShell)

```powershell
# 0. Récupérer les fichiers puis les copier sur le robot
git pull
scp speech_patch/camera_supervisor.py speech_patch/start_camera_supervisor.sh speech_patch/diag_camera.sh speech_patch/fix_usb_autosuspend.sh speech_patch/robot_watchdog.py robot:/home/ubuntu/speech_patch/

# 1. Photo de l'état actuel (AVANT le changement)
ssh robot "bash ~/speech_patch/diag_camera.sh"

# 2. Relancer robot_watchdog (nouvelle version, sans la caméra)
ssh robot "pkill -f '[r]obot_watchdog.py'; setsid nohup bash -lc 'python3 -u ~/speech_patch/robot_watchdog.py --interval 10 --max-restarts 5' > /tmp/watchdog.log 2>&1 < /dev/null &"

# 3. Lancer le superviseur caméra, avec lancement automatique à chaque démarrage
ssh robot "bash ~/speech_patch/start_camera_supervisor.sh --install-boot"

# 4. Laisser tourner 15-30 min (faire quelques picks), puis :
ssh robot "tail -40 ~/camera_events.log"
```

## Lecture du résultat

- **Aucune « PANNE » dans `camera_events.log`** : c'était bien les watchdogs. Problème réglé.
- **Des pannes avec `process driver=MORT`** : le driver plante tout seul. Lire la fin de `aurora.log` dans l'événement.
- **Des pannes avec `disconnect` / `reset` / `-71` / `-110` dans dmesg** : problème **matériel**. Le câble USB, le hub ou l'alimentation sont en cause :
  - brancher la caméra **directement** sur la Jetson. Aujourd'hui elle passe par le hub `1-2.2`. Utiliser un port USB 3 si possible ;
  - changer le câble pour un câble court et blindé ;
  - tester avec la batterie bien chargée. Les servos qui forcent font chuter la tension ;
  - si `power/control = auto` : `ssh robot "bash ~/speech_patch/fix_usb_autosuspend.sh"`.
- **Un test sans risque** : `CAM_DRY_RUN=1 bash ~/speech_patch/start_camera_supervisor.sh` note les pannes sans jamais relancer la caméra. Si la caméra ne plante plus quand personne ne la relance, la cause est confirmée.

## Note

Si la caméra passe sur un autre port USB, son adresse change. Il faut alors donner le nouveau port au superviseur, par exemple `CAM_USB_PORT=1-2.1` (voir `lsusb -t`).
