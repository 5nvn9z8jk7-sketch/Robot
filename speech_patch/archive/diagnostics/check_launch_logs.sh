#!/bin/bash

echo "=== Processus de launch ==="
ps aux | grep "ros2 launch" | grep -v grep

echo ""
echo "=== Fichiers de log recents ==="
ls -lt ~/nohup.out 2>/dev/null
ls -lt ~/.ros/log/ 2>/dev/null
find ~/.ros/log -name "*.log" -mmin -30 2>/dev/null | head -10

echo ""
echo "=== Chercher les logs du launch (stdout du processus 6683) ==="
PID=6683
if [ -d /proc/$PID ]; then
    echo "FDs du processus $PID:"
    ls -la /proc/$PID/fd/ 2>/dev/null | head -20
    echo ""
    echo "Cmdline:"
    cat /proc/$PID/cmdline 2>/dev/null | tr '\0' ' '
    echo ""
    echo "CWD:"
    readlink /proc/$PID/cwd 2>/dev/null
else
    echo "Processus $PID non trouve"
fi

echo ""
echo "=== Logs ROS2 pour agent_process ==="
find ~/.ros/log -name "*agent*" 2>/dev/null | head -5

echo ""
echo "=== Test direct: appeler le service set_prompt puis publier ASR ==="
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo "--- Set prompt ---"
ros2 service call /agent_process/set_prompt large_models_msgs/srv/SetString "{data: 'Tu es un robot mobile. Reponds en JSON: {\"action\": \"move('"'"'forward'"'"', 1, 0)\", \"response\": \"J'"'"'avance\"}'}" 2>&1

echo ""
echo "--- Publish ASR 'avance' ---"
ros2 topic pub --once /vocal_detect/asr_result std_msgs/msg/String "{data: 'avance'}" 2>&1

echo ""
echo "--- Echo agent_process/result (15s) ---"
timeout 15 ros2 topic echo /agent_process/result 2>&1 || echo "(pas de resultat en 15s)"

echo ""
echo "--- Echo tts_node/tts_text (5s) ---"
timeout 5 ros2 topic echo /tts_node/tts_text 2>&1 || echo "(pas de TTS en 5s)"
