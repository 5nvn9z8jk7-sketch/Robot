#!/bin/bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo "=== Battery topic info ==="
ros2 topic info /ros_robot_controller/battery 2>/dev/null

echo ""
echo "=== Battery echo (5s) ==="
timeout 5 ros2 topic echo /ros_robot_controller/battery 2>&1 || echo "(pas de message en 5s)"

echo ""
echo "=== ros_robot_controller node info ==="
ros2 node info /ros_robot_controller 2>/dev/null | head -25

echo ""
echo "=== Serial errors? ==="
dmesg 2>/dev/null | grep -i "serial\|ch341\|ttyUSB\|usb" | tail -10 || echo "(pas de dmesg accessible)"
