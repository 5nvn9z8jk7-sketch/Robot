#!/bin/bash
# start_watchdogs.sh — Lance les 2 superviseurs détachés de la session ssh (setsid)
# Usage: bash /home/ubuntu/speech_patch/start_watchdogs.sh  (idempotent, appelable au boot)
# - robot_watchdog.py    : nœuds ROS (relance ros_robot_controller, v6, v3, rosbridge…)
# - camera_supervisor.py : caméra aurora930 (remplace camera_watchdog_v2.sh)

# Arrêt des anciens watchdogs — pattern bracketé obligatoire (évite le self-kill)
pkill -f '[r]obot_watchdog.py' 2>/dev/null
pkill -f '[c]amera_watchdog' 2>/dev/null
pkill -f '[c]amera_supervisor.py' 2>/dev/null
sleep 1

# Watchdog nœuds ROS
setsid nohup bash -lc 'source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null; exec python3 -u /home/ubuntu/speech_patch/robot_watchdog.py --interval 10 --max-restarts 5' \
  > /tmp/watchdog.log 2>&1 < /dev/null &

# Superviseur caméra (relance driver + reset USB si le flux meurt)
setsid nohup bash -lc 'source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null; source ~/third_party/aurora_ws/install/setup.bash 2>/dev/null; exec python3 -u /home/ubuntu/speech_patch/camera_supervisor.py' \
  > ~/camera_supervisor.out 2>&1 < /dev/null &

sleep 2
echo "Superviseurs lancés :"
echo "  robot_watchdog    PID $(pgrep -f '[r]obot_watchdog.py' | tr '\n' ' ')"
echo "  camera_supervisor PID $(pgrep -f '[c]amera_supervisor.py' | tr '\n' ' ')"
echo "Logs: /tmp/watchdog.log  ~/camera_events.log"
