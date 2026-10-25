#!/bin/bash
# deploy_pick_v4.sh — Déploie pick_and_place_node_v4 (avec caméra DEPTH)

ROBOT_DIR="/home/ubuntu/speech_patch"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Déploiement pick_and_place_node_v4 (DEPTH + 360 scan) ==="

if ! ping -c 1 -W 2 192.168.1.30 > /dev/null 2>&1; then
    echo "❌ Robot non accessible. Allume-le d'abord."
    exit 1
fi

ssh robot "mkdir -p $ROBOT_DIR"
scp "$LOCAL_DIR/pick_and_place_node_v4.py" "robot:$ROBOT_DIR/"
echo "✅ Fichier transféré"

# Arrêter les anciennes versions
ssh robot "pkill -f pick_and_place_node 2>/dev/null; sleep 1"

# Lancer v4
ssh robot "bash -c '
source /home/ubuntu/ros2_ws/install/setup.bash
source /opt/ros/humble/setup.bash
nohup python3 $ROBOT_DIR/pick_and_place_node_v4.py \
  --ros-args \
  -p gripper_reach:=0.18 \
  -p linear_speed:=0.10 \
  -p angular_speed:=0.5 \
  -p scan_step_deg:=30 \
  -p min_y_pixel:=200 \
  -p target_size_px:=80 \
  -p distance_tolerance:=0.02 \
  -p use_depth:=true \
  > /tmp/pick_v4.log 2>&1 &
echo \"Lancé PID \$!\"
'"

sleep 3

echo "=== Vérification ==="
ssh robot "bash -c 'source /home/ubuntu/ros2_ws/install/setup.bash && ros2 node list 2>/dev/null | grep pick'"

echo ""
echo "✅ pick_and_place_node_v4 déployé (avec caméra depth)"
echo ""
echo "Vérifier que la depth est active:"
echo "  ssh robot \"bash -c 'source /home/ubuntu/ros2_ws/install/setup.bash && timeout 2 ros2 topic hz /depth_cam/depth0/image_raw'\""
echo ""
echo "Logs: ssh robot 'tail -f /tmp/pick_v4.log'"
