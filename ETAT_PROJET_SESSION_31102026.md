# Session 31/10 → 01/11/2026 : stabilité caméra (EN COURS, pause pour recharge batterie)

## Diagnostic (diag_camera.sh, 01/11 04:31)

- **Cause matérielle confirmée.** La caméra Aurora 930 (USB `3251:1930`) se déconnecte réellement du bus :
  - les messages système montrent des erreurs `-71` en rafale (descriptor read, not accepting address, unable to enumerate) ;
  - la caméra portait le numéro de périphérique 42 après 40 min d'allumage, soit environ 35 reconnexions.
- **Branchement actuel** : port `1-2.2.1`, en USB 2 (480M). La caméra passe derrière **deux hubs en cascade** (Terminus `1-2` puis QinHeng `1-2.2`) et partage ce chemin avec une carte série CH340. Le **bus USB 3 (bus 2, 10 Gbit/s) est vide**.
- **Ce qui aggravait la situation** : deux anciens watchdogs tournaient en même temps (`camera_watchdog_v2.sh` et l'ancien `robot_watchdog.py`). On compte 109 relances au total. Chaque relance faisait un unbind/bind USB.
- **Hors de cause** :
  - la veille USB (`power/control=on`) ;
  - la température (~70 °C) ;
  - le mode puissance (MAXN_SUPER) ;
  - l'alimentation (~10 W).

## Fait

- `camera_supervisor.py` est le superviseur unique. Il est abonné en permanence, détecte les images gelées, retrouve le port USB tout seul par son identifiant, et note chaque panne dans `~/camera_events.log`.
- `robot_watchdog.py` ne gère plus la caméra. Pour réactiver l'ancien comportement : `WATCHDOG_MANAGE_CAMERA=1`.
- `start_camera_supervisor.sh --install-boot` est **déployé et lancé sur le robot** :
  - il ajoute un lancement au démarrage (`@reboot`) dans crontab ;
  - il désactive `camera_watchdog` dans `~/start_*.sh`.
- **Premier résultat** : 4374 images en 5 min (~15 i/s), 0 image gelée, 0 relance. Le superviseur a redémarré à 04:42 (redémarrage du robot ?).

## Reste à faire

1. **Matériel** : brancher la caméra directement sur la Jetson, de préférence sur le port USB 3 bleu, sans les hubs. Vérifier le câble (bien enfoncé, ne tire pas quand le bras bouge). L'utilisateur n'a pas encore dit s'il l'a fait.
2. Après 30 min d'utilisation : `ssh ubuntu@192.168.1.30 "uptime; tail -8 ~/camera_events.log; bash ~/speech_patch/diag_camera.sh | grep -A6 -E 'Port camera|Erreurs USB'"`
   - **Objectif** : plus d'erreur `-71`, numéro de périphérique stable, 0 relance.
3. **Accès distant pour l'agent (en cours)** :
   - le PC Windows DESKTOP-5DGQBOF (Tailscale 100.119.69.0) n'est plus accessible à l'agent : l'accès local de l'app Perplexity est cassé, peut-être bloqué par Norton ;
   - le robot n'est **pas encore** sur Tailscale. Commande à lancer :
     `ssh -t ubuntu@192.168.1.30 "curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up && tailscale ip -4"`
   - une clé SSH de l'agent (`perplexity-sandbox`) a été proposée pour `~/.ssh/authorized_keys` du robot. L'utilisateur n'a pas confirmé `CLE_OK`. L'environnement de l'agent est temporaire, il faudra regénérer une clé à la reprise ;
   - retirer l'appareil « perplexity-sandbox » de la console Tailscale si on ne l'utilise plus.
4. Ensuite : dépose du cube dans le bac (cycle complet).

## Notes

- Le dépôt GitHub `Robot` a été **passé en public** le 31/10 pour que le robot puisse faire `git clone`.
- L'horloge du robot est en CST (fuseau chinois, locale chinoise dans les logs).
- Le 31/10 à 21:35, l'utilisateur a fusionné sa version locale de `robot_watchdog.py` (commit 64672f7). Elle corrige `_run_cmd` en passant par `bash -c` (avec `/bin/sh`, `source` échouait et tous les nœuds étaient relancés en boucle) et ne gère plus la caméra non plus. **Le robot tourne encore l'ancienne version** (déployée avant la fusion) : il faut la redéployer à la reprise. Il suffit de relancer la commande `git clone` + `cp` + `start_camera_supervisor.sh --install-boot`.
