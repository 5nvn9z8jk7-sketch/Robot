#!/bin/bash
# Lance la caméra depth Aurora pour le pick-and-place
# Usage: bash start_depth_camera.sh

source /home/ubuntu/ros2_ws/install/setup.bash

echo "=== Vérification caméra depth ==="

# Vérifier si le topic publie déjà
if timeout 2 ros2 topic hz /depth_cam/depth0/image_raw 2>/dev/null | head -1 | grep -q "average rate"; then
    echo "✅ Caméra depth déjà active"
    exit 0
fi

echo "⚠️  Caméra depth inactive — tentative de lancement..."

# Tuer les anciens processus caméra
pkill -f "aurora" 2>/dev/null
pkill -f "depth_cam" 2>/dev/null
pkill -f "usb_cam" 2>/dev/null
sleep 2

# Essayer de lancer via bringup (qui inclut depth_camera)
echo "=== Lancement via bringup (caméra uniquement) ==="
nohup ros2 launch peripherals depth_camera.launch.py > /tmp/depth_cam.log 2>&1 &
sleep 5

# Vérifier
if timeout 2 ros2 topic hz /depth_cam/depth0/image_raw 2>/dev/null | head -1 | grep -q "average rate"; then
    echo "✅ Caméra depth lancée avec succès"
    exit 0
fi

# Si échec, essayer usb_cam
echo "=== Tentative avec usb_cam ==="
nohup ros2 run usb_cam usb_cam_node_exe --ros-args -p video_device:=/dev/video0 -p image_width:=640 -p image_height:=480 -p pixel_format:=yuyv -p camera_frame_id:=depth_cam > /tmp/usb_cam.log 2>&1 &
sleep 3

# Vérifier les topics disponibles
if ros2 topic list 2>/dev/null | grep -q "image_raw"; then
    echo "✅ Caméra lancée (topic image_raw disponible)"
    ros2 topic list 2>/dev/null | grep image_raw
else
    echo "❌ Impossible de lancer la caméra"
    echo "Vérifie que la caméra est branchée et alimentée"
    exit 1
fi
