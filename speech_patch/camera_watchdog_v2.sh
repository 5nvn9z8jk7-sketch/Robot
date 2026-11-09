#!/bin/bash
# Watchdog camera v2 - verifie le FLUX de donnees, pas juste le publisher
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash 2>/dev/null
source ~/third_party/aurora_ws/install/setup.bash 2>/dev/null

LOG=~/watchdog.log
echo "[$(date)] Watchdog v2 demarre (check flux donnees)" >> $LOG

while true; do
    # Verifier si la camera publie des DONNEES (pas juste le publisher)
    # On utilise ros2 topic hz avec timeout court
    RATE=$(timeout 4 ros2 topic hz /depth_cam/rgb0/image_raw 2>&1 | grep 'average rate' | tail -1 | awk '{print $3}')
    
    if [ -z "$RATE" ]; then
        echo "[$(date)] CAMERA NE STREAM PAS (rate=rien) - Redemarrage..." >> $LOG
        
        pkill -9 -f aurora930_node 2>/dev/null
        sleep 2
        echo '1-2.2.1' | sudo tee /sys/bus/usb/drivers/usb/unbind 2>/dev/null
        sleep 2
        echo '1-2.2.1' | sudo tee /sys/bus/usb/drivers/usb/bind 2>/dev/null
        sleep 3
        
        setsid ~/third_party/aurora_ws/install/deptrum-ros-driver-aurora930/lib/deptrum-ros-driver-aurora930/aurora930_node \
          --ros-args -r __ns:=/ \
          -r depth/image_raw:=depth_cam/depth0/image_raw \
          -r ir/camera_info:=depth_cam/depth0/camera_info \
          -r ir/image_raw:=depth_cam/ir0/image_raw \
          -r points2:=depth_cam/depth0/points \
          -r rgb/camera_info:=depth_cam/rgb0/camera_info \
          -r rgb/image_raw:=depth_cam/rgb0/image_raw \
          >> ~/aurora.log 2>&1 < /dev/null &
        disown
        
        sleep 12
        RATE2=$(timeout 4 ros2 topic hz /depth_cam/rgb0/image_raw 2>&1 | grep 'average rate' | tail -1 | awk '{print $3}')
        echo "[$(date)] Apres redemarrage: rate=$RATE2 Hz" >> $LOG
    else
        echo "[$(date)] Camera OK ($RATE Hz)" >> $LOG
    fi
    
    sleep 20
done
