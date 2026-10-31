#!/bin/bash
# Lance camera_supervisor.py (superviseur unique camera) et arrete les anciens watchdogs camera.
# Usage : bash ~/speech_patch/start_camera_supervisor.sh      (CAM_DRY_RUN=1 pour observer sans relancer)
# Option --install-boot : ajoute aussi le lancement automatique a chaque demarrage (crontab @reboot).
if [ "$1" = "--install-boot" ]; then
  (crontab -l 2>/dev/null | grep -vE 'start_camera_supervisor.sh|camera_watchdog'; echo "@reboot sleep 20 && bash /home/ubuntu/speech_patch/start_camera_supervisor.sh") | crontab -
  echo "Lancement au demarrage installe (crontab -l pour verifier)"
fi
# Patterns bracketes [x] : evite le self-kill de pkill -f.
pkill -f '[c]amera_watchdog' 2>/dev/null
pkill -f '[c]amera_supervisor.py' 2>/dev/null
sleep 1
setsid nohup bash -lc 'source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null; source ~/third_party/aurora_ws/install/setup.bash 2>/dev/null; exec python3 -u ~/speech_patch/camera_supervisor.py' \
  > ~/camera_supervisor.out 2>&1 < /dev/null &
sleep 2
if pgrep -f '[c]amera_supervisor.py' >/dev/null; then
  echo "OK : superviseur camera lance. Suivi : tail -f ~/camera_events.log"
else
  echo "ECHEC : voir ~/camera_supervisor.out"; tail -20 ~/camera_supervisor.out
fi
