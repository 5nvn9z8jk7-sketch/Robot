#!/bin/bash
# deploy_mission.sh — Déploie le nœud de mission autonome

LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Déploiement Mission Autonome ==="

if ! ping -c 1 -W 2 192.168.1.30 > /dev/null 2>&1; then
    echo "❌ Robot non accessible"
    exit 1
fi

ssh robot "mkdir -p /home/ubuntu/speech_patch"
scp "$LOCAL_DIR/autonomous_mission_node.py" "robot:/home/ubuntu/speech_patch/"
echo "✅ Fichier transféré"

ssh robot "pkill -f autonomous_mission_node 2>/dev/null; sleep 1"

ssh robot "bash -c '
source /home/ubuntu/ros2_ws/install/setup.bash
source /opt/ros/humble/setup.bash
nohup python3 /home/ubuntu/speech_patch/autonomous_mission_node.py > /tmp/mission.log 2>&1 &
echo \"Mission node lancé PID \$!\"
'"

sleep 2
echo "=== Vérification ==="
ssh robot "bash -c 'source /home/ubuntu/ros2_ws/install/setup.bash && ros2 node list 2>/dev/null | grep mission'"

echo ""
echo "✅ Mission autonome prête"
echo ""
echo "Commandes vocales:"
echo "  'Mission attrape tous les cubes' → attrape tous les cubes un par un"
echo "  'Patrouille' → patrouille 2 minutes"
echo "  'Retourne à la base' → revient au départ"
echo "  'Status' → annonce batterie + position"
echo "  'Stop' → arrête tout"
echo ""
echo "Logs: ssh robot 'tail -f /tmp/mission.log'"
