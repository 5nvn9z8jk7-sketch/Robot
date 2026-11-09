#!/bin/bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo "=== agent_process: tous les parametres ==="
ros2 param list /agent_process 2>/dev/null

echo ""
echo "=== Parametres LLM ==="
for p in llm_url model_name api_key prompt use_vllm; do
    val=$(ros2 param get /agent_process "$p" 2>/dev/null)
    echo "$p = $val"
done

echo ""
echo "=== Variables d'environnement du processus agent_process ==="
PID=$(ps aux | grep "agent_process" | grep -v grep | awk '{print $2}' | head -1)
if [ -n "$PID" ]; then
    echo "PID: $PID"
    cat /proc/$PID/environ 2>/dev/null | tr '\0' '\n' | grep -i "ollama\|llm\|api\|url\|model\|speech" || echo "(pas de variables pertinentes)"
else
    echo "Processus agent_process non trouve"
fi

echo ""
echo "=== Test Ollama depuis le robot ==="
curl -s --connect-timeout 5 --max-time 10 http://192.168.1.20:11434/api/generate -d '{"model":"qwen3.5:9b","prompt":"Dis bonjour en francais","stream":false,"options":{"num_predict":50}}' 2>&1 | head -3
