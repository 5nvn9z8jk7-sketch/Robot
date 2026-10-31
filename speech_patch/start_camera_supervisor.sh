#!/bin/bash
# Lance camera_supervisor.py (superviseur unique camera) et arrete les anciens watchdogs camera.
# Usage : bash ~/speech_patch/start_camera_supervisor.sh      (CAM_DRY_RUN=1 pour observer sans relancer)
# Option --install-boot : ajoute aussi le lancement automatique a chaque demarrage (crontab @reboot).
if [ "$1" = "--install-boot" ]; then
  (crontab -l 2>/dev/null | grep -vE 'start_camera_supervisor.sh|camera_watchdog'; echo "@reboot sleep 20 && bash /home/ubuntu/speech_patch/start_camera_supervisor.sh") | crontab -
  # Empeche l'ancien watchdog camera de revenir au demarrage
  for f in ~/start_watchdog.sh ~/start_*.sh; do [ -f "$f" ] && grep -q 'camera_watchdog' "$f" && sed -i '/camera_watchdog/s/^/# (desactive 31\/10) /' "$f" && echo "ancien watchdog camera desactive dans $f"; done
  echo "Lancement au demarrage installe (crontab -l pour verifier)"
fi
# Patterns bracketes [x] : evite le self-kill de pkill -f.
pkill -f '[c]amera_watchdog' 2>/dev/null
pkill -f '[c]amera_supervisor.py' 2>/dev/null
sleep 1
# Relance robot_watchdog avec la nouvelle version (qui ne touche plus a la camera)
if pgrep -f '[r]obot_watchdog.py' >/dev/null; then
  pkill -f '[r]obot_watchdog.py'; sleep 1
  setsid nohup bash -lc 'source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null; exec python3 -u ~/speech_patch/robot_watchdog.py --interval 10 --max-restarts 5' > /tmp/watchdog.log 2>&1 < /dev/null &
  echo "robot_watchdog relance (nouvelle version, sans gestion camera)"
fi
setsid nohup bash -lc 'source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null; source ~/third_party/aurora_ws/install/setup.bash 2>/dev/null; exec python3 -u ~/speech_patch/camera_supervisor.py' \
  > ~/camera_supervisor.out 2>&1 < /dev/null &
sleep 2
if pgrep -f '[c]amera_supervisor.py' >/dev/null; then
  echo "OK : superviseur camera lance. Suivi : tail -f ~/camera_events.log"
  echo "--- processus camera actifs ---"; ps -eo pid,etime,cmd | grep -E '[c]amera_watchdog|[c]amera_supervisor|[r]obot_watchdog|[a]urora930_node' | cut -c1-120
else
  echo "ECHEC : voir ~/camera_supervisor.out"; tail -20 ~/camera_supervisor.out
fi
