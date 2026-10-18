#!/bin/bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo "=== agent_process: topic connections ==="
ros2 node info /agent_process 2>/dev/null

echo ""
echo "=== Topic /vocal_detect/asr_result: publishers et subscribers ==="
ros2 topic info /vocal_detect/asr_result 2>/dev/null

echo ""
echo "=== Test: Ollama depuis le robot ==="
curl -s --connect-timeout 5 http://192.168.1.20:11434/api/generate -d '{
  "model": "qwen3.5:9b",
  "prompt": "Tu es un robot. Reponds en JSON: {\"action\": \"move('"'"'forward'"'"', 1, 0)\", \"response\": \"J'"'"'avance\"}",
  "stream": false,
  "options": {"num_predict": 100}
}' 2>&1 | head -5

echo ""
echo "=== agent_process: parametres ==="
ros2 param list /agent_process 2>/dev/null

echo ""
echo "=== agent_process: log stdout (si disponible) ==="
# Le noeud tourne depuis le launch, chercher les logs ROS
ls -la ~/.ros/log/ 2>/dev/null
find ~/.ros/log -name "*.log" -newer ~/simple_asr.log 2>/dev/null | head -5

echo ""
echo "=== Verifier si le noeud agent_process recoit des messages ==="
echo "Test: publier sur /vocal_detect/asr_result et ecouter /agent_process/result pendant 10s"
ros2 topic pub --once /vocal_detect/asr_result std_msgs/msg/String "{data: 'test avance'}" 2>&1 &
sleep 1
timeout 10 ros2 topic echo /agent_process/result 2>&1 || echo "(pas de resultat agent_process en 10s)"
