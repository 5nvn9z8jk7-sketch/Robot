#!/bin/bash
# Test: le mouvement des servos tue-t-il la caméra ?
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash 2>/dev/null

check_stream() {
  timeout 5 ros2 topic hz /depth_cam/rgb0/image_raw 2>&1 | grep "average rate" | head -1
}

echo "--- stream avant:"
check_stream

echo "--- mouvement 1 servo (pince 10):"
ros2 topic pub --once /servo_controller servo_controller_msgs/msg/ServosPosition \
  "{duration: 0.5, position_unit: pwm, position: [{id: 10, position: 250}]}" >/dev/null 2>&1
sleep 3
echo "--- stream apres 1 servo:"
check_stream

echo "--- mouvement 6 servos (tous a 500):"
ros2 topic pub --once /servo_controller servo_controller_msgs/msg/ServosPosition \
  "{duration: 1.0, position_unit: pwm, position: [{id: 1, position: 500}, {id: 2, position: 500}, {id: 3, position: 500}, {id: 4, position: 500}, {id: 5, position: 500}, {id: 10, position: 200}]}" >/dev/null 2>&1
sleep 4
echo "--- stream apres 6 servos:"
check_stream
echo "--- FIN TEST ---"
