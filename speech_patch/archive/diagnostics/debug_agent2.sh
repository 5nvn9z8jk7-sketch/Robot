#!/bin/bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo "=== agent_process: node info ==="
ros2 node info /agent_process 2>/dev/null

echo ""
echo "=== Topic asr_result: connections ==="
ros2 topic info /vocal_detect/asr_result 2>/dev/null
