#!/bin/bash
# install_watchdog_autostart.sh — Démarre les superviseurs automatiquement au boot du robot
# À exécuter UNE SEULE FOIS sur le robot (nécessite start_watchdogs.sh déployé)

echo "=== Installation des superviseurs en autostart ==="

# Crontab @reboot — sleep 30 : laisse bringup démarrer ros_robot_controller/caméra
# avant que les superviseurs ne testent et ne relancent quoi que ce soit.
# On supprime aussi les anciennes lignes (start_watchdog.sh, camera_watchdog…)
# pour garantir UN SEUL point d'entrée au boot.
(crontab -l 2>/dev/null | grep -vE 'start_watchdog|camera_watchdog|start_camera_supervisor'
 echo "@reboot sleep 30 && bash /home/ubuntu/speech_patch/start_watchdogs.sh >> /tmp/watchdogs_boot.log 2>&1") | crontab -

echo "✅ Autostart installé :"
crontab -l | grep -E 'watchdog|supervisor'
echo ""
echo "Les superviseurs (nœuds ROS + caméra) démarreront seuls à chaque boot du robot."
