#!/bin/bash
# restart_pc_asr.sh — Démarre le serveur ASR audio pour PC (port 9091)
source /opt/ros/humble/setup.bash 2>/dev/null
source ~/ros2_ws/install/setup.bash 2>/dev/null
source ~/ros2_ws/.typerc 2>/dev/null
export SPEECH_LANG=fr

pkill -f pc_audio_asr_server 2>/dev/null
sleep 1

setsid python3 ~/pc_audio_asr_server.py > ~/pc_audio_asr.log 2>&1 < /dev/null &
sleep 8

echo "=== Log ==="
tail -10 ~/pc_audio_asr.log
echo ""
echo "=== Port 9091 ==="
ss -tlnp 2>/dev/null | grep 9091 || netstat -tlnp 2>/dev/null | grep 9091 || echo "Port 9091 non ouvert"
