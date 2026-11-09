#!/bin/bash
# deploy_watchdog.sh — Déploie et lance les superviseurs sur le robot (détachés via setsid)
# Le démarrage au boot est installé par install_watchdog_autostart.sh (une seule fois)

LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Déploiement des superviseurs ==="

if ! ping -c 1 -W 2 192.168.1.30 > /dev/null 2>&1; then
    echo "❌ Robot non accessible"
    exit 1
fi

# Transférer les superviseurs + le lanceur
scp "$LOCAL_DIR/robot_watchdog.py" \
    "$LOCAL_DIR/camera_supervisor.py" \
    "$LOCAL_DIR/start_camera_supervisor.sh" \
    "$LOCAL_DIR/start_watchdogs.sh" \
    "robot:/home/ubuntu/speech_patch/"
echo "✅ Fichiers transférés"

# Lancer via le script idempotent (setsid nohup → survit à la fin de la session ssh)
ssh robot "bash /home/ubuntu/speech_patch/start_watchdogs.sh"

echo ""
echo "Vérifier : ssh robot 'tail -f /tmp/watchdog.log ~/camera_events.log'"
echo "Arrêter  : ssh robot 'pkill -f \"[r]obot_watchdog.py\"; pkill -f \"[c]amera_supervisor.py\"'"
