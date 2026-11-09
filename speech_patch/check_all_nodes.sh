#!/bin/bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo "=== Tous les noeuds vocaux ==="
ros2 node list 2>/dev/null | grep -E "simple_asr|vocal_detect|agent_process|tts_node|llm_control|ros_robot_controller|odom_publisher"

echo ""
echo "=== Processus actifs ==="
ps aux | grep -E "agent_process|llm_control_move|tts_node|simple_asr_node" | grep -v grep

echo ""
echo "=== Test: publier un faux ASR pour voir si la chaine reagit ==="
echo "(on va publier 'avance' manuellement sur /vocal_detect/asr_result)"
ros2 topic pub --once /vocal_detect/asr_result std_msgs/msg/String "{data: 'avance'}" 2>&1 &
sleep 3
echo "Message publie"

echo ""
echo "=== Verification cmd_vel (5s) ==="
timeout 5 ros2 topic echo /controller/cmd_vel 2>&1 || echo "(pas de mouvement en 5s)"

echo ""
echo "=== Logs agent_process (dernieres lignes) ==="
find ~/.ros/log -name "*agent_process*" -type f 2>/dev/null | tail -1 | xargs tail -20 2>/dev/null || echo "(pas de logs)"
