#!/bin/bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo "=== ROS logs vocal_detect (dernieres 30 lignes) ==="
find ~/.ros/log -name "*vocal_detect*" -type f 2>/dev/null | tail -1 | xargs tail -30 2>/dev/null || echo "(pas de log trouve)"

echo ""
echo "=== Tous les logs ROS recents ==="
ls -lt ~/.ros/log/latest/ 2>/dev/null | head -20

echo ""
echo "=== Process vocal_detect CPU/MEM ==="
ps aux | grep vocal_detect | grep -v grep

echo ""
echo "=== Test: publier un faux resultat ASR pour verifier la chaine ==="
echo "(on va tester si agent_process reagit a un message manuel)"

echo ""
echo "=== Verifier si le modele ASR existe ==="
ls -la ~/.local/share/sherpa-onnx* 2>/dev/null || ls -la /home/ubuntu/.local/share/sherpa* 2>/dev/null || echo "(dossier sherpa non trouve dans les chemins standards)"
find /home/ubuntu -name "*sherpa*" -type d 2>/dev/null | head -5

echo ""
echo "=== Verifier les modeles dans le package large_models ==="
find ~/ros2_ws/src -name "*sherpa*" -o -name "*asr*" -o -name "*model*" 2>/dev/null | grep -v ".git" | head -20
