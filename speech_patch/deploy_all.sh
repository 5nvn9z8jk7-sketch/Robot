#!/bin/bash
# Déploie et lance tous les nœuds sur le robot
# Usage: bash deploy_all.sh

source /home/ubuntu/ros2_ws/install/setup.bash 2>/dev/null

echo "=== Démarrage des nœuds ==="

# 1. Moteurs
if ! ros2 node list 2>/dev/null | grep -q ros_robot_controller; then
    setsid nohup ros2 run ros_robot_controller ros_robot_controller >/tmp/rrc.log 2>&1 < /dev/null &
    disown
    echo "Moteurs: lancé"
else
    echo "Moteurs: déjà actif"
fi

# 2. Caméra depth
bash /home/ubuntu/speech_patch/start_camera.sh 2>/dev/null
sleep 3

# 3. TTS
export ASR_MODE=offline ASR_LANGUAGE=fr
if ! ros2 node list 2>/dev/null | grep -q /tts_node; then
    setsid nohup ros2 run large_models tts_node >/tmp/tts.log 2>&1 < /dev/null &
    disown
    echo "TTS: lancé"
else
    echo "TTS: déjà actif"
fi

# 4. Détection couleur
if ! ros2 node list 2>/dev/null | grep -q simple_color_detect; then
    setsid nohup python3 /home/ubuntu/speech_patch/simple_color_detect_v2.py >/tmp/color.log 2>&1 < /dev/null &
    disown
    echo "Color detect: lancé"
else
    echo "Color detect: déjà actif"
fi

# 5. Pick-and-place v5
pkill -f pick_and_place_node 2>/dev/null
sleep 1
setsid nohup python3 /home/ubuntu/speech_patch/pick_and_place_node_v5.py --ros-args -p use_depth:=true -p gripper_reach:=0.15 >/tmp/pick_v5.log 2>&1 < /dev/null &
disown
echo "Pick v5: lancé"

# 6. Mission autonome
setsid nohup python3 /home/ubuntu/speech_patch/autonomous_mission_node.py >/tmp/mission.log 2>&1 < /dev/null &
disown
echo "Mission: lancé"

# 7. Watchdog
if ! pgrep -f robot_watchdog >/dev/null 2>&1; then
    setsid nohup python3 /home/ubuntu/speech_patch/robot_watchdog.py --interval 10 >/tmp/watchdog.log 2>&1 < /dev/null &
    disown
    echo "Watchdog: lancé"
else
    echo "Watchdog: déjà actif"
fi

echo "=== Tous les nœuds sont lancés ==="
echo "Vérifie avec: ros2 node list"
