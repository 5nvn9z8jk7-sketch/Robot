#!/bin/bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo "enable_wakeup = $(ros2 param get /vocal_detect enable_wakeup 2>/dev/null)"
echo "awake_word = $(ros2 param get /vocal_detect awake_word 2>/dev/null)"
echo "mode = $(ros2 param get /vocal_detect mode 2>/dev/null)"
echo "mic_type = $(ros2 param get /vocal_detect mic_type 2>/dev/null)"
echo "awake_method = $(ros2 param get /vocal_detect awake_method 2>/dev/null)"
echo "offline = $(ros2 param get /vocal_detect offline 2>/dev/null)"
echo "port = $(ros2 param get /vocal_detect port 2>/dev/null)"
