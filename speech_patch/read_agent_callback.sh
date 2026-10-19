#!/bin/bash
echo "=== agent_process.py - asr_callback complet ==="
sed -n '156,200p' /home/ubuntu/ros2_ws/src/large_models/large_models/large_models/agent_process.py

echo ""
echo "=== agent_process.py - init_process ==="
sed -n '100,106p' /home/ubuntu/ros2_ws/src/large_models/large_models/large_models/agent_process.py

echo ""
echo "=== agent_process.py - __init__ complet (lines 27-100) ==="
sed -n '27,100p' /home/ubuntu/ros2_ws/src/large_models/large_models/large_models/agent_process.py

echo ""
echo "=== agent_process.py - config (llm_model, ollama_host, prompt) ==="
sed -n '1,26p' /home/ubuntu/ros2_ws/src/large_models/large_models/large_models/agent_process.py

echo ""
echo "=== large_models/config.py ==="
grep -n "llm_model\|offline_llm\|ollama_host\|prompt\|PROMPT\|system_prompt\|DEFAULT" /home/ubuntu/ros2_ws/src/large_models/large_models/config.py | head -30
