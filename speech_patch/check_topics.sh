#!/bin/bash
# check_topics.sh — Liste les topics pertinents sur le robot
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo "=== Topics vocal_detect ==="
ros2 topic list 2>/dev/null | grep vocal_detect

echo ""
echo "=== Topics agent/llm ==="
ros2 topic list 2>/dev/null | grep -E "agent|llm|tts"

echo ""
echo "=== Topics controller/motor ==="
ros2 topic list 2>/dev/null | grep -E "controller|cmd_vel|odom"

echo ""
echo "=== Topics battery ==="
ros2 topic list 2>/dev/null | grep -i battery

echo ""
echo "=== Topic info asr_result ==="
ros2 topic info /vocal_detect/asr_result 2>/dev/null

echo ""
echo "=== Topic info cmd_vel ==="
ros2 topic info /controller/cmd_vel 2>/dev/null

echo ""
echo "=== Nodes actifs ==="
ros2 node list 2>/dev/null
