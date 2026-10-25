#!/bin/bash
# deploy_pick_v3.sh — Déploie pick_and_place_node_v3 (scan 360° + auto-distance)
# À lancer quand le robot est rechargé et allumé

ROBOT_DIR="/home/ubuntu/speech_patch"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Déploiement pick_and_place_node_v3 (360° + auto-distance) ==="

# Vérifier que le robot est accessible
if ! ping -c 1 -W 2 192.168.1.30 > /dev/null 2>&1; then
    echo "❌ Robot non accessible. Allume-le d'abord."
    exit 1
fi

# Créer le répertoire
ssh robot "mkdir -p $ROBOT_DIR"

# Transférer
scp "$LOCAL_DIR/pick_and_place_node_v3.py" "robot:$ROBOT_DIR/"
echo "✅ Fichier transféré"

# Arrêter les anciennes versions
ssh robot "pkill -f pick_and_place_node 2>/dev/null; sleep 1"

# Lancer v3
ssh robot "bash -c '
source /home/ubuntu/ros2_ws/install/setup.bash
source /opt/ros/humble/setup.bash
nohup python3 $ROBOT_DIR/pick_and_place_node_v3.py \
  --ros-args \
  -p target_size_px:=80 \
  -p gripper_reach:=0.18 \
  -p linear_speed:=0.12 \
  -p angular_speed:=0.6 \
  -p scan_step_deg:=30 \
  -p min_y_pixel:=200 \
  -p size_tolerance:=0.15 \
  > /tmp/pick_v3.log 2>&1 &
echo \"Lancé PID \$!\"
'"

sleep 3

# Vérifier
echo "=== Vérification ==="
ssh robot "bash -c 'source /home/ubuntu/ros2_ws/install/setup.bash && ros2 node list 2>/dev/null | grep pick'"

echo ""
echo "✅ pick_and_place_node_v3 déployé"
echo ""
echo "Commandes vocales disponibles:"
echo "  - \"Attrape le cube rouge\"     → détection directe devant"
echo "  - \"Cherche le cube rouge\"     → scan 360° puis attrape"
echo "  - \"Va chercher le cube\"        → scan 360° puis attrape"
echo ""
echo "Paramètres ajustables:"
echo "  ros2 param set /pick_and_place_node_v3 target_size_px 80"
echo "  ros2 param set /pick_and_place_node_v3 scan_step_deg 30"
echo "  ros2 param list /pick_and_place_node_v3"
echo ""
echo "Logs: ssh robot 'tail -f /tmp/pick_v3.log'"
