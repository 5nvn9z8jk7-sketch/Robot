#!/bin/bash
source /opt/ros/humble/setup.bash 2>/dev/null
source ~/ros2_ws/install/setup.bash 2>/dev/null
source ~/third_party/third_party_ws/install/setup.bash 2>/dev/null
source ~/third_party/aurora_ws/install/setup.bash 2>/dev/null
export SPEECH_LANG=fr
export SPEECH_FORCE_FR=1
pkill -f pick_and_place_node 2>/dev/null
sleep 1
nohup python3 -u /home/ubuntu/speech_patch/pick_and_place_node_v6.py > ~/pick_and_place.log 2>&1 &
echo "pick_and_place_node PID=$!"
