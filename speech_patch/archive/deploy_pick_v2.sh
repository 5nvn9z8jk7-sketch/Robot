#!/bin/bash
# deploy_pick_v2.sh — Déploie et lance pick_and_place_node_v2 sur le robot
# Version sans caméra depth, avec distance fixe configurable

set -e

ROBOT_DIR="/home/ubuntu/speech_patch"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Déploiement pick_and_place_node_v2 ==="

# 1. Créer le répertoire sur le robot
ssh robot "mkdir -p $ROBOT_DIR"

# 2. Transférer le fichier
scp "$LOCAL_DIR/pick_and_place_node_v2.py" "robot:$ROBOT_DIR/"

# 3. Arrêter l'ancien nœud pick_and_place
ssh robot "pkill -f pick_and_place_node 2>/dev/null || true"
sleep 1

# 4. Lancer le nouveau nœud
ssh robot "bash -lc '
source /home/ubuntu/ros2_ws/install/setup.bash
source /opt/ros/humble/setup.bash
nohup python3 $ROBOT_DIR/pick_and_place_node_v2.py \
  --ros-args \
  -p fixed_distance_m:=0.25 \
  -p gripper_reach:=0.15 \
  -p linear_speed:=0.15 \
  -p angular_speed:=0.8 \
  -p min_y_pixel:=200 \
  > /tmp/pick_v2.log 2>&1 &
echo \"Lancé avec PID \$!\"
'"

sleep 3

# 5. Vérifier que le nœud est actif
echo "=== Vérification ==="
ssh robot "bash -lc 'source /home/ubuntu/ros2_ws/install/setup.bash && ros2 node list 2>/dev/null | grep pick'"

echo ""
echo "✅ pick_and_place_node_v2 déployé"
echo ""
echo "Paramètres ajustables en temps réel:"
echo "  ros2 param set /pick_and_place_node_v2 fixed_distance_m 0.30"
echo "  ros2 param set /pick_and_place_node_v2 gripper_reach 0.15"
echo "  ros2 param list /pick_and_place_node_v2"
echo ""
echo "Logs: ssh robot 'tail -f /tmp/pick_v2.log'"
