#!/bin/bash
source /opt/ros/humble/setup.bash 2>/dev/null
source ~/ros2_ws/install/setup.bash 2>/dev/null
source ~/ros2_ws/.typerc 2>/dev/null
export SPEECH_LANG=fr
pkill -f simple_asr_node 2>/dev/null
sleep 2
setsid python3 ~/simple_asr_node.py > ~/simple_asr.log 2>&1 < /dev/null &
sleep 8
echo "=== ASR log ==="
tail -10 ~/simple_asr.log
