#!/bin/bash
# deploy_watchdog.sh — Déploie et lance le watchdog sur le robot

LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Déploiement du Watchdog ==="

if ! ping -c 1 -W 2 192.168.1.30 > /dev/null 2>&1; then
    echo "❌ Robot non accessible"
    exit 1
fi

# Transférer
scp "$LOCAL_DIR/robot_watchdog.py" "robot:/home/ubuntu/speech_patch/"
echo "✅ Fichier transféré"

# Arrêter l'ancien watchdog
ssh robot "pkill -f robot_watchdog 2>/dev/null; sleep 1"

# Lancer le watchdog
ssh robot "bash -c '
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
nohup python3 /home/ubuntu/speech_patch/robot_watchdog.py --interval 10 --max-restarts 5 > /tmp/watchdog.log 2>&1 &
echo \"Watchdog lancé PID \$!\"
'"

sleep 2

echo ""
echo "✅ Watchdog actif"
echo ""
echo "Vérifier: ssh robot 'tail -f /tmp/watchdog.log'"
echo "Arrêter:  ssh robot 'pkill -f robot_watchdog'"
