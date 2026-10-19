#!/bin/bash
echo "=== OllamaAPI.chat() signature et default max_tokens ==="
sed -n '858,970p' /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py | grep -n "def chat\|max_tokens\|num_predict\|temperature\|def __init__" | head -20

echo ""
echo "=== Default max_tokens dans le patch ==="
grep -n "max_tokens\|MAX_TOKENS\|num_predict\|4096\|2048\|1024\|512\|256\|128" /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py | head -20

echo ""
echo "=== Comment agent_process appelle le LLM ==="
grep -rn "max_tokens\|num_predict\|\.chat(\|stream_chat\|OllamaAPI\|openai\|OpenAI" /home/ubuntu/ros2_ws/src/large_models/large_models/large_models/agent_process.py 2>/dev/null | head -30

echo ""
echo "=== agent_process.py - section LLM ==="
grep -n "class\|def \|llm\|chat\|ollama\|openai\|max_tokens\|api_key\|base_url" /home/ubuntu/ros2_ws/src/large_models/large_models/large_models/agent_process.py 2>/dev/null | head -40
