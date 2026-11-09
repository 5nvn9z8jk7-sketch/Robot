#!/bin/bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo "=== Nodes vocaux ==="
ros2 node list 2>/dev/null | grep -E "simple_asr|vocal_detect|agent_process|tts_node|llm_control"

echo ""
echo "=== Topic asr_result publishers ==="
ros2 topic info /vocal_detect/asr_result 2>/dev/null

echo ""
echo "=== Log simple_asr ==="
cat ~/simple_asr.log
