#!/bin/bash
source /opt/ros/humble/setup.bash 2>/dev/null
source ~/ros2_ws/install/setup.bash 2>/dev/null
source ~/third_party/third_party_ws/install/setup.bash 2>/dev/null
source ~/third_party/aurora_ws/install/setup.bash 2>/dev/null
export SPEECH_LANG=fr
pkill -f pick_and_place_node 2>/dev/null
pkill -f voice_pick_node 2>/dev/null
sleep 1
setsid python3 -u /home/ubuntu/speech_patch/pick_and_place_node_v6.py > ~/pick_and_place.log 2>&1 < /dev/null &
setsid python3 ~/voice_pick_node.py > ~/voice_pick.log 2>&1 < /dev/null &
sleep 3
echo "Nodes:"
ros2 node list 2>/dev/null | grep -E "pick_and_place|voice_pick"
echo "---"
tail -2 ~/pick_and_place.log
