#!/bin/bash
# Lance le nœud ASR simple sur le robot (avec verrou anti-double)
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
export SPEECH_LANG=fr
export SPEECH_FORCE_FR=1
export SHERPA_DIR=~/third_party/sherpa-onnx
export ASR_TIMEOUT=30

# Verrou: tuer les instances precedentes
for pid in $(ps aux | grep simple_asr_node | grep -v grep | awk '{print $2}'); do
    kill -9 "$pid" 2>/dev/null
done
sleep 1

echo "Demarrage simple_asr_node..."
exec python3 ~/simple_asr_node.py
