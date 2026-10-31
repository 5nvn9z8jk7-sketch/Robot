#!/bin/bash
source /opt/ros/humble/setup.bash 2>/dev/null
source ~/ros2_ws/install/setup.bash 2>/dev/null
source ~/third_party/third_party_ws/install/setup.bash 2>/dev/null
source ~/third_party/aurora_ws/install/setup.bash 2>/dev/null
source ~/ros2_ws/.typerc 2>/dev/null

# Kill all camera-related processes
pkill -9 -f aurora930_node 2>/dev/null
pkill -9 -f camera_container 2>/dev/null
pkill -9 -f orbbec_camera 2>/dev/null
pkill -9 -f depth_camera 2>/dev/null
sleep 2

# Launch camera
setsid ros2 launch peripherals depth_camera.launch.py depth_camera_name:=depth_cam > ~/aurora_cam.log 2>&1 < /dev/null &
echo "Launch PID: $!"

# Wait for topics
for i in $(seq 1 20); do
    sleep 1
    PUBS=$(ros2 topic info /depth_cam/depth0/image_raw 2>/dev/null | grep "Publisher count" | grep -o "[0-9]*")
    if [ "$PUBS" = "1" ]; then
        echo "Camera ready after ${i}s (publisher count: $PUBS)"
        ros2 topic list 2>/dev/null | grep depth_cam | sort
        exit 0
    fi
    echo "Waiting... ${i}s (publishers: ${PUBS:-0})"
done

echo "ERROR: camera not ready after 20s"
tail -20 ~/aurora_cam.log
exit 1
