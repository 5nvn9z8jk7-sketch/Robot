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

# Fix: sid=100 -> 0 (modele VITS fr n'a qu'un speaker, sid=100 cause GatherElements ONNX error)
sed -i 's/offline_tts_speaker = 100/offline_tts_speaker = 0/' ~/ros2_ws/build/large_models/large_models/config.py 2>/dev/null
sed -i 's/offline_tts_speaker = 100/offline_tts_speaker = 0/' ~/ros2_ws/src/large_models/large_models/large_models/config.py 2>/dev/null

setsid python3 -u /home/ubuntu/ros2_ws/install/large_models/lib/large_models/tts_node --ros-args > ~/tts_node.log 2>&1 < /dev/null &
sleep 10

echo "TTS process:"
ps aux | grep tts_node | grep -v grep | head -1
echo "Log:"
cat ~/tts_node.log
