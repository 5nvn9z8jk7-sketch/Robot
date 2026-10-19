#!/bin/bash
source /opt/ros/humble/setup.bash 2>/dev/null
source ~/ros2_ws/install/setup.bash 2>/dev/null
source ~/third_party/third_party_ws/install/setup.bash 2>/dev/null
source ~/ros2_ws/.typerc 2>/dev/null

export SPEECH_LANG=fr
export SPEECH_FORCE_FR=1
export OLLAMA_URL=http://192.168.1.20:11434

pkill -9 -f tts_node 2>/dev/null
sleep 2

setsid python3 /home/ubuntu/ros2_ws/install/large_models/lib/large_models/tts_node --ros-args > ~/tts_node.log 2>&1 < /dev/null &
sleep 8

echo "TTS process:"
ps aux | grep tts_node | grep -v grep | head -1
echo "Log tail:"
tail -15 ~/tts_node.log
