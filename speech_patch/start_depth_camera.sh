#!/bin/bash
source /opt/ros/humble/setup.bash 2>/dev/null
source ~/ros2_ws/install/setup.bash 2>/dev/null
source ~/third_party/third_party_ws/install/setup.bash 2>/dev/null
source ~/third_party/aurora_ws/install/setup.bash 2>/dev/null
export DEPTH_CAMERA_TYPE=aurora
export need_compile=True
if ros2 topic list 2>/dev/null | grep -q '/depth_cam/depth0/image_raw'; then
    echo 'Camera depth deja active'
    exit 0
fi
pkill -f aurora930_node 2>/dev/null
pkill -f orbbec_camera 2>/dev/null
pkill -f component_container 2>/dev/null
sleep 1
nohup ros2 launch peripherals depth_camera.launch.py depth_camera_name:=depth_cam > ~/aurora_cam.log 2>&1 &
echo "Aurora 930 camera PID=$!"
for i in $(seq 1 15); do
    sleep 1
    if ros2 topic list 2>/dev/null | grep -q '/depth_cam/depth0/image_raw'; then
        echo "Camera prete apres ${i}s"
        exit 0
    fi
done
echo 'ERREUR: camera non demarree'
tail -20 ~/aurora_cam.log
exit 1
