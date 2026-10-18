#!/bin/bash

echo "=== Launch file dans install ==="
find /home/ubuntu/ros2_ws/install/large_models_examples -name "llm_control_move*" 2>/dev/null
cat /home/ubuntu/ros2_ws/install/large_models_examples/share/large_models_examples/launch/llm_control_move.launch.py 2>/dev/null

echo ""
echo "=== Launch file source ==="
find /home/ubuntu/ros2_ws/src/large_models_examples -name "llm_control_move*" -o -name "*llm_control*" 2>/dev/null

echo ""
echo "=== vocal_detect.launch.py ==="
cat /home/ubuntu/ros2_ws/src/large_models/large_models/launch/vocal_detect.launch.py 2>/dev/null

echo ""
echo "=== vocal_detect.py - parametres mic_type et wakeup ==="
grep -n "mic_type\|enable_wakeup\|awake_word\|awake_method\|WonderEcho\|mic6\|ring_mic\|MIC_TYPE\|declare_parameter\|get_parameter" /home/ubuntu/ros2_ws/src/large_models/large_models/large_models/vocal_detect.py 2>/dev/null | head -40

echo ""
echo "=== .typerc ==="
cat /home/ubuntu/ros2_ws/.typerc
