#!/bin/bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo "=== Paramètres vocal_detect ==="
for p in awake_method awake_word enable_wakeup mode offline mic_type port; do
    val=$(ros2 param get /vocal_detect "$p" 2>/dev/null)
    echo "$p = $val"
done

echo ""
echo "=== Test echo asr_result (5s) ==="
timeout 5 ros2 topic echo /vocal_detect/asr_result 2>&1 || echo "(pas de message en 5s)"

echo ""
echo "=== Test echo wakeup (3s) ==="
timeout 3 ros2 topic echo /vocal_detect/wakeup 2>&1 || echo "(pas de message en 3s)"

echo ""
echo "=== Test echo battery (3s) ==="
timeout 3 ros2 topic echo /ros_robot_controller/battery 2>&1 || echo "(pas de message en 3s)"
